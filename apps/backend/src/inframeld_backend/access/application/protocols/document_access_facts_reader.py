from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.document_access_facts_dto import (
    DocumentAccessFactsDTO,
)
from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId


class DocumentAccessFactsReader(Protocol):
    """Observe current actor, exact Project and all original audience groups.

    The caller owns a short READ COMMITTED transaction and its coordination locks.
    Read Organization, requested Project and current key in compatible order, then
    observe database time and state after waits. Never lock a foreign Project.
    Include current human credential/recovery or exact trusted adapter key facts.
    Missing groups stay absent from valid_group_ids, never silently repair audiences.
    No cached permissions, independent transactions, commits or network calls.
    """

    @abstractmethod
    async def read(
        self,
        *,
        access: AccessContextDTO,
        project_id: ProjectId,
        audience_group_ids: frozenset[AccessGroupId],
    ) -> DocumentAccessFactsDTO | None: ...
