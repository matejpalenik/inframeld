from abc import abstractmethod
from typing import Protocol

from inframeld_backend.shared.application.dtos.job_attempt_context_dto import JobAttemptContextDTO


class ProjectDeletionShutdown(Protocol):
    @abstractmethod
    async def shutdown(self, context: JobAttemptContextDTO) -> None:
        """Confirm the original Project's local shutdown in one bounded transaction.

        Require genuine retained deletion backing and the exact live original
        fence before effects and their checkpoint. The operation owns the
        five-second SQL transaction, rollback and revision/audit consistency.
        A committed original checkpoint skips effects without granting new work.
        Return only after commit, never as physical-cleanup completion.
        Cancellation and uncertain commit propagate without automatic redispatch.
        """
        ...
