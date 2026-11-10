from abc import abstractmethod
from typing import Protocol

from inframeld_backend.shared.application.dtos.project_deletion_job_binding_dto import (
    ProjectDeletionJobBindingDTO,
)
from inframeld_backend.shared.application.dtos.project_deletion_job_facts_dto import (
    ProjectDeletionJobFactsDTO,
)
from inframeld_backend.shared.application.value_objects.job_id import JobId


class ProjectDeletionJobAuthorizer(Protocol):
    @abstractmethod
    async def require_current(
        self, job_id: JobId, binding: ProjectDeletionJobBindingDTO
    ) -> ProjectDeletionJobFactsDTO:
        """Require matching retained deletion backing before an original local shutdown step.

        This checks immutable obligation integrity, not current product grants,
        incoming credentials, a live fence or physical-erasure authority.
        The caller must still check its exact current job ownership and the
        Access-owned DELETING scope before effects. Missing or inconsistent
        backing raises AccessDeniedError. No new transaction or deadline is owned.
        """
        ...
