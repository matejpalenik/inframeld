from dataclasses import dataclass
from datetime import datetime

from inframeld_backend.shared.application.enums.model_metadata_source_kind import (
    ModelMetadataSourceKind,
)


@dataclass(frozen=True, slots=True)
class ModelMetadataSourceDTO:
    """Attribute a suggestion to an identified catalogue snapshot or qualified server adapter."""

    kind: ModelMetadataSourceKind
    reference: str
    revision: str
    observed_at: datetime

    def __post_init__(self) -> None:
        if not self.reference.strip() or not self.revision.strip():
            raise ValueError("A model metadata source requires its reference and revision.")
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("A model metadata source requires an aware observation time.")
