"""Define the principal values owned by Access."""

from dataclasses import dataclass
from enum import StrEnum
from typing import override
from uuid import UUID

from inframeld_backend.access.domain.organization_values import OrganizationId
from inframeld_backend.shared.domain.value_validation import require_uuid


@dataclass(frozen=True, slots=True)
class PrincipalId:
    """Identify one Principal using a UUID, independently of its existence."""

    value: UUID

    def __post_init__(self) -> None:
        """Require parsing at the boundary before creating a nominal identifier."""
        require_uuid(self.value)


class PrincipalKind(StrEnum):
    """Distinguish local human actors from application accounts."""

    HUMAN = "human"
    APPLICATION = "application"


class PrincipalStatus(StrEnum):
    """Describe whether a local actor is active, suspended, or permanently retired."""

    ACTIVE = "active"
    SUSPENDED = "suspended"
    RETIRED = "retired"


@dataclass(frozen=True, slots=True, eq=False)
class Principal:
    """Carry a local actor's identity, organization, kind, and current account status."""

    id: PrincipalId
    organization_id: OrganizationId
    kind: PrincipalKind
    status: PrincipalStatus

    @override
    def __eq__(self, other: object) -> bool:
        """Compare entity identity independently of the state observed at read time."""
        if not isinstance(other, Principal):
            return NotImplemented
        return self.id == other.id

    @override
    def __hash__(self) -> int:
        """Keep principal identity stable in sets when account state changes."""
        return hash(self.id)
