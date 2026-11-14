from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.model_connection_dto import ModelConnectionDTO
from inframeld_backend.access.application.dtos.project_action_facts_dto import ProjectActionFactsDTO
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.value_objects.model_connection_id import ModelConnectionId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


class ModelConnectionReadRepository(Protocol):
    """Observe eligible Project scope and select only directly granted current connections."""

    @abstractmethod
    async def lock_scope(
        self, access: AccessContextDTO, project_id: ProjectId
    ) -> tuple[InstallationId, ProjectActionFactsDTO] | None: ...

    @abstractmethod
    async def get_visible(
        self, facts: ProjectActionFactsDTO, project_id: ProjectId, connection_id: ModelConnectionId
    ) -> ModelConnectionDTO | None: ...

    @abstractmethod
    async def list_visible(
        self,
        facts: ProjectActionFactsDTO,
        project_id: ProjectId,
        after: ModelConnectionId | None,
        limit: int,
    ) -> tuple[ModelConnectionDTO, ...]: ...
