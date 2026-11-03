from dataclasses import dataclass

from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId


@dataclass(frozen=True, slots=True)
class ProjectMemberDTO:
    """Describe a stored relationship without implying the recipient may currently act."""

    principal_id: PrincipalId
    display_name: str
    kind: PrincipalKind
