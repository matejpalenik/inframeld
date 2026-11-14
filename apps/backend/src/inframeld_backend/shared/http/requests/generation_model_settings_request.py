from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from inframeld_backend.shared.application.enums.model_role import ModelRole
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation
from inframeld_backend.shared.http.types.model_decimal import ModelDecimal


class GenerationModelSettingsRequest(BaseModel):
    """Parse the supported generation settings without losing decimal precision."""

    model_config = ConfigDict(extra="forbid", strict=True)

    role: Literal[ModelRole.GENERATION]
    output_tokens: int = Field(ge=1, le=RevisionValidation.MAX_VALUE)
    temperature: ModelDecimal | None
    structured_output: bool
