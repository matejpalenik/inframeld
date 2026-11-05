from typing import override
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.human_admission_facts_dto import (
    HumanAdmissionFactsDTO,
)
from inframeld_backend.access.application.protocols.human_admission_writer import (
    HumanAdmissionWriter,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.organization_action import OrganizationAction
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.infrastructure.mappers.postgres_human_credential_state_mapper import (
    PostgresHumanCredentialStateMapper,
)
from inframeld_backend.access.infrastructure.readers.human_credential_state_queries import (
    HumanCredentialStateQueries,
)
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.access.infrastructure.rows.human_admission_operation_result_row import (
    HumanAdmissionOperationResultRow,
)
from inframeld_backend.access.infrastructure.rows.human_credential_version_row import (
    HumanCredentialVersionRow,
)
from inframeld_backend.access.infrastructure.rows.human_identity_link_row import (
    HumanIdentityLinkRow,
)
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.shared.application.enums.operation_reservation_state import (
    OperationReservationState,
)
from inframeld_backend.shared.application.errors.application_errors import (
    ConflictError,
    DependencyUnavailableError,
    StaleRevisionError,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)


class PostgresHumanAdmissionWriter(HumanAdmissionWriter):
    """Keep each admission's account, audit and immutable outcome in one transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def save(
        self,
        *,
        facts: HumanAdmissionFactsDTO,
        principal: Principal,
        actor_id: PrincipalId,
        operation_id: OperationId,
    ) -> None:
        try:
            await self._save(
                facts=facts, principal=principal, actor_id=actor_id, operation_id=operation_id
            )
        except (TimeoutError, OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None

    async def _save(
        self,
        *,
        facts: HumanAdmissionFactsDTO,
        principal: Principal,
        actor_id: PrincipalId,
        operation_id: OperationId,
    ) -> None:
        """Persist the admission and retained receipt under the original checked reservation."""
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Admission persistence requires the active caller transaction.")
        organization_id = facts.actor.principal.organization_id
        changed = facts.principal is None
        if (
            actor_id != facts.actor.principal.id
            or facts.actor.principal.kind is not PrincipalKind.HUMAN
            or facts.actor.principal.status is not PrincipalStatus.ACTIVE
            or principal.organization_id != organization_id
            or principal.kind is not PrincipalKind.HUMAN
            or principal.status is not PrincipalStatus.ACTIVE
            or (facts.principal is not None and principal.id != facts.principal.id)
            or facts.credential_state.identity != facts.identity
            or facts.credential_state.installation_id != facts.installation_id
        ):
            raise RuntimeError("Admission persistence changed its checked scope.")

        with self._session.no_autoflush:
            reservation = await self._session.scalar(
                select(IdempotencyReservationRow.operation_id).where(
                    IdempotencyReservationRow.operation_id == operation_id.value,
                    IdempotencyReservationRow.principal_id == actor_id.value,
                    IdempotencyReservationRow.organization_id == organization_id.value,
                    IdempotencyReservationRow.project_id.is_(None),
                    IdempotencyReservationRow.method == "POST",
                    IdempotencyReservationRow.requested_route
                    == f"/v1/organizations/{organization_id.value}/human-admissions",
                    IdempotencyReservationRow.lookup_authority_family == "organization_action_use",
                    IdempotencyReservationRow.lookup_action_id
                    == OrganizationAction.ADMIT_USERS.value,
                    IdempotencyReservationRow.state == OperationReservationState.IN_PROGRESS,
                    IdempotencyReservationRow.replay_kind.is_(None),
                    IdempotencyReservationRow.expires_at.is_(None),
                )
            )
            if reservation is None:
                raise ConflictError("Admission has no matching original reservation.")
            revision = await self._session.scalar(
                select(OrganizationRow.access_revision).where(
                    OrganizationRow.id == organization_id.value
                )
            )
            if revision is None or revision != facts.actor.access_revision:
                raise StaleRevisionError()
            link = await self._session.scalar(
                select(HumanIdentityLinkRow)
                .where(
                    HumanIdentityLinkRow.authority == facts.identity.authority.value,
                    HumanIdentityLinkRow.subject == facts.identity.subject.value,
                )
                .execution_options(populate_existing=True, autoflush=False)
            )
            if (changed and link is not None) or (
                not changed
                and (
                    link is None
                    or link.principal_id != principal.id.value
                    or link.organization_id != organization_id.value
                )
            ):
                raise ConflictError("The checked human identity binding changed.")
            if not changed:
                current = await self._session.scalar(
                    select(PrincipalRow.id).where(
                        PrincipalRow.id == principal.id.value,
                        PrincipalRow.organization_id == organization_id.value,
                        PrincipalRow.kind == PrincipalKind.HUMAN,
                        PrincipalRow.status == PrincipalStatus.ACTIVE,
                    )
                )
                if current is None:
                    raise ConflictError("The checked human is no longer admissible.")
            state_row = (
                (
                    await self._session.execute(
                        HumanCredentialStateQueries.for_identity(facts.identity)
                    )
                )
                .tuples()
                .one_or_none()
            )
            state = PostgresHumanCredentialStateMapper.to_state(facts.identity, state_row)
            if state.installation_id != facts.installation_id:
                raise ConflictError("The checked installation identity changed.")
            if state.has_pending_recovery:
                raise ConflictError("The checked human is no longer admissible.")
            if state.version is None and state_row is not None and state_row[3]:
                raise DependencyUnavailableError()

        if changed and revision == RevisionValidation.MAX_VALUE:
            raise ConflictError("The Access revision cannot advance.")
        if changed:
            self._session.add(
                PrincipalRow(
                    id=principal.id.value,
                    organization_id=organization_id.value,
                    kind=PrincipalKind.HUMAN,
                    status=PrincipalStatus.ACTIVE,
                    display_name=facts.identity.subject.value,
                )
            )
            await self._session.flush()
            self._session.add(
                HumanIdentityLinkRow(
                    authority=facts.identity.authority.value,
                    subject=facts.identity.subject.value,
                    organization_id=organization_id.value,
                    principal_id=principal.id.value,
                    principal_kind=PrincipalKind.HUMAN,
                )
            )
            if state.version is None:
                self._session.add(
                    HumanCredentialVersionRow(
                        installation_id=facts.installation_id.value,
                        authority=facts.identity.authority.value,
                        subject=facts.identity.subject.value,
                        version=1,
                    )
                )
            await self._session.flush()
            advanced = await self._session.scalar(
                update(OrganizationRow)
                .where(
                    OrganizationRow.id == organization_id.value,
                    OrganizationRow.access_revision == revision,
                )
                .values(access_revision=OrganizationRow.access_revision + 1)
                .returning(OrganizationRow.access_revision)
            )
            if advanced != revision + 1:
                raise StaleRevisionError()

        after_revision = revision + int(changed)
        self._session.add(
            HumanAdmissionOperationResultRow(
                operation_id=operation_id.value,
                installation_id=facts.installation_id.value,
                authority=facts.identity.authority.value,
                subject=facts.identity.subject.value,
                organization_id=organization_id.value,
                actor_principal_id=actor_id.value,
                principal_id=principal.id.value,
                before_revision=revision,
                access_revision=after_revision,
                changed=changed,
                status_code=201 if changed else 200,
            )
        )
        self._session.add(
            AccessAuditEventRow(
                id=uuid4(),
                organization_id=organization_id.value,
                actor_kind=PrincipalKind.HUMAN.value,
                actor_principal_id=actor_id.value,
                affected_principal_id=principal.id.value,
                event_type="human_admitted" if changed else "human_admission_unchanged",
                target_kind="principal",
                target_id=principal.id.value,
                action=OrganizationAction.ADMIT_USERS.value,
                before_values={"access_revision": revision, "admitted": not changed},
                after_values={"access_revision": after_revision, "admitted": True},
                correlation_id=operation_id.value,
            )
        )
        await self._session.flush()
