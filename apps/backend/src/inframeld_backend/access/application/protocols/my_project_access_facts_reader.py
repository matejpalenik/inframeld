from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.my_project_access_facts_dto import (
    MyProjectAccessFactsDTO,
)
from inframeld_backend.access.application.value_objects.my_project_access_position import (
    MyProjectAccessPosition,
)
from inframeld_backend.access.domain.value_objects.project_id import ProjectId


class MyProjectAccessFactsReader(Protocol):
    @abstractmethod
    async def read_page(
        self,
        *,
        access: AccessContextDTO,
        project_id: ProjectId,
        after: MyProjectAccessPosition | None,
        limit: int,
    ) -> MyProjectAccessFactsDTO | None:
        """Observe the actual caller's relationships and current Access revision.

        Use one clean request-local SQL snapshot and retain its current actor,
        credential, scope and revision header for empty pages. Join only real
        scoped Project/group/application-account targets. Return at most limit+1
        entries ordered by grant, membership, management, then target UUID and
        action literal. The combined limit covers every relationship kind.
        Do not expand implied grants, disclose another principal, authorize,
        lock, write, commit or call providers. Bootstrap owns session lifetime.
        """
        ...
