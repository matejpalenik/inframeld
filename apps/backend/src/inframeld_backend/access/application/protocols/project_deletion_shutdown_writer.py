from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.project_deletion_shutdown_facts_dto import (
    ProjectDeletionShutdownFactsDTO,
)
from inframeld_backend.shared.application.dtos.job_attempt_context_dto import JobAttemptContextDTO


class ProjectDeletionShutdownWriter(Protocol):
    """Persist only the checked local shutdown checkpoint inside its caller's transaction."""

    @abstractmethod
    async def lock_original(self, context: JobAttemptContextDTO) -> ProjectDeletionShutdownFactsDTO:
        """Lock Organization, Project and original obligation in that order.

        Require the caller's active READ COMMITTED transaction and original
        deadline. Refresh actual scope, DELETING lifecycle and parent facts
        after waits. These observations are not an admission or fence certificate.
        The caller then acquires exact job ownership before application effects.
        Missing or conflicting required backing fails closed, never provisions it.
        """
        ...

    @abstractmethod
    async def record_shutdown(
        self,
        context: JobAttemptContextDTO,
        *,
        facts: ProjectDeletionShutdownFactsDTO,
        changed: bool,
        access_revision: int,
    ) -> None:
        """Save local effects' revision/audit and monotonic parent checkpoint atomically.

        Use the same caller transaction, held coordination and live original
        fence. Recheck that fence and checked source revision before conditional
        persistence. Changed Access rows advance the revision once and require
        their correlated audit. An unchanged checked state advances no Access
        revision and creates no change audit. Both confirm local shutdown only.
        Do not settle physical cleanup, start retention, alter immutable original
        meaning, write generic completion bytes, commit or reset a deadline.
        Failure must propagate for rollback with the preceding effects.
        """
        ...
