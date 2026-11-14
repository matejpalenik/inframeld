from abc import abstractmethod
from typing import Protocol

from inframeld_backend.shared.application.commands.restored_job_quarantine_command import (
    RestoredJobQuarantineCommand,
)
from inframeld_backend.shared.application.dtos.job_snapshot_dto import JobSnapshotDTO


class RestoredJobQuarantineRepository(Protocol):
    """Observe the exact original product job and save quarantine with its operator audit."""

    @abstractmethod
    async def observe_restored_job(
        self, command: RestoredJobQuarantineCommand
    ) -> JobSnapshotDTO: ...

    @abstractmethod
    async def quarantine_restored_job(
        self, command: RestoredJobQuarantineCommand, observed: JobSnapshotDTO
    ) -> JobSnapshotDTO: ...
