"""Application-owned values used by Access contracts and persistence."""

from dataclasses import dataclass
from enum import StrEnum
from typing import NewType
from uuid import UUID

OrganizationId = NewType("OrganizationId", UUID)
PrincipalId = NewType("PrincipalId", UUID)
ProjectId = NewType("ProjectId", UUID)


class PrincipalKind(StrEnum):
    HUMAN = "human"
    APPLICATION = "application"


class PrincipalStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    RETIRED = "retired"


class ProjectStatus(StrEnum):
    ACTIVE = "active"
    DELETING = "deleting"


class ActionTargetKind(StrEnum):
    PROJECT = "project"
    PIPELINE = "pipeline"


@dataclass(frozen=True, slots=True)
class ActionId:
    value: str

    def __post_init__(self) -> None:
        if not self.value.strip() or len(self.value) > 100:
            raise ValueError("An action ID must be nonblank and at most 100 characters.")


@dataclass(frozen=True, slots=True)
class IdentityAuthority:
    value: str

    def __post_init__(self) -> None:
        if not self.value.strip():
            raise ValueError("An identity authority must be nonblank.")


@dataclass(frozen=True, slots=True)
class IdentitySubject:
    value: str

    def __post_init__(self) -> None:
        if not self.value.strip():
            raise ValueError("An identity subject must be nonblank.")
