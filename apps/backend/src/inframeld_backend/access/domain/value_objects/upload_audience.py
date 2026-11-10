from dataclasses import dataclass

from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId


@dataclass(frozen=True, slots=True)
class UploadAudience:
    """Identify one complete, nonempty set of future-upload groups."""

    group_ids: tuple[AccessGroupId, ...]

    def __post_init__(self) -> None:
        if type(self.group_ids) is not tuple:
            raise TypeError("An upload audience requires a tuple of typed group identities.")
        for group in self.group_ids:
            UploadAudience._require_group(group)
        if not self.group_ids or len(set(self.group_ids)) != len(self.group_ids):
            raise ValueError("An upload audience must be nonempty and contain no duplicates.")
        object.__setattr__(
            self, "group_ids", tuple(sorted(self.group_ids, key=lambda group: group.value))
        )

    @staticmethod
    def _require_group(group: object) -> None:
        if not isinstance(group, AccessGroupId):
            raise TypeError("An upload audience requires typed group identities.")
