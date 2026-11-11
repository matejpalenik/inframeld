from abc import abstractmethod
from typing import Protocol
from uuid import UUID

from inframeld_backend.shared.application.dtos.project_deletion_job_facts_dto import (
    ProjectDeletionJobFactsDTO,
)


class ProjectDeletionJobFactsReader(Protocol):
    @abstractmethod
    async def read(self, obligation_id: UUID) -> ProjectDeletionJobFactsDTO | None:
        """Read genuine retained backing and original attribution in the caller transaction.

        Validate every existing child against its retained original. An absent
        child is unavailable before committed local shutdown. After that genuine
        checkpoint, retain original job/payload references without inventing a
        live job, attempt or fence. Active callers must still obtain actual job
        ownership before effects or terminal saves. Native request and Project
        records may already have retired.

        Refresh with database time, without parent write locks after a child lock.
        Preserve caller transaction/deadline. Missing authoritative backing is
        absent, never reconstructed from a marker or product/artifact context.
        """
        ...
