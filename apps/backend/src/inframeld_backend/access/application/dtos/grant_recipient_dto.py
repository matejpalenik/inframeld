from dataclasses import dataclass

from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId


@dataclass(frozen=True, slots=True)
class GrantRecipientDTO:
    """Disclose only the safe principal metadata needed to choose a recipient."""

    principal_id: PrincipalId
    display_name: str
    kind: PrincipalKind
