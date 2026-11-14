from dataclasses import dataclass

from inframeld_backend.shared.application.dtos.model_metadata_source_dto import (
    ModelMetadataSourceDTO,
)
from inframeld_backend.shared.application.enums.reviewed_model_property import ReviewedModelProperty


@dataclass(frozen=True, slots=True)
class AdoptedModelSuggestionDTO:
    """Attribute one reviewed value to the exact source that supplied it."""

    property: ReviewedModelProperty
    source: ModelMetadataSourceDTO
