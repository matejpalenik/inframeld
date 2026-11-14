from dataclasses import dataclass
from datetime import datetime

from inframeld_backend.shared.application.dtos.embedding_model_settings_dto import (
    EmbeddingModelSettingsDTO,
)
from inframeld_backend.shared.application.dtos.model_selection_dto import ModelSelectionDTO
from inframeld_backend.shared.application.dtos.reviewed_model_settings_dto import (
    ReviewedModelSettingsDTO,
)
from inframeld_backend.shared.application.dtos.spending_usage_dto import SpendingUsageDTO
from inframeld_backend.shared.application.enums.model_call_outcome import ModelCallOutcome
from inframeld_backend.shared.application.enums.model_role import ModelRole
from inframeld_backend.shared.application.value_objects.model_call_id import ModelCallId
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation


@dataclass(frozen=True, slots=True)
class ModelCallObservationDTO:
    """Attribute a call to actual revisions and safe facts from the trusted gateway.

    This record carries no authority and cannot authenticate an adapter or its result.
    """

    selection: ModelSelectionDTO
    provider: str
    operation_id: OperationId
    call_id: ModelCallId
    is_preflight: bool
    outcome: ModelCallOutcome
    settings_fingerprint: str
    access_revision: int
    credential_revision: int | None
    adapter_revision: str
    observed_at: datetime
    observed_model: str | None
    provider_model_revision: str | None
    observed_dimensions: int | None
    usage: tuple[SpendingUsageDTO, ...] | None

    def __post_init__(self) -> None:
        RevisionValidation.require(self.access_revision)
        if self.credential_revision is not None:
            RevisionValidation.require(self.credential_revision)
        if not all(
            value.strip()
            for value in (self.provider, self.settings_fingerprint, self.adapter_revision)
        ):
            raise ValueError(
                "Call evidence requires its actual provider, settings and adapter revision."
            )
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("Call evidence requires an aware observation time.")
        if self.observed_dimensions is not None:
            RevisionValidation.require(self.observed_dimensions)
            if self.selection.role is not ModelRole.EMBEDDING or self.observed_dimensions == 0:
                raise ValueError(
                    "Observed embedding dimensions require the embedding role and a positive value."
                )
        elif (
            self.selection.role is ModelRole.EMBEDDING and self.outcome is ModelCallOutcome.ACCEPTED
        ):
            raise ValueError("Accepted embedding evidence requires observed dimensions.")

    def validates(
        self,
        reviewed: ReviewedModelSettingsDTO,
        access_revision: int,
        credential_revision: int | None,
        adapter_revision: str,
        provider: str,
    ) -> bool:
        """Check if accepted historical evidence applies to the current reviewed selection."""
        settings = reviewed.effective.settings
        return (
            self.outcome is ModelCallOutcome.ACCEPTED
            and self.selection == reviewed.selection
            and self.settings_fingerprint == reviewed.fingerprint
            and self.access_revision == access_revision
            and self.credential_revision == credential_revision
            and self.adapter_revision == adapter_revision
            and self.provider == provider
            and (
                not isinstance(settings, EmbeddingModelSettingsDTO)
                or (
                    self.provider == settings.expected_provider
                    and self.observed_dimensions == settings.dimensions
                    and (
                        settings.expected_model_revision is None
                        or self.provider_model_revision == settings.expected_model_revision
                    )
                )
            )
        )
