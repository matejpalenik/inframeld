from dataclasses import dataclass

from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId


@dataclass(frozen=True, slots=True)
class ModelConnectionGrantItemDTO:
    recipient_id: PrincipalId
    can_grant: bool
