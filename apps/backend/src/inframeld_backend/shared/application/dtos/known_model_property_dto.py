from dataclasses import dataclass, field
from typing import Literal

from inframeld_backend.shared.application.dtos.model_metadata_source_dto import (
    ModelMetadataSourceDTO,
)
from inframeld_backend.shared.application.enums.model_property_state import ModelPropertyState


@dataclass(frozen=True, slots=True)
class KnownModelPropertyDTO[T]:
    """Carry one sourced property value for review."""

    value: T
    source: ModelMetadataSourceDTO
    state: Literal[ModelPropertyState.KNOWN] = field(kw_only=True)
