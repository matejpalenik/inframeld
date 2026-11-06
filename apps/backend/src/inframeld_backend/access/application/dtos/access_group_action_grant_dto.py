from dataclasses import dataclass

from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId


@dataclass(frozen=True, slots=True)
class AccessGroupActionGrantDTO:
    """Carry one stored exact assignment without implying current recipient eligibility."""

    recipient_principal_id: PrincipalId
    action_id: ActionId
    can_grant: bool
