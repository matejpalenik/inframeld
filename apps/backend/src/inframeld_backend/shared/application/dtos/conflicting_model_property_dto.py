from dataclasses import dataclass, field
from typing import Literal

from inframeld_backend.shared.application.dtos.known_model_property_dto import KnownModelPropertyDTO
from inframeld_backend.shared.application.enums.model_metadata_source_kind import (
    ModelMetadataSourceKind,
)
from inframeld_backend.shared.application.enums.model_property_state import ModelPropertyState


@dataclass(frozen=True, slots=True)
class ConflictingModelPropertyDTO[T]:
    """Keep disagreeing values and all the evidence needed to explain them."""

    alternatives: tuple[KnownModelPropertyDTO[T], ...]
    state: Literal[ModelPropertyState.CONFLICT] = field(kw_only=True)

    def __post_init__(self) -> None:
        if not self.alternatives or all(
            item.value == self.alternatives[0].value for item in self.alternatives
        ):
            raise ValueError("A metadata conflict requires distinct values.")

    def prefill(self) -> KnownModelPropertyDTO[T] | None:
        """Prefer one unambiguous qualified server value as a suggestion for review."""
        server = tuple(
            item
            for item in self.alternatives
            if item.source.kind is ModelMetadataSourceKind.SELECTED_SERVER
        )
        if server and all(item.value == server[0].value for item in server):
            return server[0]
        return None
