from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.commands.resume_identity_recovery_cleanup_command import (
    ResumeIdentityRecoveryCleanupCommand,
)
from inframeld_backend.access.application.dtos.identity_recovery_cleanup_resume_result_dto import (
    IdentityRecoveryCleanupResumeResultDTO,
)


class IdentityRecoveryCleanupResumer(Protocol):
    """Authorize a new bounded run of the original recovery through host maintenance.

    Call only from the protected host-maintenance boundary.
    An accepted request replays its original result. This grants no product
    permission and never releases access or repeats confirmed cleanup.
    """

    @abstractmethod
    async def resume(
        self, *, command: ResumeIdentityRecoveryCleanupCommand
    ) -> IdentityRecoveryCleanupResumeResultDTO:
        """Commit an authorization or recover the original accepted result.

        Own one five-second database transaction, including commit. A completed
        recovery or fully confirmed cleanup returns a successful no-run outcome.

        RecoveryMaintenanceError identifies controlled rejections, including
        active runs, missing Kratos evidence, installation mismatch and changed
        request meaning. Missing required state uses its dependency_unavailable
        code. Database availability failures and deadline expiry raise
        DependencyUnavailableError. Cancellation propagates.

        An absent response or unavailable commit acknowledgment leaves the
        outcome unknown. Retry the identical command with the original request
        ID rather than requesting another authorization.
        """
        ...
