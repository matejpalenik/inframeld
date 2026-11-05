import re
from dataclasses import dataclass, field

from inframeld_backend.access.domain.value_objects.project_id import ProjectId


@dataclass(frozen=True, slots=True)
class GetMyProjectAccessQuery:
    project_id: ProjectId
    limit: int = 25
    cursor: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if type(self.limit) is not int or not 1 <= self.limit <= 100:
            raise ValueError("The page limit must be an integer from 1 to 100.")

        if self.cursor is not None and (
            not 1 <= len(self.cursor) <= 1024
            or re.fullmatch(r"[A-Za-z0-9_-]+", self.cursor) is None
        ):
            raise ValueError("The continuation cursor has invalid syntax.")
