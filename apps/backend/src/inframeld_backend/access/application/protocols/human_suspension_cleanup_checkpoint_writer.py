from abc import abstractmethod
from typing import Protocol
from uuid import UUID

from inframeld_backend.access.application.dtos.human_suspension_cleanup_dispatch_dto import (
    HumanSuspensionCleanupDispatchDTO,
)
from inframeld_backend.access.domain.enums.identity_recovery_cleanup_state import (
    IdentityRecoveryCleanupState,
)
from inframeld_backend.shared.application.dtos.job_attempt_context_dto import JobAttemptContextDTO
from inframeld_backend.shared.application.enums.human_suspension_cleanup_step import (
    HumanSuspensionCleanupStep,
)


class HumanSuspensionCleanupCheckpointWriter(Protocol):
    """Persist one exact fenced effect in the caller's short transaction."""

    @abstractmethod
    async def prepare_dispatch(
        self, context: JobAttemptContextDTO, *, worker_id: UUID, step: HumanSuspensionCleanupStep
    ) -> HumanSuspensionCleanupDispatchDTO | None:
        """Mark the current step, or return no effect if durably confirmed."""
        ...

    @abstractmethod
    async def confirm(
        self, context: JobAttemptContextDTO, *, worker_id: UUID, step: HumanSuspensionCleanupStep
    ) -> None: ...

    @abstractmethod
    async def stop_unconfirmed(
        self,
        context: JobAttemptContextDTO,
        *,
        worker_id: UUID,
        step: HumanSuspensionCleanupStep,
        outcome: IdentityRecoveryCleanupState,
    ) -> None: ...
