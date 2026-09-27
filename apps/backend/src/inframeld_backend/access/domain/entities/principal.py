from dataclasses import dataclass
from typing import override

from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId


@dataclass(frozen=True, slots=True, eq=False)
class Principal:
    """A local actor whose identity stays the same when its account status changes.

    Equality and hashing use only the principal ID. The remaining fields describe
    the account state observed by the reader.
    """

    id: PrincipalId
    organization_id: OrganizationId
    kind: PrincipalKind
    status: PrincipalStatus

    @override
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Principal):
            return NotImplemented
        return self.id == other.id

    @override
    def __hash__(self) -> int:
        return hash(self.id)
