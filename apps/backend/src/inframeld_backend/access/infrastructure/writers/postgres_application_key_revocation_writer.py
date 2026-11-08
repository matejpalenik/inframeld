from typing import override
from uuid import uuid4

from sqlalchemy import DateTime, String, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.application_key_revocation_record_dto import (
    ApplicationKeyRevocationRecordDTO,
)
from inframeld_backend.access.application.protocols.application_key_revocation_writer import (
    ApplicationKeyRevocationWriter,
)
from inframeld_backend.access.domain.enums.application_account_action import (
    ApplicationAccountAction,
)
from inframeld_backend.access.domain.enums.application_key_adapter import ApplicationKeyAdapter
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.access.infrastructure.rows.application_account_row import (
    ApplicationAccountRow,
)
from inframeld_backend.access.infrastructure.rows.application_key_revocation_result_row import (
    ApplicationKeyRevocationResultRow,
)
from inframeld_backend.access.infrastructure.rows.application_key_row import ApplicationKeyRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_membership_row import ProjectMembershipRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.shared.application.enums.operation_reservation_state import (
    OperationReservationState,
)
from inframeld_backend.shared.application.errors.application_errors import (
    ConflictError,
    StaleRevisionError,
)
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)
from inframeld_backend.shared.infrastructure.rows.installation_identity_row import (
    InstallationIdentityRow,
)


class PostgresApplicationKeyRevocationWriter(ApplicationKeyRevocationWriter):
    """Save the checked transition and safe receipt while retaining the caller's guards."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def save(
        self, *, original: ApplicationKeyRevocationRecordDTO, expected_project_revision: int
    ) -> None:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Key persistence requires the active caller transaction.")
        isolation = await self._session.scalar(
            select(func.current_setting("transaction_isolation", type_=String()))
        )
        if isolation != "read committed":
            raise RuntimeError("Key persistence requires READ COMMITTED isolation.")
        metadata = original.metadata
        RevisionValidation.require(expected_project_revision)
        RevisionValidation.require(original.access_revision)
        if (
            metadata.revoked_at is None
            or metadata.expires_at <= metadata.created_at
            or metadata.revoked_at < metadata.created_at
            or not 1 <= len(metadata.allowed_adapters) <= 2
            or len(set(metadata.allowed_adapters)) != len(metadata.allowed_adapters)
        ):
            raise RuntimeError("Key persistence changed its checked revocation metadata.")

        route = (
            f"/v1/projects/{metadata.project_id.value}/application-accounts/"
            f"{metadata.application_principal_id.value}/keys/{metadata.key_id.value}/revoke"
        )
        parent = IdempotencyReservationRow
        reservation = await self._session.scalar(
            select(parent.operation_id).where(
                parent.operation_id == original.operation_id.value,
                parent.organization_id == original.organization_id.value,
                parent.project_id == metadata.project_id.value,
                parent.principal_id == original.actor_principal_id.value,
                parent.method == "POST",
                parent.requested_route == route,
                parent.state == OperationReservationState.IN_PROGRESS,
                parent.lookup_authority_family.is_(None),
                parent.lookup_action_id.is_(None),
            )
        )
        if reservation is None:
            raise ConflictError("Key revocation has no matching original reservation.")
        installed = await self._session.scalar(
            select(InstallationIdentityRow.installation_id).where(
                InstallationIdentityRow.singleton_key == 1
            )
        )
        if installed != original.installation_id.value:
            raise ConflictError("Key revocation changed its installation binding.")
        actor = await self._session.scalar(
            select(PrincipalRow.id)
            .join(ProjectMembershipRow, ProjectMembershipRow.principal_id == PrincipalRow.id)
            .where(
                PrincipalRow.id == original.actor_principal_id.value,
                PrincipalRow.organization_id == original.organization_id.value,
                PrincipalRow.kind == PrincipalKind.HUMAN,
                PrincipalRow.status == PrincipalStatus.ACTIVE,
                ProjectMembershipRow.project_id == metadata.project_id.value,
                ProjectMembershipRow.organization_id == original.organization_id.value,
                ProjectMembershipRow.principal_kind == PrincipalKind.HUMAN,
            )
        )
        account = await self._session.scalar(
            select(ApplicationAccountRow.principal_id)
            .join(PrincipalRow, PrincipalRow.id == ApplicationAccountRow.principal_id)
            .where(
                ApplicationAccountRow.principal_id == metadata.application_principal_id.value,
                ApplicationAccountRow.organization_id == original.organization_id.value,
                ApplicationAccountRow.project_id == metadata.project_id.value,
                ApplicationAccountRow.principal_kind == PrincipalKind.APPLICATION,
                PrincipalRow.organization_id == original.organization_id.value,
                PrincipalRow.kind == PrincipalKind.APPLICATION,
            )
        )
        if actor is None or account is None:
            raise ConflictError("The checked revocation participant or account is unavailable.")
        revision = await self._session.scalar(
            select(ProjectRow.access_revision).where(
                ProjectRow.id == metadata.project_id.value,
                ProjectRow.organization_id == original.organization_id.value,
                ProjectRow.status == ProjectStatus.ACTIVE,
            )
        )
        if revision != expected_project_revision:
            raise StaleRevisionError()

        key = ApplicationKeyRow
        stored = (
            (
                await self._session.execute(
                    select(key.allowed_adapters, key.created_at, key.expires_at, key.revoked_at)
                    .where(
                        key.key_id == metadata.key_id.value,
                        key.organization_id == original.organization_id.value,
                        key.project_id == metadata.project_id.value,
                        key.application_principal_id == account,
                        key.installation_id == original.installation_id.value,
                    )
                    .with_for_update()
                )
            )
            .tuples()
            .one_or_none()
        )
        if stored is None:
            raise ConflictError("The checked key binding is no longer available.")
        adapters, created_at, expires_at, revoked_at = stored
        changed = revoked_at is None
        now = await self._session.scalar(
            select(func.clock_timestamp(type_=DateTime(timezone=True)))
        )
        if (
            tuple(ApplicationKeyAdapter(value) for value in adapters) != metadata.allowed_adapters
            or created_at != metadata.created_at
            or expires_at != metadata.expires_at
            or original.access_revision != expected_project_revision + int(changed)
            or (not changed and metadata.revoked_at != revoked_at)
            or now is None
            or (changed and metadata.revoked_at > now)
        ):
            raise RuntimeError("Key persistence changed its checked original outcome.")

        if changed:
            advanced = await self._session.scalar(
                update(ProjectRow)
                .where(
                    ProjectRow.id == metadata.project_id.value,
                    ProjectRow.organization_id == original.organization_id.value,
                    ProjectRow.status == ProjectStatus.ACTIVE,
                    ProjectRow.access_revision == expected_project_revision,
                    ProjectRow.access_revision < RevisionValidation.MAX_VALUE,
                )
                .values(access_revision=original.access_revision)
                .returning(ProjectRow.access_revision)
            )
            if advanced is None:
                raise StaleRevisionError()
            revoked = await self._session.scalar(
                update(ApplicationKeyRow)
                .where(
                    ApplicationKeyRow.key_id == metadata.key_id.value,
                    ApplicationKeyRow.organization_id == original.organization_id.value,
                    ApplicationKeyRow.project_id == metadata.project_id.value,
                    ApplicationKeyRow.application_principal_id == account,
                    ApplicationKeyRow.installation_id == original.installation_id.value,
                    ApplicationKeyRow.revoked_at.is_(None),
                )
                .values(revoked_at=metadata.revoked_at)
                .returning(ApplicationKeyRow.key_id)
            )
            if revoked is None:
                raise ConflictError("The checked key revocation changed concurrently.")
            self._session.add(
                AccessAuditEventRow(
                    id=uuid4(),
                    organization_id=original.organization_id.value,
                    project_id=metadata.project_id.value,
                    actor_kind="human",
                    actor_principal_id=original.actor_principal_id.value,
                    affected_principal_id=account,
                    event_type="application_key_revoked",
                    target_kind="application_key",
                    target_id=metadata.key_id.value,
                    action=ApplicationAccountAction.REVOKE_KEYS.value,
                    before_values={
                        "revoked_at": None,
                        "access_revision": expected_project_revision,
                    },
                    after_values={
                        "revoked_at": metadata.revoked_at.isoformat(),
                        "access_revision": original.access_revision,
                    },
                    correlation_id=original.operation_id.value,
                )
            )
        self._session.add(
            ApplicationKeyRevocationResultRow(
                operation_id=original.operation_id.value,
                organization_id=original.organization_id.value,
                project_id=metadata.project_id.value,
                application_principal_id=account,
                installation_id=original.installation_id.value,
                actor_principal_id=original.actor_principal_id.value,
                key_id=metadata.key_id.value,
                allowed_adapters=[adapter.value for adapter in metadata.allowed_adapters],
                created_at=metadata.created_at,
                expires_at=metadata.expires_at,
                revoked_at=metadata.revoked_at,
                before_revision=expected_project_revision,
                access_revision=original.access_revision,
            )
        )
        await self._session.flush()
