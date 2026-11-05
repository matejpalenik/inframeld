from enum import StrEnum
from typing import Literal

from inframeld_backend.shared.application.enums.http_method import HttpMethod


class ProjectMembershipChangeKind(StrEnum):
    """Identify the intended membership change in commands and retained receipts."""

    ADD = "add"
    REMOVE = "remove"

    @property
    def http_method(self) -> Literal[HttpMethod.PUT, HttpMethod.DELETE]:
        return HttpMethod.PUT if self is ProjectMembershipChangeKind.ADD else HttpMethod.DELETE

    def success_status(self, *, changed: bool) -> int:
        """Only a newly added membership returns 201, including on receipt replay."""
        return 201 if self is ProjectMembershipChangeKind.ADD and changed else 200
