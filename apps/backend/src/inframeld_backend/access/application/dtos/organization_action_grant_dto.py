from dataclasses import dataclass

from inframeld_backend.access.domain.value_objects.action_id import ActionId


@dataclass(frozen=True, slots=True)
class OrganizationActionGrantDTO:
    """Observe one stored assignment in the caller's Organization."""

    action_id: ActionId
    can_grant: bool
