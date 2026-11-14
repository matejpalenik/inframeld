from datetime import UTC, datetime
from decimal import MAX_EMAX, MIN_EMIN, Context, Decimal, DecimalException, Inexact

from inframeld_backend.shared.application.dtos.embedding_cost_estimate_basis_dto import (
    EmbeddingCostEstimateBasisDTO,
)
from inframeld_backend.shared.application.dtos.embedding_cost_estimate_dto import (
    EmbeddingCostEstimateDTO,
)
from inframeld_backend.shared.application.dtos.embedding_estimate_connection_dto import (
    EmbeddingEstimateConnectionDTO,
)
from inframeld_backend.shared.application.dtos.embedding_input_quantity_dto import (
    EmbeddingInputQuantityDTO,
)
from inframeld_backend.shared.application.dtos.embedding_model_settings_dto import (
    EmbeddingModelSettingsDTO,
)
from inframeld_backend.shared.application.dtos.model_metadata_source_dto import (
    ModelMetadataSourceDTO,
)
from inframeld_backend.shared.application.dtos.reviewed_model_settings_dto import (
    ReviewedModelSettingsDTO,
)
from inframeld_backend.shared.application.dtos.spending_rate_dto import SpendingRateDTO
from inframeld_backend.shared.application.enums.embedding_cost_estimate_reason import (
    EmbeddingCostEstimateReason,
)
from inframeld_backend.shared.application.enums.model_metadata_source_kind import (
    ModelMetadataSourceKind,
)
from inframeld_backend.shared.application.enums.model_role import ModelRole
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation

_INPUT_TOKENS = ("input", "token")
# This single LiteLLM v1.108.6 row is the reviewed advisory price for the official adapter.
_OPENAI_SMALL_INPUT_RATE = SpendingRateDTO(*_INPUT_TOKENS, Decimal("0.00000002"))
_OPENAI_SMALL_CATALOGUE_SOURCE = ModelMetadataSourceDTO(
    kind=ModelMetadataSourceKind.CATALOGUE,
    reference="BerriAI/litellm v1.108.6:model_prices_and_context_window.json#text-embedding-3-small",
    revision="65781e15922f3a7c33b8f991adf56c11d26d0a60",
    observed_at=datetime(2026, 11, 11, 23, 29, 33, tzinfo=UTC),
)


class EmbeddingCostEstimatePolicy:
    """Estimate an exact advisory input cost from already captured facts."""

    @staticmethod
    def estimate(
        *,
        reviewed: ReviewedModelSettingsDTO,
        connection: EmbeddingEstimateConnectionDTO | None,
        current_access_revision: int,
        input_reference: str,
        captured_at: datetime,
        quantity: EmbeddingInputQuantityDTO | None,
    ) -> EmbeddingCostEstimateDTO:
        """Capture the rate only for the supported model and an exact trusted binding."""
        selection = reviewed.selection
        if selection.role is not ModelRole.EMBEDDING or selection.model != "text-embedding-3-small":
            return EmbeddingCostEstimateDTO(None, EmbeddingCostEstimateReason.UNSUPPORTED_MODEL)
        RevisionValidation.require(current_access_revision)
        settings = reviewed.effective.settings
        if (
            not isinstance(settings, EmbeddingModelSettingsDTO)
            or settings.expected_provider != "openai"
            or connection is None
            or connection.selection != selection
            or connection.settings_fingerprint != reviewed.fingerprint
            or connection.access_revision != current_access_revision
            or connection.official_openai_destination is not True
            or connection.official_openai_adapter is not True
        ):
            return EmbeddingCostEstimateDTO(None, EmbeddingCostEstimateReason.UNVERIFIED_BINDING)

        rate = EmbeddingCostEstimatePolicy._input_rate(reviewed.price_overrides)
        source = None if rate is not None else _OPENAI_SMALL_CATALOGUE_SOURCE
        basis = EmbeddingCostEstimateBasisDTO(
            connection, input_reference, captured_at, rate or _OPENAI_SMALL_INPUT_RATE, source
        )
        return EmbeddingCostEstimatePolicy.refine(basis, quantity)

    @staticmethod
    def refine(
        basis: EmbeddingCostEstimateBasisDTO,
        quantity: EmbeddingInputQuantityDTO | None,
    ) -> EmbeddingCostEstimateDTO:
        """Use the original basis with a saved observation of the same input and profile."""
        if quantity is None:
            return EmbeddingCostEstimateDTO(
                None, EmbeddingCostEstimateReason.MISSING_INPUT_QUANTITY, basis
            )
        if (
            quantity.input_reference != basis.input_reference
            or quantity.settings_fingerprint != basis.connection.settings_fingerprint
            or quantity.selection != basis.connection.selection
        ):
            return EmbeddingCostEstimateDTO(
                None, EmbeddingCostEstimateReason.MISMATCHED_INPUT_QUANTITY, basis
            )

        rate, tokens = basis.rate.usd_per_unit, quantity.usage.quantity
        # The product needs at most the sum of the operand coefficient lengths.
        context = Context(
            prec=len(rate.as_tuple().digits) + len(tokens.as_tuple().digits),
            Emin=MIN_EMIN,
            Emax=MAX_EMAX,
            traps=[Inexact],
        )
        try:
            amount = context.multiply(rate, tokens)
        except DecimalException:
            return EmbeddingCostEstimateDTO(
                None, EmbeddingCostEstimateReason.AMOUNT_OUT_OF_RANGE, basis, quantity
            )
        return EmbeddingCostEstimateDTO(amount, None, basis, quantity)

    @staticmethod
    def _input_rate(rates: tuple[SpendingRateDTO, ...]) -> SpendingRateDTO | None:
        return next((rate for rate in rates if (rate.category, rate.unit) == _INPUT_TOKENS), None)
