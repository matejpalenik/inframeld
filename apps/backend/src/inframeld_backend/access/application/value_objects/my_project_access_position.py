from dataclasses import dataclass
from uuid import UUID

from inframeld_backend.access.application.enums.my_project_access_item_kind import (
    MyProjectAccessItemKind,
)
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.shared.domain.validation.value_validation import ValueValidation


@dataclass(frozen=True, slots=True)
class MyProjectAccessPosition:
    """Resume one combined own-access page without carrying authorization."""

    kind: MyProjectAccessItemKind
    target_id: UUID
    action_id: ActionId | None

    def __post_init__(self) -> None:
        ValueValidation.require_uuid(self.target_id)
        if self.kind not in {
            MyProjectAccessItemKind.GRANT,
            MyProjectAccessItemKind.MEMBERSHIP,
            MyProjectAccessItemKind.MANAGEMENT,
        }:
            raise ValueError("The own-access relationship kind is unsupported.")
        if (self.kind == MyProjectAccessItemKind.GRANT) != (self.action_id is not None):
            raise ValueError("Only a grant position carries an action.")

    @property
    def sort_key(self) -> tuple[int, int, str]:
        order = {
            MyProjectAccessItemKind.GRANT: 0,
            MyProjectAccessItemKind.MEMBERSHIP: 1,
            MyProjectAccessItemKind.MANAGEMENT: 2,
        }
        return order[self.kind], self.target_id.int, self.action_id.value if self.action_id else ""
