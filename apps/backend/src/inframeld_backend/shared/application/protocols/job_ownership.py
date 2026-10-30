from abc import abstractmethod
from typing import Protocol

from inframeld_backend.shared.application.dtos.job_attempt_context_dto import JobAttemptContextDTO
from inframeld_backend.shared.application.dtos.job_snapshot_dto import JobSnapshotDTO


class JobOwnership(Protocol):
    """Fence an owning business save inside its already-authorized transaction.

    Use the same session as the owning publication. Check current domain/source
    authority first. A matching fence alone grants no product permission.
    """

    @abstractmethod
    async def require_current(self, context: JobAttemptContextDTO) -> JobSnapshotDTO: ...
