import asyncio
from hmac import compare_digest
from typing import override

from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.project_action import ProjectAction
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.shared.application.dtos.deletion_status_binding_dto import (
    DeletionStatusBindingDTO,
)
from inframeld_backend.shared.application.dtos.new_operation_reservation_dto import (
    NewOperationReservationDTO,
)
from inframeld_backend.shared.application.dtos.operation_reservation_request_dto import (
    OperationReservationRequestDTO,
)
from inframeld_backend.shared.application.enums.operation_lookup_authority_family import (
    OperationLookupAuthorityFamily,
)
from inframeld_backend.shared.application.enums.operation_reservation_state import (
    OperationReservationState,
)
from inframeld_backend.shared.application.errors.application_errors import (
    ConflictError,
    DependencyUnavailableError,
)
from inframeld_backend.shared.application.protocols.deletion_status_binding_writer import (
    DeletionStatusBindingWriter,
)
from inframeld_backend.shared.application.value_objects.deletion_status_retention_profile import (
    DeletionStatusRetentionProfile,
)
from inframeld_backend.shared.application.value_objects.request_id import RequestId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.infrastructure.mappers.postgres_deletion_status_mapper import (
    PostgresDeletionStatusMapper,
)
from inframeld_backend.shared.infrastructure.rows.deletion_status_binding_row import (
    DeletionStatusBindingRow,
)
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)
from inframeld_backend.shared.infrastructure.rows.installation_identity_row import (
    InstallationIdentityRow,
)


class PostgresDeletionStatusBindingWriter(DeletionStatusBindingWriter):
    """Capture original correlation without committing or establishing deletion admission."""

    def __init__(self, session: AsyncSession, profile: DeletionStatusRetentionProfile) -> None:
        self._session = session
        self._profile = profile

    @override
    async def bind_original_request(
        self,
        *,
        reservation: NewOperationReservationDTO,
        request_id: RequestId,
        expected_installation_id: InstallationId,
        expected_request: OperationReservationRequestDTO,
    ) -> DeletionStatusBindingDTO:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Deletion status binding requires an active caller transaction.")
        try:
            async with asyncio.timeout(5):
                return await self._bind(
                    reservation=reservation,
                    request_id=request_id,
                    expected_installation_id=expected_installation_id,
                    expected_request=expected_request,
                )
        except (TimeoutError, OperationalError, SqlAlchemyTimeoutError, LookupError):
            raise DependencyUnavailableError() from None

    async def _bind(
        self,
        *,
        reservation: NewOperationReservationDTO,
        request_id: RequestId,
        expected_installation_id: InstallationId,
        expected_request: OperationReservationRequestDTO,
    ) -> DeletionStatusBindingDTO:
        # Existing reservation coordination serializes first bindings. Re-read
        # retained history after waiting, so the first committed attribution wins.
        """Retain the original deletion lookup binding without overwriting another request meaning."""
        native = await self._session.scalar(
            select(IdempotencyReservationRow)
            .where(IdempotencyReservationRow.operation_id == reservation.operation_id.value)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        retained = await self._session.scalar(
            select(DeletionStatusBindingRow)
            .where(DeletionStatusBindingRow.operation_id == reservation.operation_id.value)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        installed = await self._session.scalar(
            select(InstallationIdentityRow.installation_id).where(
                InstallationIdentityRow.singleton_key == 1
            )
        )
        if installed is None:
            raise DependencyUnavailableError("The installation identity is not available.")
        if installed != expected_installation_id.value:
            raise ConflictError()

        request = expected_request
        authority = request.lookup_authority
        if (
            request.project_id is None
            or authority is None
            or (
                authority.family is not OperationLookupAuthorityFamily.PROJECT_ACTION_USE
                or authority.action_id.value != ProjectAction.DELETE_PROJECT.value
            )
        ):
            raise ConflictError()
        if native is not None:
            self._require_native_meaning(native, request)

        if retained is not None:
            self._require_retained_meaning(retained, request_id, expected_installation_id, request)
            return self._to_binding(retained)
        if native is None or (
            native.state is not OperationReservationState.IN_PROGRESS
            or native.replay_kind is not None
            or native.expires_at is not None
        ):
            raise ConflictError()

        # The locked native reservation retains its real Principal/Project foreign
        # keys until commit. Current authorization remains the owning workflow's job.
        principal = await self._session.scalar(
            select(PrincipalRow.id).where(
                PrincipalRow.id == request.principal_id.value,
                PrincipalRow.organization_id == request.organization_id.value,
                PrincipalRow.kind == PrincipalKind.HUMAN,
            )
        )
        project = await self._session.scalar(
            select(ProjectRow.id).where(
                ProjectRow.id == request.project_id.value,
                ProjectRow.organization_id == request.organization_id.value,
            )
        )
        if principal is None or project is None:
            raise ConflictError()

        retained = DeletionStatusBindingRow(
            operation_id=native.operation_id,
            request_id=request_id.value,
            installation_id=installed,
            organization_id=native.organization_id,
            project_id=project,
            initiator_principal_id=principal,
            method=native.method,
            requested_route=native.requested_route,
            request_key=native.request_key,
            request_fingerprint=native.request_fingerprint,
            authority_family=authority.family.value,
            action_id=authority.action_id.value,
            retention_days=self._profile.days,
            retention_policy_version=self._profile.policy_version,
        )
        self._session.add(retained)
        await self._session.flush()
        await self._session.refresh(retained)
        return self._to_binding(retained)

    @staticmethod
    def _require_native_meaning(
        row: IdempotencyReservationRow, request: OperationReservationRequestDTO
    ) -> None:
        """Check the request against the supported native deletion operation."""
        authority = request.lookup_authority
        if (
            authority is None
            or request.project_id is None
            or (
                row.principal_id != request.principal_id.value
                or row.organization_id != request.organization_id.value
                or row.project_id != request.project_id.value
                or row.method != request.method
                or row.requested_route != request.requested_route
                or row.request_key != request.key.value
                or not compare_digest(row.request_fingerprint, request.fingerprint)
                or row.lookup_authority_family != authority.family.value
                or row.lookup_action_id != authority.action_id.value
            )
        ):
            raise ConflictError()

    @staticmethod
    def _require_retained_meaning(
        row: DeletionStatusBindingRow,
        request_id: RequestId,
        installation_id: InstallationId,
        request: OperationReservationRequestDTO,
    ) -> None:
        """Reject a retained lookup binding that changes the original deletion request."""
        authority = request.lookup_authority
        if (
            authority is None
            or request.project_id is None
            or (
                row.request_id != request_id.value
                or row.installation_id != installation_id.value
                or row.initiator_principal_id != request.principal_id.value
                or row.organization_id != request.organization_id.value
                or row.project_id != request.project_id.value
                or row.method != request.method
                or row.requested_route != request.requested_route
                or row.request_key != request.key.value
                or not compare_digest(row.request_fingerprint, request.fingerprint)
                or row.authority_family != authority.family.value
                or row.action_id != authority.action_id.value
            )
        ):
            raise ConflictError()

    @staticmethod
    def _to_binding(row: DeletionStatusBindingRow) -> DeletionStatusBindingDTO:
        try:
            return PostgresDeletionStatusMapper.to_binding(row)
        except (TypeError, ValueError, LookupError):
            raise DependencyUnavailableError() from None
