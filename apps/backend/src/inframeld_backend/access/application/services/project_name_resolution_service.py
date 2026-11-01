from typing import override

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_metadata_dto import ProjectMetadataDTO
from inframeld_backend.access.application.errors.retired_project_name_error import (
    RetiredProjectNameError,
)
from inframeld_backend.access.application.protocols.project_metadata_authorizer import (
    ProjectMetadataAuthorizer,
)
from inframeld_backend.access.application.protocols.project_metadata_facts_reader import (
    ProjectMetadataFactsReader,
)
from inframeld_backend.access.application.protocols.project_metadata_repository import (
    ProjectMetadataRepository,
)
from inframeld_backend.access.application.protocols.project_name_resolver import ProjectNameResolver
from inframeld_backend.access.application.queries.resolve_project_name_query import (
    ResolveProjectNameQuery,
)
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.enums.resource_name_kind import ResourceNameKind
from inframeld_backend.shared.application.protocols.resource_name_resolver import (
    ResourceNameResolver,
)
from inframeld_backend.shared.application.protocols.transaction_manager import TransactionManager
from inframeld_backend.shared.application.queries.resolve_resource_name_query import (
    ResolveResourceNameQuery,
)


class ProjectNameResolutionService(ProjectNameResolver):
    def __init__(
        self,
        *,
        transactions: TransactionManager,
        facts: ProjectMetadataFactsReader,
        resolver: ResourceNameResolver,
        authorizer: ProjectMetadataAuthorizer,
        repository: ProjectMetadataRepository,
    ) -> None:
        self._transactions = transactions
        self._facts = facts
        self._resolver = resolver
        self._authorizer = authorizer
        self._repository = repository

    @override
    async def resolve(
        self, *, access: AccessContextDTO, query: ResolveProjectNameQuery
    ) -> ProjectMetadataDTO:
        async with self._transactions.begin():
            scope = await self._facts.scope(access=access)
            binding = await self._resolver.resolve(
                ResolveResourceNameQuery(scope, ResourceNameKind.PROJECT, query.name)
            )
            project_id = ProjectId(binding.resource_id)
            authorized = await self._authorizer.require_read(access=access, project_id=project_id)
            if (authorized.organization_id, authorized.project_id) != (
                scope.organization_id,
                project_id,
            ):
                raise RuntimeError("Project resolution changed its authorized scope.")
            metadata = await self._repository.get(
                organization_id=scope.organization_id, project_id=project_id
            )
            if (metadata.organization_id, metadata.project_id) != (
                scope.organization_id,
                project_id,
            ):
                raise RuntimeError("Project metadata changed its resolved binding.")
            if binding.retired or metadata.name != query.name:
                raise RetiredProjectNameError(metadata.project_id, metadata.name)
            return ProjectMetadataDTO(
                metadata.organization_id,
                metadata.project_id,
                metadata.name,
                metadata.display_name,
                metadata.revision,
            )
