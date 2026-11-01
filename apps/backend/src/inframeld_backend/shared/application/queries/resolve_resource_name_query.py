from dataclasses import dataclass

from inframeld_backend.shared.application.dtos.resource_name_scope_dto import ResourceNameScopeDTO
from inframeld_backend.shared.application.enums.resource_name_kind import ResourceNameKind
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName


@dataclass(frozen=True, slots=True)
class ResolveResourceNameQuery:
    scope: ResourceNameScopeDTO
    kind: ResourceNameKind
    name: ResourceName
