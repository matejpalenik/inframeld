from datetime import datetime
from typing import override

from sqlalchemy import exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.first_administrator_bootstrap_facts_dto import (
    FirstAdministratorBootstrapFactsDTO,
)
from inframeld_backend.access.application.dtos.first_administrator_bootstrap_receipt_dto import (
    FirstAdministratorBootstrapReceiptDTO,
)
from inframeld_backend.access.application.dtos.first_administrator_bootstrap_result_dto import (
    FirstAdministratorBootstrapResultDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.enums.first_administrator_bootstrap_error_code import (
    FirstAdministratorBootstrapErrorCode as Code,
)
from inframeld_backend.access.application.errors.first_administrator_bootstrap_error import (
    FirstAdministratorBootstrapError,
)
from inframeld_backend.access.application.protocols.first_administrator_bootstrap_facts_reader import (
    FirstAdministratorBootstrapFactsReader,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.infrastructure.mappers.postgres_human_credential_state_mapper import (
    PostgresHumanCredentialStateMapper,
)
from inframeld_backend.access.infrastructure.readers.human_credential_state_queries import (
    HumanCredentialStateQueries,
)
from inframeld_backend.access.infrastructure.resources.postgres_identity_coordinator import (
    PostgresIdentityCoordinator,
)
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.access.infrastructure.rows.first_administrator_bootstrap_receipt_row import (
    FirstAdministratorBootstrapReceiptRow,
)
from inframeld_backend.access.infrastructure.rows.host_maintenance_receipt_row import (
    HostMaintenanceReceiptRow,
)
from inframeld_backend.access.infrastructure.rows.human_identity_link_row import (
    HumanIdentityLinkRow,
)
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.infrastructure.rows.artifact_attempt_row import ArtifactAttemptRow
from inframeld_backend.shared.infrastructure.rows.artifact_cleanup_obligation_row import (
    ArtifactCleanupObligationRow,
)
from inframeld_backend.shared.infrastructure.rows.artifact_storage_capacity_row import (
    ArtifactStorageCapacityRow,
)
from inframeld_backend.shared.infrastructure.rows.deletion_status_observation_row import (
    DeletionStatusObservationRow,
)
from inframeld_backend.shared.infrastructure.rows.durable_job_row import DurableJobRow
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)
from inframeld_backend.shared.infrastructure.rows.installation_identity_row import (
    InstallationIdentityRow,
)


class PostgresFirstAdministratorBootstrapFactsReader(FirstAdministratorBootstrapFactsReader):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _require_transaction(self) -> None:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Bootstrap facts require an active caller transaction.")

    @override
    async def read(
        self, *, installation_id: InstallationId, identity: VerifiedHumanIdentityDTO
    ) -> FirstAdministratorBootstrapFactsDTO:
        self._require_transaction()
        installed = await self._session.scalar(
            select(InstallationIdentityRow.installation_id).where(
                InstallationIdentityRow.singleton_key == 1
            )
        )
        if installed is None:
            raise FirstAdministratorBootstrapError(Code.DEPENDENCY_UNAVAILABLE)
        if installed != installation_id.value:
            raise FirstAdministratorBootstrapError(Code.INSTALLATION_MISMATCH)

        await PostgresIdentityCoordinator(self._session).acquire(
            installation_id=installation_id, identity=identity
        )
        locked = await self._session.scalar(
            select(InstallationIdentityRow.installation_id)
            .where(InstallationIdentityRow.singleton_key == 1)
            .with_for_update()
        )
        if locked is None:
            raise FirstAdministratorBootstrapError(Code.DEPENDENCY_UNAVAILABLE)
        if locked != installed:
            raise RuntimeError("The installation identity changed while waiting for its turn.")

        link = select(HumanIdentityLinkRow).where(
            HumanIdentityLinkRow.authority == identity.authority.value,
            HumanIdentityLinkRow.subject == identity.subject.value,
        )
        linked = await self._session.scalar(
            link.execution_options(populate_existing=True, autoflush=False)
        )
        if linked is not None:
            organization = await self._session.scalar(
                select(OrganizationRow.id)
                .where(OrganizationRow.id == linked.organization_id)
                .with_for_update()
            )
            if organization is None:
                raise FirstAdministratorBootstrapError(Code.IDENTITY_INELIGIBLE)

        # These are fresh statements after any identity, installation or Org wait.
        linked = await self._session.scalar(
            link.execution_options(populate_existing=True, autoflush=False)
        )
        principal = None
        if linked is not None:
            row = await self._session.scalar(
                select(PrincipalRow)
                .where(
                    PrincipalRow.id == linked.principal_id,
                    PrincipalRow.organization_id == linked.organization_id,
                    PrincipalRow.kind == linked.principal_kind,
                )
                .execution_options(populate_existing=True, autoflush=False)
            )
            if row is None:
                raise RuntimeError("The current identity link has no coherent local principal.")
            principal = Principal(
                PrincipalId(row.id), OrganizationId(row.organization_id), row.kind, row.status
            )
        state = await self._session.execute(HumanCredentialStateQueries.for_identity(identity))
        credential = PostgresHumanCredentialStateMapper.to_state(
            identity, state.tuples().one_or_none()
        )
        business = await self._session.scalar(
            select(
                or_(
                    exists().where(OrganizationRow.id.is_not(None)),
                    exists().where(PrincipalRow.id.is_not(None)),
                    exists().where(HumanIdentityLinkRow.subject.is_not(None)),
                    # Retained business roots can outlive their Organization.
                    # Credential generations and recovery records are allowed.
                    exists().where(AccessAuditEventRow.id.is_not(None)),
                    exists().where(DurableJobRow.id.is_not(None)),
                    exists().where(IdempotencyReservationRow.operation_id.is_not(None)),
                    exists().where(DeletionStatusObservationRow.operation_id.is_not(None)),
                    exists().where(ArtifactAttemptRow.id.is_not(None)),
                    exists().where(ArtifactCleanupObligationRow.id.is_not(None)),
                    exists().where(ArtifactStorageCapacityRow.installation_id.is_not(None)),
                )
            )
        )
        claimed = await self._session.scalar(
            select(
                or_(
                    exists().where(
                        FirstAdministratorBootstrapReceiptRow.installation_id == installed
                    ),
                    exists().where(
                        HostMaintenanceReceiptRow.installation_id == installed,
                        HostMaintenanceReceiptRow.mode == "bootstrap-first-administrator",
                    ),
                )
            )
        )
        observed = await self._session.scalar(
            select(func.clock_timestamp(type_=OrganizationRow.created_at.type))
        )
        if (
            not isinstance(business, bool)
            or not isinstance(claimed, bool)
            or not isinstance(observed, datetime)
        ):
            raise FirstAdministratorBootstrapError(Code.DEPENDENCY_UNAVAILABLE)
        return FirstAdministratorBootstrapFactsDTO(
            installation_id, identity, credential, principal, business, claimed, observed
        )

    @override
    async def receipt(
        self, *, installation_id: InstallationId, operation_id: OperationId
    ) -> FirstAdministratorBootstrapReceiptDTO | None:
        self._require_transaction()
        parent = await self._session.get(
            HostMaintenanceReceiptRow,
            (installation_id.value, operation_id.value),
            populate_existing=True,
        )
        if parent is None:
            return None
        if parent.mode != "bootstrap-first-administrator":
            raise FirstAdministratorBootstrapError(Code.KEY_REUSED)
        row = await self._session.get(
            FirstAdministratorBootstrapReceiptRow, installation_id.value, populate_existing=True
        )
        if (
            row is None
            or row.operator_request_id != operation_id.value
            or row.organization_name != "Inframeld"
            or parent.outcome != "bootstrapped"
            or any(
                value is not None
                for value in (
                    parent.recovery_operation_id,
                    parent.released,
                    parent.run_id,
                    parent.deadline,
                )
            )
        ):
            raise RuntimeError("The stored first-administrator claim has no valid typed result.")
        return FirstAdministratorBootstrapReceiptDTO(
            RequestFingerprint(row.request_fingerprint),
            VerifiedHumanIdentityDTO(
                IdentityAuthority(parent.authority), IdentitySubject(parent.subject)
            ),
            row.expected_identity_id,
            parent.operator_label,
            parent.reason,
            row.before_revision,
            parent.authorized_at,
            FirstAdministratorBootstrapResultDTO(
                operation_id,
                installation_id,
                OrganizationId(row.organization_id),
                PrincipalId(row.recipient_id),
                row.after_revision,
            ),
        )
