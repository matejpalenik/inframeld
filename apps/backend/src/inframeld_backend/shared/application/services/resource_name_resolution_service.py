from typing import override

from inframeld_backend.shared.application.dtos.resource_name_binding_dto import (
    ResourceNameBindingDTO,
)
from inframeld_backend.shared.application.errors.application_errors import ResourceNotFoundError
from inframeld_backend.shared.application.protocols.resource_name_binding_reader import (
    ResourceNameBindingReader,
)
from inframeld_backend.shared.application.protocols.resource_name_resolver import (
    ResourceNameResolver,
)
from inframeld_backend.shared.application.queries.resolve_resource_name_query import (
    ResolveResourceNameQuery,
)
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation


class ResourceNameResolutionService(ResourceNameResolver):
    def __init__(self, resource_name_binding_reader: ResourceNameBindingReader) -> None:
        self._resource_name_binding_reader = resource_name_binding_reader

    @override
    async def resolve(self, query: ResolveResourceNameQuery) -> ResourceNameBindingDTO:
        bindings = await self._resource_name_binding_reader.read(query)
        if len(bindings) != 1:
            raise ResourceNotFoundError()

        binding = bindings[0]
        if (
            binding.kind is not query.kind
            or binding.scope != query.scope
            or binding.name != query.name
            or type(binding.revision) is not int
            or not 0 <= binding.revision <= RevisionValidation.MAX_VALUE
        ):
            raise ResourceNotFoundError()

        return binding
