from abc import abstractmethod
from typing import Protocol

from inframeld_backend.shared.application.dtos.resource_name_binding_dto import (
    ResourceNameBindingDTO,
)
from inframeld_backend.shared.application.queries.resolve_resource_name_query import (
    ResolveResourceNameQuery,
)


class ResourceNameBindingReader(Protocol):
    """Observe only the requested exact kind/scope, without fallback or disclosure authority."""

    @abstractmethod
    async def read(self, query: ResolveResourceNameQuery) -> tuple[ResourceNameBindingDTO, ...]: ...
