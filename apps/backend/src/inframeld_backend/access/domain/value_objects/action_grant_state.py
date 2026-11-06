from dataclasses import dataclass, replace
from typing import Self


@dataclass(frozen=True, slots=True)
class ActionGrantState:
    """Distinguish an absent assignment from use-only and delegating assignments."""

    can_grant: bool | None

    def set_level(self, *, can_grant: bool) -> Self:
        return replace(self, can_grant=can_grant)

    def remove(self) -> Self:
        return replace(self, can_grant=None)
