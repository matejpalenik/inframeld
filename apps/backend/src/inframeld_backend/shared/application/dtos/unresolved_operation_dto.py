from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class UnresolvedOperationDTO:
    """Establish no authoritative retained match, without claiming no effects."""

    outcome: Literal["unresolved"] = "unresolved"
