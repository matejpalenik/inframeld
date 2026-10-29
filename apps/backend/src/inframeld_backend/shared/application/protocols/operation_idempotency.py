from abc import abstractmethod
from typing import Protocol

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
from inframeld_backend.shared.application.dtos.recovery_required_operation_dto import (
    RecoveryRequiredOperationDTO,
)
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.value_objects.operation_lookup_authority import (
    OperationLookupAuthority,
)
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)


class OperationIdempotency(Protocol):
    """Recognize retries so a workflow can avoid performing the same work twice.

    Reservations associate a retry key and request meaning with an operation.
    The owning workflow authorizes each attempt and owns the transaction. This
    capability manages operation metadata, not permissions or business results.
    """

    @abstractmethod
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
        """Reserve new work or identify a matching retained operation.

        Authorize current access and match the requested scope before calling,
        including on retries. Copy the supplied values unchanged into the
        reservation request. Never commit or execute the business change here.
        An expired saved replay may be replaced by a new reservation.

        Args:
            context: Retry key, HTTP method and canonical route identifying the
                logical request. Reuse them when retrying the same operation.
            access: Authenticated caller supplying the reservation's principal ID.
            authorization: Current checked organization and optional project.
                These fields and interface conformance alone prove no authority.
            fingerprint: Digest already computed from the request's meaning.
            expected_replay_kind: Saved outcome category this workflow can handle.

        Returns:
            NewOperationReservationDTO for work that may execute now.
            CompletedSynchronousOperationDTO for a saved synchronous outcome.
            AcceptedAsyncOperationDTO for accepted background work, which may
            still be running. RecoveryRequiredOperationDTO for original work
            that must not restart automatically. Existing outcomes preserve the
            original operation ID and any recorded expiry. Synchronous expiry
            is required, while asynchronous expiry may be absent.

        Raises:
            IdempotencyKeyReusedError: The retained key has different request meaning.
            IdempotencyInProgressError: Original work is unfinished. The error
                includes its operation ID and three-second retry advice.
            ConflictError: Stored metadata is malformed or has an incompatible
                replay kind.
        """
        ...

    @abstractmethod
    async def record_completed_result(
        self,
        operation: NewOperationReservationDTO,
        *,
        replay_kind: OperationReplayKind,
    ) -> CompletedSynchronousOperationDTO | AcceptedAsyncOperationDTO:
        """Save retry metadata after newly reserved work's effects have been saved.

        Use the same transaction as those effects and leave commit to the owner.
        For ASYNC_JOB, save admission of the job, not completion of its execution.
        Persistence failures propagate so the owner can roll back both steps.

        Args:
            operation: New reservation obtained for this work in this transaction.
            replay_kind: Outcome category the workflow has made safe to replay.

        Returns:
            Synchronous completion with required expiry, or asynchronous acceptance
            with optional expiry. Both retain the operation ID and set `created`
            to true. Later replays set it to false. Expiry limits the saved retry
            result, not the lifetime of a permission or other business resource.

        Raises:
            ConflictError: The operation is not newly reserved or can no longer
                be completed, the replay kind is unsupported, or synchronous
                completion has no stored expiry.
        """
        ...
