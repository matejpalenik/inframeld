from typing import override

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.protocols.operation_lookup_authorizer import (
    OperationLookupAuthorizer,
)
from inframeld_backend.shared.application.dtos.accepted_async_operation_dto import (
    AcceptedAsyncOperationDTO,
)
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.dtos.in_progress_operation_dto import (
    InProgressOperationDTO,
)
from inframeld_backend.shared.application.dtos.recovery_required_operation_dto import (
    RecoveryRequiredOperationDTO,
)
from inframeld_backend.shared.application.dtos.unresolved_operation_dto import (
    UnresolvedOperationDTO,
)
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.enums.operation_reservation_state import (
    OperationReservationState,
)
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.application.protocols.operation_lookup_reader import (
    OperationLookupReader,
)
from inframeld_backend.shared.application.protocols.original_operation_lookup import (
    OriginalOperationLookup,
)
from inframeld_backend.shared.application.queries.lookup_original_operation_query import (
    LookupOriginalOperationQuery,
)


class OriginalOperationLookupService(OriginalOperationLookup):
    def __init__(
        self, authorizer: OperationLookupAuthorizer, reader: OperationLookupReader
    ) -> None:
        self._authorizer = authorizer
        self._reader = reader

    @override
    async def lookup(
        self, *, access: AccessContextDTO, query: LookupOriginalOperationQuery
    ) -> (
        CompletedSynchronousOperationDTO
        | AcceptedAsyncOperationDTO
        | InProgressOperationDTO
        | RecoveryRequiredOperationDTO
        | UnresolvedOperationDTO
    ):
        query.expected_authority.require_supported_scope(
            project_id=query.project_id, method=query.method, requested_route=query.requested_route
        )
        authorized = await self._authorizer.require_authorization(access=access, request=query)
        if (authorized.organization_id, authorized.project_id) != (
            query.organization_id,
            query.project_id,
        ):
            raise RuntimeError("Lookup authorization returned a different scope.")

        stored = await self._reader.read(principal_id=access.actor_principal_id, query=query)
        if stored is None:
            return UnresolvedOperationDTO()
        if stored.created:
            raise DependencyUnavailableError()

        if stored.state in (
            OperationReservationState.IN_PROGRESS,
            OperationReservationState.RECOVERY_REQUIRED,
        ):
            if stored.replay_kind is not None or stored.expires_at is not None:
                raise DependencyUnavailableError()
            if stored.state is OperationReservationState.IN_PROGRESS:
                return InProgressOperationDTO(stored.operation_id)
            return RecoveryRequiredOperationDTO(stored.operation_id)

        if stored.state is not OperationReservationState.REPLAYABLE:
            raise DependencyUnavailableError()
        if stored.replay_kind is OperationReplayKind.ASYNC_JOB:
            return AcceptedAsyncOperationDTO(stored.operation_id, False, stored.expires_at)
        if (
            stored.replay_kind is OperationReplayKind.SAFE_RESULT
            or stored.replay_kind is OperationReplayKind.ISSUED_SECRET
            or stored.replay_kind is OperationReplayKind.ANSWER_RECEIPT
        ) and stored.expires_at is not None:
            return CompletedSynchronousOperationDTO(
                stored.operation_id, False, stored.replay_kind, stored.expires_at
            )
        raise DependencyUnavailableError()
