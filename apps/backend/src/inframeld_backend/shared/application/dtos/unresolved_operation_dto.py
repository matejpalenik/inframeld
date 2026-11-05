from dataclasses import dataclass
from typing import Literal

from inframeld_backend.shared.application.enums.operation_lookup_outcome import (
    OperationLookupOutcome,
)


@dataclass(frozen=True, slots=True)
class UnresolvedOperationDTO:
    """Establish no authoritative retained match, without claiming no effects."""

    outcome: Literal[OperationLookupOutcome.UNRESOLVED] = OperationLookupOutcome.UNRESOLVED
