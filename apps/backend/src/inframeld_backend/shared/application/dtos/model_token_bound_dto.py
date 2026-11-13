from dataclasses import dataclass

from inframeld_backend.shared.application.enums.model_token_bound_kind import ModelTokenBoundKind


@dataclass(frozen=True, slots=True)
class ModelTokenBoundDTO:
    """Identify the pinned implementation that can establish a bound for the selected model."""

    kind: ModelTokenBoundKind
    implementation: str
    revision: str

    def __post_init__(self) -> None:
        if not self.implementation.strip() or not self.revision.strip():
            raise ValueError("A token bound requires a pinned implementation and revision.")
