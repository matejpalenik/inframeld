from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.commands.assign_project_use_only_grant_command import (
    AssignProjectUseOnlyGrantCommand,
)
from inframeld_backend.access.application.commands.remove_project_action_grant_command import (
    RemoveProjectActionGrantCommand,
)
from inframeld_backend.access.application.commands.set_project_action_grant_command import (
    SetProjectActionGrantCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_action_grant_change_result_dto import (
    ProjectActionGrantChangeResultDTO,
)
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.dtos.operation_admission_context_dto import (
    OperationAdmissionContextDTO,
)


class ProjectGrantChanger(Protocol):
    """Give a human permission to perform a named action in one project.

    The caller requests the change. The recipient is the person receiving the
    permission. Implementations own the database transaction and require a
    request-local session with no active transaction when the call starts.
    """

    @abstractmethod
    async def set_action_grant(
        self,
        *,
        access: AccessContextDTO,
        command: SetProjectActionGrantCommand,
        context: OperationAdmissionContextDTO,
    ) -> ProjectActionGrantChangeResultDTO:
        """Set an eligible exact assignment under current human delegation.

        Authorize actor/scope before reservation or completed replay. Only new
        work checks recipient eligibility, reviewed Access revision and handover.
        Commit change/revision/audit/original result together. New assignment is
        201, level change or no-op is 200. Replay returns original status/facts.
        """
        ...

    @abstractmethod
    async def remove_action_grant(
        self,
        *,
        access: AccessContextDTO,
        command: RemoveProjectActionGrantCommand,
        context: OperationAdmissionContextDTO,
    ) -> ProjectActionGrantChangeResultDTO:
        """Remove only this action, including from an inactive/blocked recipient.

        Retain current actor authority and exact recipient scope. New work checks
        reviewed Access revision and remaining eligible exact-action grantors.
        An authorized absent result is 200 without a revision increment. Replay
        returns original removal facts and never removes a later assignment.
        """
        ...

    @abstractmethod
    async def assign_use_only(
        self,
        *,
        access: AccessContextDTO,
        command: AssignProjectUseOnlyGrantCommand,
        context: OperationAdmissionContextDTO,
    ) -> CompletedSynchronousOperationDTO:
        """Assign permission to use an action without granting permission to delegate it.

        For example, Alice lets Bob create access groups in Support. Alice must
        currently be allowed to grant that action, and Bob must be an eligible
        human member of the project.

        Commit a new grant, updated permission revision, audit entry and saved
        retry result together. Check current authority before looking up any
        saved result. A matching completed retry returns the original result
        without another write. Check the expected revision only for new work.

        Args:
            access: Authenticated caller requesting the assignment, such as Alice.
            command: Project, recipient, action and the permission revision the
                caller last read. The revision detects changes before new work.
            context: Stable retry key, method and canonical route for this request.

        Returns:
            Completion metadata, rather than the permission record. `operation_id`
            identifies the original operation. `created` is true for a new
            assignment and false for a saved replay. `expires_at` expires the
            saved retry result, not the granted permission.

        Raises:
            ResourceNotFoundError: The project is unavailable to the caller, or
                the recipient does not exist.
            AccessDeniedError: The caller cannot delegate the action, or the
                caller or recipient fails the current access requirements.
            StaleRevisionError: Project permissions changed before a new assignment.
            ConflictError: The grant already exists, the retry key has different
                meaning, or earlier work is unfinished or requires recovery.
            RuntimeError: Authorization returned a different project, or the
                database session already has an active transaction.
        """
        ...
