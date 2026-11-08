from typing import override
from uuid import uuid4

from sqlalchemy import DateTime, String, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.application_key_creation_dto import (
    ApplicationKeyCreationDTO,
)
from inframeld_backend.access.application.protocols.application_key_issuance_writer import (
    ApplicationKeyIssuanceWriter,
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
from inframeld_backend.access.infrastructure.rows.application_key_issuance_result_row import (
    ApplicationKeyIssuanceResultRow,
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


class PostgresApplicationKeyIssuanceWriter(ApplicationKeyIssuanceWriter):
    """Persist issuance on the same transaction as its coordinated observations."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def create(
        self, *, key: ApplicationKeyCreationDTO, expected_project_revision: int
    ) -> None:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Key persistence requires the active caller transaction.")
        isolation = await self._session.scalar(
            select(func.current_setting("transaction_isolation", type_=String()))
        )
        if isolation != "read committed":
            raise RuntimeError("Key persistence requires READ COMMITTED isolation.")
        original, metadata = key.original, key.original.metadata
        RevisionValidation.require(expected_project_revision)
        RevisionValidation.require(original.access_revision)
        if (
            original.access_revision != expected_project_revision + 1
            or metadata.revoked_at is not None
            or metadata.expires_at <= metadata.created_at
            or len(key.verifier) != 32
            or not 1 <= len(metadata.allowed_adapters) <= 2
            or len(set(metadata.allowed_adapters)) != len(metadata.allowed_adapters)
            or (ApplicationKeyAdapter.HTTP in metadata.allowed_adapters)
            != (key.http_audience is not None)
            or (ApplicationKeyAdapter.MCP in metadata.allowed_adapters)
            != (key.mcp_audience is not None)
        ):
            raise RuntimeError("Key persistence changed its checked initial state.")
        route = f"/v1/projects/{metadata.project_id.value}/application-accounts/{metadata.application_principal_id.value}/keys"
        parent = IdempotencyReservationRow
        reservation = await self._session.scalar(
            select(parent.operation_id).where(
                parent.operation_id == original.operation_id.value,
                parent.organization_id == original.organization_id.value,
                parent.project_id == metadata.project_id.value,
                parent.principal_id == original.issuer_principal_id.value,
                parent.method == "POST",
                parent.requested_route == route,
                parent.state == OperationReservationState.IN_PROGRESS,
                parent.lookup_authority_family.is_(None),
                parent.lookup_action_id.is_(None),
            )
        )
        if reservation is None:
            raise ConflictError("Key issuance has no matching original reservation.")
        installed = await self._session.scalar(
            select(InstallationIdentityRow.installation_id).where(
                InstallationIdentityRow.singleton_key == 1
            )
        )
        if installed != original.installation_id.value:
            raise ConflictError("Key issuance changed its installation binding.")
        for principal, kind in (
            (original.issuer_principal_id, PrincipalKind.HUMAN),
            (metadata.application_principal_id, PrincipalKind.APPLICATION),
        ):
            eligible = await self._session.scalar(
                select(PrincipalRow.id)
                .join(ProjectMembershipRow, ProjectMembershipRow.principal_id == PrincipalRow.id)
                .where(
                    PrincipalRow.id == principal.value,
                    PrincipalRow.organization_id == original.organization_id.value,
                    PrincipalRow.kind == kind,
                    PrincipalRow.status == PrincipalStatus.ACTIVE,
                    ProjectMembershipRow.project_id == metadata.project_id.value,
                    ProjectMembershipRow.organization_id == original.organization_id.value,
                    ProjectMembershipRow.principal_kind == kind,
                )
            )
            if eligible is None:
                raise ConflictError("The checked issuance participant is no longer eligible.")
        account = await self._session.scalar(
            select(ApplicationAccountRow.principal_id).where(
                ApplicationAccountRow.principal_id == metadata.application_principal_id.value,
                ApplicationAccountRow.project_id == metadata.project_id.value,
                ApplicationAccountRow.organization_id == original.organization_id.value,
            )
        )
        if account is None:
            raise ConflictError("The checked application binding is no longer available.")
        count = await self._session.scalar(
            select(func.count())
            .select_from(ApplicationKeyRow)
            .where(
                ApplicationKeyRow.application_principal_id == account,
                ApplicationKeyRow.project_id == metadata.project_id.value,
                ApplicationKeyRow.organization_id == original.organization_id.value,
                ApplicationKeyRow.revoked_at.is_(None),
                ApplicationKeyRow.expires_at > func.clock_timestamp(type_=DateTime(timezone=True)),
            )
        )
        if count is None or count >= 2:
            raise ConflictError("The application already has two usable keys.")
        revision = await self._session.scalar(
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
        if revision is None:
            raise StaleRevisionError()

        await self._session.execute(
            insert(ApplicationKeyRow).values(
                key_id=metadata.key_id.value,
                organization_id=original.organization_id.value,
                project_id=metadata.project_id.value,
                application_principal_id=account,
                installation_id=original.installation_id.value,
                http_audience=key.http_audience.value if key.http_audience is not None else None,
                mcp_audience=key.mcp_audience.value if key.mcp_audience is not None else None,
                allowed_adapters=[adapter.value for adapter in metadata.allowed_adapters],
                verifier=key.verifier,
                created_at=metadata.created_at,
                expires_at=metadata.expires_at,
                issued_by_principal_id=original.issuer_principal_id.value,
                revoked_at=None,
            )
        )
        self._session.add(
            ApplicationKeyIssuanceResultRow(
                operation_id=original.operation_id.value,
                organization_id=original.organization_id.value,
                project_id=metadata.project_id.value,
                application_principal_id=account,
                installation_id=original.installation_id.value,
                issuer_principal_id=original.issuer_principal_id.value,
                key_id=metadata.key_id.value,
                allowed_adapters=[adapter.value for adapter in metadata.allowed_adapters],
                created_at=metadata.created_at,
                expires_at=metadata.expires_at,
                revoked_at=None,
                before_revision=expected_project_revision,
                access_revision=original.access_revision,
            )
        )
        self._session.add(
            AccessAuditEventRow(
                id=uuid4(),
                organization_id=original.organization_id.value,
                project_id=metadata.project_id.value,
                actor_kind="human",
                actor_principal_id=original.issuer_principal_id.value,
                affected_principal_id=account,
                event_type="application_key_issued",
                target_kind="application_key",
                target_id=metadata.key_id.value,
                action=ApplicationAccountAction.ISSUE_KEYS.value,
                before_values={"access_revision": expected_project_revision},
                after_values={
                    "key_id": str(metadata.key_id.value),
                    "allowed_adapters": [adapter.value for adapter in metadata.allowed_adapters],
                    "created_at": metadata.created_at.isoformat(),
                    "expires_at": metadata.expires_at.isoformat(),
                    "access_revision": original.access_revision,
                },
                correlation_id=original.operation_id.value,
            )
        )
        await self._session.flush()
