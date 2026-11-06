from enum import StrEnum

from inframeld_backend.shared.application.enums.http_method import HttpMethod


class AccessGroupChangeKind(StrEnum):
    ADD_MEMBER = "add-member"
    REMOVE_MEMBER = "remove-member"
    APPOINT_MANAGER = "appoint-manager"
    REMOVE_MANAGER = "remove-manager"

    @property
    def is_addition(self) -> bool:
        return self in (self.ADD_MEMBER, self.APPOINT_MANAGER)

    @property
    def collection(self) -> str:
        return "members" if self in (self.ADD_MEMBER, self.REMOVE_MEMBER) else "managers"

    @property
    def http_method(self) -> HttpMethod:
        return HttpMethod.PUT if self.is_addition else HttpMethod.DELETE

    def success_status(self, *, changed: bool) -> int:
        return 201 if self.is_addition and changed else 200
