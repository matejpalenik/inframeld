from datetime import timedelta
from typing import override
from uuid import UUID, uuid4

from sqlalchemy import DateTime, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.commands.restore_human_command import RestoreHumanCommand
from inframeld_backend.access.application.commands.suspend_human_command import SuspendHumanCommand
from inframeld_backend.access.application.dtos.human_lifecycle_facts_dto import (
    HumanLifecycleFactsDTO,
)
from inframeld_backend.access.application.dtos.human_restoration_result_dto import (
    HumanRestorationResultDTO,
)
from inframeld_backend.access.application.dtos.human_suspension_result_dto import (
    HumanSuspensionResultDTO,
)
from inframeld_backend.access.application.protocols.human_lifecycle_writer import (
    HumanLifecycleWriter,
)
from inframeld_backend.access.domain.entities.human_suspension import HumanSuspension
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.organization_action import OrganizationAction
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.access.infrastructure.rows.human_credential_version_row import (
    HumanCredentialVersionRow,
)
from inframeld_backend.access.infrastructure.rows.human_lifecycle_operation_result_row import (
    HumanLifecycleOperationResultRow,
)
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.shared.application.dtos.new_operation_reservation_dto import (
    NewOperationReservationDTO,
)
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.enums.operation_lookup_authority_family import (
    OperationLookupAuthorityFamily,
)
from inframeld_backend.shared.application.enums.operation_reservation_state import (
    OperationReservationState,
)
from inframeld_backend.shared.application.errors.application_errors import (
    ConflictError,
    DependencyUnavailableError,
    StaleRevisionError,
)
from inframeld_backend.shared.application.value_objects.job_id import JobId
from inframeld_backend.shared.application.value_objects.request_id import RequestId
from inframeld_backend.shared.infrastructure.rows.durable_job_row import DurableJobRow
from inframeld_backend.shared.infrastructure.rows.human_suspension_obligation_row import (
    HumanSuspensionObligationRow,
)
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)


class PostgresHumanLifecycleWriter(HumanLifecycleWriter):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def save_suspension(
        self,
        *,
        facts: HumanLifecycleFactsDTO,
        command: SuspendHumanCommand,
        target: Principal,
        suspension: HumanSuspension,
        operation: NewOperationReservationDTO,
        request_id: RequestId,
    ) -> None:
        before = self._checked_target(facts, target)
        if target.status is before.status:
            return
        original = await self._session.scalar(
            select(IdempotencyReservationRow).where(
                IdempotencyReservationRow.operation_id == operation.operation_id.value,
                IdempotencyReservationRow.principal_id == facts.actor.id.value,
                IdempotencyReservationRow.organization_id == facts.organization_id.value,
                IdempotencyReservationRow.project_id.is_(None),
                IdempotencyReservationRow.method == HttpMethod.POST.value,
                IdempotencyReservationRow.requested_route
                == f"/v1/organizations/{facts.organization_id.value}/humans/{target.id.value}/suspend",
                IdempotencyReservationRow.state == OperationReservationState.IN_PROGRESS,
                IdempotencyReservationRow.lookup_authority_family
                == OperationLookupAuthorityFamily.ORGANIZATION_ACTION_USE.value,
                IdempotencyReservationRow.lookup_action_id
                == OrganizationAction.SUSPEND_USERS.value,
            )
        )
        if original is None:
            raise ConflictError("Suspension requires its original in-progress reservation.")
        await self._save_transition(
            facts=facts,
            before=before,
            target=target,
            event_type="human_suspended",
            reason=command.reason.value,
            operation=operation,
        )
        now = await self._session.scalar(
            select(func.clock_timestamp(type_=DateTime(timezone=True)))
        )
        if now is None:
            raise DependencyUnavailableError("The database clock is unavailable.")
        obligation = HumanSuspensionObligationRow(
            id=suspension.id.value,
            job_id=JobId(uuid4()).value,
            operation_id=operation.operation_id.value,
            request_id=request_id.value,
            installation_id=facts.installation_id.value,
            organization_id=facts.organization_id.value,
            principal_id=target.id.value,
            initiator_principal_id=facts.actor.id.value,
            authority=suspension.authority.value,
            subject=suspension.subject.value,
            request_key=original.request_key,
            request_fingerprint=original.request_fingerprint,
            before_access_revision=facts.access_revision,
            access_revision=facts.access_revision + 1,
            admitted_at=now,
            queued_deadline=now + timedelta(hours=24),
            kratos_sessions=suspension.kratos_sessions,
            hydra_cli_grants=suspension.hydra_cli_grants,
            hydra_remembered_logins=suspension.hydra_remembered_logins,
        )
        self._session.add(obligation)
        await self._session.flush()
        self._session.add(
            DurableJobRow(
                id=obligation.job_id,
                operation_id=None,
                request_id=obligation.request_id,
                installation_id=obligation.installation_id,
                principal_id=None,
                principal_kind=None,
                organization_id=obligation.organization_id,
                project_id=None,
                action_id=None,
                payload_kind="human.suspension-cleanup",
                payload_version=1,
                payload=obligation.id.bytes,
                admitted_at=obligation.admitted_at,
                queued_deadline=obligation.queued_deadline,
                due_at=obligation.admitted_at,
                binding_kind="human_suspension",
                suspension_obligation_id=obligation.id,
            )
        )
        await self._session.flush()

    @override
    async def save_restoration(
        self,
        *,
        facts: HumanLifecycleFactsDTO,
        command: RestoreHumanCommand,
        target: Principal,
        version: HumanCredentialVersion,
        operation: NewOperationReservationDTO,
    ) -> None:
        before = self._checked_target(facts, target)
        if target.status is before.status:
            return
        identity = facts.target_identity
        prior_version = facts.target_version
        if identity is None or prior_version is None:
            raise DependencyUnavailableError("The original credential state is unavailable.")
        advanced = await self._session.scalar(
            update(HumanCredentialVersionRow)
            .where(
                HumanCredentialVersionRow.installation_id == facts.installation_id.value,
                HumanCredentialVersionRow.authority == identity.authority.value,
                HumanCredentialVersionRow.subject == identity.subject.value,
                HumanCredentialVersionRow.version == prior_version.value,
            )
            .values(version=version.value)
            .returning(HumanCredentialVersionRow.version)
        )
        if advanced is None:
            raise ConflictError("The original credential version changed.")
        await self._save_transition(
            facts=facts,
            before=before,
            target=target,
            event_type="human_restored",
            reason=command.security_review_reference.value,
            operation=operation,
        )

    @override
    async def save_result(
        self,
        *,
        facts: HumanLifecycleFactsDTO,
        result: HumanSuspensionResultDTO | HumanRestorationResultDTO,
    ) -> None:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Human lifecycle results require the active caller transaction.")
        changed = result.access_revision != facts.access_revision
        if isinstance(result, HumanSuspensionResultDTO):
            cleanup_id = UUID(result.cleanup_operation_id.value)
            before_version = credential_version = None
        else:
            if facts.target_version is None:
                raise DependencyUnavailableError("The original credential version is unavailable.")
            cleanup_id = (
                facts.current_suspension.id.value
                if changed and facts.current_suspension is not None
                else None
            )
            before_version = facts.target_version.value
            credential_version = result.credential_version.value
        self._session.add(
            HumanLifecycleOperationResultRow(
                operation_id=result.operation.operation_id.value,
                installation_id=facts.installation_id.value,
                organization_id=result.organization_id.value,
                principal_id=result.principal_id.value,
                actor_principal_id=result.actor_principal_id.value,
                action_id=OrganizationAction(facts.action_id.value),
                before_revision=facts.access_revision,
                access_revision=result.access_revision,
                changed=changed,
                cleanup_operation_id=cleanup_id,
                before_credential_version=before_version,
                credential_version=credential_version,
            )
        )
        await self._session.flush()

    def _checked_target(self, facts: HumanLifecycleFactsDTO, target: Principal) -> Principal:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Human lifecycle writes require the active caller transaction.")
        before = facts.target
        if (
            before is None
            or before.id != target.id
            or target.organization_id != facts.organization_id
        ):
            raise ConflictError("The checked human target changed.")
        return before

    async def _save_transition(
        self,
        *,
        facts: HumanLifecycleFactsDTO,
        before: Principal,
        target: Principal,
        event_type: str,
        reason: str,
        operation: NewOperationReservationDTO,
    ) -> None:
        changed = await self._session.scalar(
            update(PrincipalRow)
            .where(
                PrincipalRow.id == target.id.value,
                PrincipalRow.organization_id == facts.organization_id.value,
                PrincipalRow.kind == before.kind,
                PrincipalRow.status == before.status,
            )
            .values(status=target.status)
            .returning(PrincipalRow.id)
        )
        if changed is None:
            raise ConflictError("The checked human status changed.")
        revised = await self._session.scalar(
            update(OrganizationRow)
            .where(
                OrganizationRow.id == facts.organization_id.value,
                OrganizationRow.access_revision == facts.access_revision,
            )
            .values(access_revision=facts.access_revision + 1)
            .returning(OrganizationRow.id)
        )
        if revised is None:
            raise StaleRevisionError()
        self._session.add(
            AccessAuditEventRow(
                id=uuid4(),
                organization_id=facts.organization_id.value,
                actor_kind="human",
                actor_principal_id=facts.actor.id.value,
                event_type=event_type,
                target_kind="principal",
                target_id=target.id.value,
                affected_principal_id=target.id.value,
                action=facts.action_id.value,
                before_values={
                    "status": before.status.value,
                    "access_revision": facts.access_revision,
                },
                after_values={
                    "status": target.status.value,
                    "access_revision": facts.access_revision + 1,
                },
                reason=reason,
                correlation_id=operation.operation_id.value,
            )
        )
