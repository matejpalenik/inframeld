from dataclasses import dataclass

from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId


@dataclass(frozen=True, slots=True)
class ProjectActionGrantDTO:
    """Carry one stored assignment, independently of its recipient's eligibility."""

    recipient_principal_id: PrincipalId
    action_id: ActionId
    can_grant: bool
