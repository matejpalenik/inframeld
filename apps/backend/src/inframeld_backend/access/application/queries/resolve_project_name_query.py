from dataclasses import dataclass

from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName


@dataclass(frozen=True, slots=True)
class ResolveProjectNameQuery:
    name: ResourceName
