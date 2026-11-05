from enum import StrEnum
from typing import Literal


class ProjectMembershipChangeKind(StrEnum):
    """Identify the intended membership change in commands and retained receipts."""

    ADD = "add"
    REMOVE = "remove"

    @property
    def http_method(self) -> Literal["PUT", "DELETE"]:
        return "PUT" if self is ProjectMembershipChangeKind.ADD else "DELETE"

    def success_status(self, *, changed: bool) -> int:
        """Only a newly added membership returns 201, including on receipt replay."""
        return 201 if self is ProjectMembershipChangeKind.ADD and changed else 200
