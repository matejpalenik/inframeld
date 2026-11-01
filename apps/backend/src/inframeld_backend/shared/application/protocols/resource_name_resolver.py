from abc import abstractmethod
from typing import Protocol

from inframeld_backend.shared.application.dtos.resource_name_binding_dto import (
    ResourceNameBindingDTO,
)
from inframeld_backend.shared.application.queries.resolve_resource_name_query import (
    ResolveResourceNameQuery,
)


class ResourceNameResolver(Protocol):
    """Validate one exact binding. A retired binding is never an automatic redirect.

    The owner must check current Access before disclosing either binding or guidance.
    """

    @abstractmethod
    async def resolve(self, query: ResolveResourceNameQuery) -> ResourceNameBindingDTO: ...
