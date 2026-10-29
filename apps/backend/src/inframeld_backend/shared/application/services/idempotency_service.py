from datetime import datetime
from typing import override

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.protocols.authorized_operation_scope import (
    AuthorizedOperationScope,
)
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.dtos.accepted_async_operation_dto import (
    AcceptedAsyncOperationDTO,
)
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.dtos.new_operation_reservation_dto import (
    NewOperationReservationDTO,
)
from inframeld_backend.shared.application.dtos.operation_admission_context_dto import (
    OperationAdmissionContextDTO,
)
from inframeld_backend.shared.application.dtos.operation_reservation_request_dto import (
    OperationReservationRequestDTO,
)
from inframeld_backend.shared.application.dtos.operation_reservation_result_dto import (
    OperationReservationResultDTO,
)
from inframeld_backend.shared.application.dtos.recovery_required_operation_dto import (
    RecoveryRequiredOperationDTO,
)
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.enums.operation_reservation_state import (
    OperationReservationState,
)
from inframeld_backend.shared.application.errors.application_errors import (
    ConflictError,
    IdempotencyInProgressError,
)
from inframeld_backend.shared.application.protocols.operation_idempotency import (
    OperationIdempotency,
)
from inframeld_backend.shared.application.protocols.operation_reservation_writer import (
    OperationReservationWriter,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.application.value_objects.operation_lookup_authority import (
    OperationLookupAuthority,
)
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)


class IdempotencyService(OperationIdempotency):
    def __init__(self, reservations: OperationReservationWriter) -> None:
        self._reservations = reservations

    @override
    async def find_or_reserve[ProjectScope: ProjectId | None](
        self,
        *,
        context: OperationAdmissionContextDTO,
        access: AccessContextDTO,
        authorization: AuthorizedOperationScope[ProjectScope],
        fingerprint: RequestFingerprint,
        expected_replay_kind: OperationReplayKind,
        lookup_authority: OperationLookupAuthority | None = None,
    ) -> (
        NewOperationReservationDTO
        | CompletedSynchronousOperationDTO
        | AcceptedAsyncOperationDTO
        | RecoveryRequiredOperationDTO
    ):
        if lookup_authority is not None:
            lookup_authority.require_supported_scope(
                project_id=authorization.project_id,
                method=context.method,
                requested_route=context.requested_route,
            )

        stored = await self._reservations.reserve(
            OperationReservationRequestDTO(
                principal_id=access.actor_principal_id,
                organization_id=authorization.organization_id,
                project_id=authorization.project_id,
                method=context.method,
                requested_route=context.requested_route,
                key=context.key,
                fingerprint=fingerprint.value,
                lookup_authority=lookup_authority,
            )
        )
        if stored.created:
            if stored.state is not OperationReservationState.IN_PROGRESS:
                raise ConflictError("The operation is not newly reserved work.")
            self._require_incomplete_shape(stored)
            return NewOperationReservationDTO(stored.operation_id)

        if stored.state in (
            OperationReservationState.IN_PROGRESS,
            OperationReservationState.RECOVERY_REQUIRED,
        ):
            self._require_incomplete_shape(stored)
            if stored.state is OperationReservationState.IN_PROGRESS:
                raise IdempotencyInProgressError(
                    operation_id=stored.operation_id,
                    retry_after_seconds=3,
                )
            return RecoveryRequiredOperationDTO(stored.operation_id)

        kind = stored.replay_kind
        if (
            stored.state is not OperationReservationState.REPLAYABLE
            or kind is None
            or kind is not expected_replay_kind
        ):
            raise ConflictError("The saved operation has an unexpected replay outcome.")
        return self._completed(
            operation_id=stored.operation_id,
            created=False,
            replay_kind=kind,
            expires_at=stored.expires_at,
        )

    @override
    async def record_completed_result(
        self,
        operation: NewOperationReservationDTO,
        *,
        replay_kind: OperationReplayKind,
    ) -> CompletedSynchronousOperationDTO | AcceptedAsyncOperationDTO:
        reserved = self._require_new_operation(operation)
        expiry = await self._reservations.mark_replayable(reserved.operation_id, replay_kind)
        return self._completed(
            operation_id=reserved.operation_id,
            created=True,
            replay_kind=replay_kind,
            expires_at=expiry,
        )

    @staticmethod
    def _require_new_operation(operation: object) -> NewOperationReservationDTO:
        if not isinstance(operation, NewOperationReservationDTO):
            raise ConflictError("The operation is not newly reserved work.")
        return operation

    @staticmethod
    def _require_incomplete_shape(stored: OperationReservationResultDTO) -> None:
        if stored.replay_kind is not None or stored.expires_at is not None:
            raise ConflictError("An unfinished operation has unexpected replay metadata.")

    @staticmethod
    def _completed(
        *,
        operation_id: OperationId,
        created: bool,
        replay_kind: OperationReplayKind,
        expires_at: datetime | None,
    ) -> CompletedSynchronousOperationDTO | AcceptedAsyncOperationDTO:
        if replay_kind is OperationReplayKind.ASYNC_JOB:
            return AcceptedAsyncOperationDTO(operation_id, created, expires_at)
        if (
            replay_kind is OperationReplayKind.SAFE_RESULT
            or replay_kind is OperationReplayKind.ISSUED_SECRET
            or replay_kind is OperationReplayKind.ANSWER_RECEIPT
        ):
            if expires_at is None:
                raise ConflictError("The completed operation has no replay deadline.")
            return CompletedSynchronousOperationDTO(
                operation_id=operation_id,
                created=created,
                replay_kind=replay_kind,
                expires_at=expires_at,
            )
        raise ConflictError("The saved operation has an unexpected replay outcome.")
