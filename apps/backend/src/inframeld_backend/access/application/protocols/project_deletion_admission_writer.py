from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.commands.delete_project_command import (
    DeleteProjectCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_action_authorization_dto import (
    ProjectActionAuthorizationDTO,
)
from inframeld_backend.access.domain.value_objects.project_deletion_obligation_id import (
    ProjectDeletionObligationId,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.dtos.new_operation_reservation_dto import (
    NewOperationReservationDTO,
)
from inframeld_backend.shared.application.value_objects.job_id import JobId
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)
from inframeld_backend.shared.application.value_objects.request_id import RequestId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


class ProjectDeletionAdmissionWriter(Protocol):
    """Persist complete deletion admission without owning the caller's transaction."""

    @abstractmethod
    async def admit(
        self,
        *,
        installation_id: InstallationId,
        scope: ProjectActionAuthorizationDTO,
        access: AccessContextDTO,
        command: DeleteProjectCommand,
        context: IdempotencyContextDTO,
        request_id: RequestId,
        reservation: NewOperationReservationDTO,
        fingerprint: RequestFingerprint,
        obligation_id: ProjectDeletionObligationId,
        job_id: JobId,
    ) -> None:
        """Save the block, one revision, audit, immutable original and durable capacity together.

        Require the caller's active READ COMMITTED transaction and already-held
        Organization/Project coordination. Recheck exact scope, ACTIVE status
        and reviewed revision before conditional persistence. Bind the genuine
        obligation, queued shutdown job and nonexpiring physical-pending parent
        to these original identities and request meaning. This is not ordinary
        JobAdmissionService authority or a caller-supplied admission certificate.

        Capacity denial and all failures propagate for complete rollback.
        Never commit, reset the original deadline, swallow cancellation or
        dispatch work here. No shutdown checkpoint or erasure success is implied.
        """
        ...
