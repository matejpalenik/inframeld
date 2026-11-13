from dataclasses import dataclass, field
from typing import Literal

from inframeld_backend.shared.application.enums.model_property_state import ModelPropertyState


@dataclass(frozen=True, slots=True)
class UnknownModelPropertyDTO:
    """Represent unavailable information without substituting a default."""

    state: Literal[ModelPropertyState.UNKNOWN] = field(kw_only=True)
