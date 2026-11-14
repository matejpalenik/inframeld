from dataclasses import replace
from datetime import UTC, datetime
from decimal import MAX_EMAX, ROUND_UP, Decimal, localcontext
from uuid import UUID

import pytest

from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.dtos.effective_model_settings_dto import (
    EffectiveModelSettingsDTO,
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
from inframeld_backend.shared.application.dtos.model_selection_dto import ModelSelectionDTO
from inframeld_backend.shared.application.dtos.model_token_bound_dto import ModelTokenBoundDTO
from inframeld_backend.shared.application.dtos.reviewed_model_settings_dto import (
    ReviewedModelSettingsDTO,
)
from inframeld_backend.shared.application.dtos.spending_rate_dto import SpendingRateDTO
from inframeld_backend.shared.application.dtos.spending_usage_dto import SpendingUsageDTO
from inframeld_backend.shared.application.enums.embedding_cost_estimate_reason import (
    EmbeddingCostEstimateReason,
)
from inframeld_backend.shared.application.enums.embedding_distance import EmbeddingDistance
from inframeld_backend.shared.application.enums.embedding_normalization import (
    EmbeddingNormalization,
)
from inframeld_backend.shared.application.enums.model_metadata_source_kind import (
    ModelMetadataSourceKind,
)
from inframeld_backend.shared.application.enums.model_role import ModelRole
from inframeld_backend.shared.application.enums.model_token_bound_kind import ModelTokenBoundKind
from inframeld_backend.shared.application.policies.embedding_cost_estimate_policy import (
    EmbeddingCostEstimatePolicy,
)
from inframeld_backend.shared.application.value_objects.model_connection_id import ModelConnectionId

_CAPTURED_AT = datetime(2026, 11, 14, 12, tzinfo=UTC)
_OBSERVED_AT = datetime(2026, 11, 14, 13, tzinfo=UTC)
_INPUT = "upload-review:17"
_FINGERPRINT = "reviewed-embedding-profile-2"
_REVISION = 4
_SELECTION = ModelSelectionDTO(
    ProjectId(UUID(int=1)),
    ModelConnectionId(UUID(int=2)),
    "text-embedding-3-small",
    ModelRole.EMBEDDING,
)
_REVIEWED = ReviewedModelSettingsDTO(
    selection=_SELECTION,
    effective=EffectiveModelSettingsDTO(
        context_tokens=8191,
        token_bound=ModelTokenBoundDTO(ModelTokenBoundKind.EXACT, "test-token-counter", "1"),
        settings=EmbeddingModelSettingsDTO(
            dimensions=1536,
            normalization=EmbeddingNormalization.L2,
            distance=EmbeddingDistance.COSINE,
            document_prefix="",
            query_prefix="",
            expected_provider="openai",
            role=ModelRole.EMBEDDING,
        ),
    ),
    fingerprint=_FINGERPRINT,
)
_CONNECTION = EmbeddingEstimateConnectionDTO(_SELECTION, _FINGERPRINT, _REVISION, True, True)
_QUANTITY = EmbeddingInputQuantityDTO(
    _SELECTION,
    _INPUT,
    _FINGERPRINT,
    "processing-generation:18",
    "token-count:1",
    _OBSERVED_AT,
    SpendingUsageDTO("input", "token", Decimal(12_500)),
)


def _estimate(
    *,
    reviewed: ReviewedModelSettingsDTO = _REVIEWED,
    connection: EmbeddingEstimateConnectionDTO | None = _CONNECTION,
    current_access_revision: int = _REVISION,
    quantity: EmbeddingInputQuantityDTO | None = _QUANTITY,
) -> EmbeddingCostEstimateDTO:
    return EmbeddingCostEstimatePolicy.estimate(
        reviewed=reviewed,
        connection=connection,
        current_access_revision=current_access_revision,
        input_reference=_INPUT,
        captured_at=_CAPTURED_AT,
        quantity=quantity,
    )


def test_official_embedding_advisory_estimate_captures_exact_price_and_quantity() -> None:
    estimate = _estimate()
    assert estimate.amount_usd == Decimal("0.00025")
    assert estimate.reason is None
    assert estimate.quantity == _QUANTITY
    assert estimate.basis is not None
    assert estimate.basis.connection == _CONNECTION
    assert estimate.basis.captured_at == _CAPTURED_AT
    assert estimate.basis.rate == SpendingRateDTO("input", "token", Decimal("0.00000002"))
    source = estimate.basis.catalogue_source
    assert source is not None
    assert source.kind is ModelMetadataSourceKind.CATALOGUE
    assert "v1.108.6" in source.reference
    assert source.revision == "65781e15922f3a7c33b8f991adf56c11d26d0a60"
    assert source.observed_at == datetime(2026, 11, 11, 23, 29, 33, tzinfo=UTC)
    assert _estimate() == estimate


@pytest.mark.parametrize(
    "connection",
    [
        None,
        replace(_CONNECTION, official_openai_destination=False),
        replace(_CONNECTION, official_openai_adapter=False),
        replace(_CONNECTION, settings_fingerprint="another-profile"),
        replace(_CONNECTION, access_revision=_REVISION + 1),
        replace(_CONNECTION, selection=replace(_SELECTION, project_id=ProjectId(UUID(int=3)))),
        replace(
            _CONNECTION, selection=replace(_SELECTION, connection_id=ModelConnectionId(UUID(int=3)))
        ),
        replace(_CONNECTION, selection=replace(_SELECTION, model="openai/text-embedding-3-small")),
        replace(_CONNECTION, selection=replace(_SELECTION, role=ModelRole.RERANKING)),
    ],
)
def test_price_and_override_require_verified_exact_connection_binding(
    connection: EmbeddingEstimateConnectionDTO | None,
) -> None:
    reviewed = replace(_REVIEWED, price_overrides=(SpendingRateDTO("input", "token", Decimal(0)),))
    estimate = _estimate(connection=connection, reviewed=reviewed)
    assert estimate.amount_usd is None
    assert estimate.reason is EmbeddingCostEstimateReason.UNVERIFIED_BINDING
    assert estimate.basis is None


def test_verified_official_binding_cannot_override_a_different_expected_provider() -> None:
    settings = _REVIEWED.effective.settings
    assert isinstance(settings, EmbeddingModelSettingsDTO)
    reviewed = replace(
        _REVIEWED,
        effective=replace(
            _REVIEWED.effective,
            settings=replace(settings, expected_provider="private-gateway"),
        ),
    )
    estimate = _estimate(reviewed=reviewed)
    assert estimate.amount_usd is None
    assert estimate.reason is EmbeddingCostEstimateReason.UNVERIFIED_BINDING
    assert estimate.basis is None


def test_other_models_and_stale_current_revision_do_not_receive_the_official_price() -> None:
    selection = replace(_SELECTION, model="openai/text-embedding-3-small")
    different = _estimate(
        reviewed=replace(_REVIEWED, selection=selection),
        connection=replace(_CONNECTION, selection=selection),
    )
    assert different.reason is EmbeddingCostEstimateReason.UNSUPPORTED_MODEL
    stale = _estimate(current_access_revision=_REVISION + 1)
    assert stale.reason is EmbeddingCostEstimateReason.UNVERIFIED_BINDING


def test_saved_override_wins_and_is_exact_below_accounting_quantum() -> None:
    rate = SpendingRateDTO("input", "token", Decimal("0.0000000000000001234567890123456789"))
    reviewed = replace(
        _REVIEWED, price_overrides=(SpendingRateDTO("output", "token", Decimal(7)), rate)
    )
    with localcontext() as context:
        context.prec = 3
        context.rounding = ROUND_UP
        estimate = _estimate(reviewed=reviewed)
    assert estimate.amount_usd == Decimal("0.0000000000015432098626543209862500")
    assert estimate.basis is not None
    assert estimate.basis.rate == rate
    assert estimate.basis.catalogue_source is None
    assert estimate.basis.connection.settings_fingerprint == _FINGERPRINT
    assert estimate.basis.captured_at == _CAPTURED_AT


def test_zero_override_remains_a_reviewed_rate_without_catalogue_attribution() -> None:
    rate = SpendingRateDTO("input", "token", Decimal(0))
    estimate = _estimate(reviewed=replace(_REVIEWED, price_overrides=(rate,)))
    assert estimate.amount_usd == 0
    assert estimate.basis is not None and estimate.basis.catalogue_source is None
    assert estimate.basis.rate == rate


def test_refinement_keeps_original_price_and_requires_the_same_saved_input() -> None:
    initial = _estimate(quantity=None)
    assert initial.amount_usd is None
    assert initial.reason is EmbeddingCostEstimateReason.MISSING_INPUT_QUANTITY
    assert initial.basis is not None
    for quantity in (
        replace(_QUANTITY, input_reference="other-upload"),
        replace(_QUANTITY, settings_fingerprint="other-profile"),
        replace(_QUANTITY, selection=replace(_SELECTION, project_id=ProjectId(UUID(int=3)))),
        replace(
            _QUANTITY, selection=replace(_SELECTION, connection_id=ModelConnectionId(UUID(int=3)))
        ),
    ):
        rejected = EmbeddingCostEstimatePolicy.refine(initial.basis, quantity)
        assert rejected.reason is EmbeddingCostEstimateReason.MISMATCHED_INPUT_QUANTITY
        assert rejected.quantity is None
    new_rate = SpendingRateDTO("input", "token", Decimal("0.00000003"))
    new_capture = _estimate(reviewed=replace(_REVIEWED, price_overrides=(new_rate,)))
    assert new_capture.amount_usd == Decimal("0.000375")
    refined = EmbeddingCostEstimatePolicy.refine(initial.basis, _QUANTITY)
    assert refined.amount_usd == Decimal("0.00025")
    assert refined.basis is initial.basis
    assert refined.quantity == _QUANTITY
    assert initial.quantity is None


@pytest.mark.parametrize(
    "usage",
    [
        SpendingUsageDTO("output", "token", Decimal(1)),
        SpendingUsageDTO("input", "byte", Decimal(1)),
        SpendingUsageDTO("input", "token", Decimal("1.5")),
    ],
)
def test_saved_quantity_requires_whole_embedding_input_tokens(usage: SpendingUsageDTO) -> None:
    with pytest.raises(ValueError, match="whole input tokens"):
        replace(_QUANTITY, usage=usage)


def test_out_of_range_arithmetic_preserves_evidence_as_unknown() -> None:
    rate = SpendingRateDTO("input", "token", Decimal(f"9e{MAX_EMAX}"))
    estimate = _estimate(reviewed=replace(_REVIEWED, price_overrides=(rate,)))
    assert estimate.amount_usd is None
    assert estimate.reason is EmbeddingCostEstimateReason.AMOUNT_OUT_OF_RANGE
    assert estimate.basis is not None and estimate.basis.rate == rate
    assert estimate.quantity == _QUANTITY
