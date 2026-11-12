from dataclasses import dataclass, replace
from typing import override

from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.shared.domain.errors.domain_errors import InvalidStateTransitionError


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

    def suspend(self) -> "Principal":
        """Block a human immediately without applying ordinary assignment handover."""
        if self.kind is not PrincipalKind.HUMAN or self.status is PrincipalStatus.RETIRED:
            raise InvalidStateTransitionError("Only a non-retired human can be suspended.")
        return (
            self
            if self.status is PrincipalStatus.SUSPENDED
            else replace(self, status=PrincipalStatus.SUSPENDED)
        )

    def restore(self) -> "Principal":
        """Produce the checked human status transition without granting any rights."""
        if self.kind is not PrincipalKind.HUMAN or self.status is PrincipalStatus.RETIRED:
            raise InvalidStateTransitionError("Only a non-retired human can be restored.")
        return (
            self
            if self.status is PrincipalStatus.ACTIVE
            else replace(self, status=PrincipalStatus.ACTIVE)
        )
