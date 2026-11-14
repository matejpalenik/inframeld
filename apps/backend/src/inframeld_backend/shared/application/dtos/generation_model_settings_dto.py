from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

from inframeld_backend.shared.application.enums.model_role import ModelRole
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation


@dataclass(frozen=True, slots=True)
class GenerationModelSettingsDTO:
    """Carry reviewed generation limits and controls, including provider-controlled temperature."""

    output_tokens: int
    temperature: Decimal | None
    structured_output: bool
    role: Literal[ModelRole.GENERATION] = field(kw_only=True)

    def __post_init__(self) -> None:
        RevisionValidation.require(self.output_tokens)
        if self.output_tokens == 0:
            raise ValueError("An output token limit must be positive.")
        if self.temperature is not None and (not self.temperature.is_finite()):
            raise ValueError("An explicit temperature requires a finite decimal.")
