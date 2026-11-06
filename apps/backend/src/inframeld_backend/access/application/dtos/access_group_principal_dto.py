from dataclasses import dataclass

from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId


@dataclass(frozen=True, slots=True)
class AccessGroupPrincipalDTO:
    principal_id: PrincipalId
    kind: PrincipalKind
    display_name: str
