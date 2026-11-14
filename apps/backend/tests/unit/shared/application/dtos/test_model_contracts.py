from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest
from pydantic import TypeAdapter, ValidationError

from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.dtos.adopted_model_suggestion_dto import (
    AdoptedModelSuggestionDTO,
)
from inframeld_backend.shared.application.dtos.conflicting_model_property_dto import (
    ConflictingModelPropertyDTO,
)
from inframeld_backend.shared.application.dtos.effective_model_settings_dto import (
    EffectiveModelSettingsDTO,
)
from inframeld_backend.shared.application.dtos.embedding_model_settings_dto import (
    EmbeddingModelSettingsDTO,
)
from inframeld_backend.shared.application.dtos.generation_model_settings_dto import (
    GenerationModelSettingsDTO,
)
from inframeld_backend.shared.application.dtos.known_model_property_dto import KnownModelPropertyDTO
from inframeld_backend.shared.application.dtos.model_call_observation_dto import (
    ModelCallObservationDTO,
)
from inframeld_backend.shared.application.dtos.model_metadata_dto import ModelMetadataDTO
from inframeld_backend.shared.application.dtos.model_metadata_source_dto import (
    ModelMetadataSourceDTO,
)
from inframeld_backend.shared.application.dtos.model_pricing_dto import ModelPricingDTO
from inframeld_backend.shared.application.dtos.model_selection_dto import ModelSelectionDTO
from inframeld_backend.shared.application.dtos.model_token_bound_dto import ModelTokenBoundDTO
from inframeld_backend.shared.application.dtos.portable_model_settings_dto import (
    PortableModelSettingsDTO,
)
from inframeld_backend.shared.application.dtos.reviewed_model_settings_dto import (
    ReviewedModelSettingsDTO,
)
from inframeld_backend.shared.application.dtos.spending_rate_dto import SpendingRateDTO
from inframeld_backend.shared.application.dtos.spending_usage_dto import SpendingUsageDTO
from inframeld_backend.shared.application.dtos.unknown_model_property_dto import (
    UnknownModelPropertyDTO,
)
from inframeld_backend.shared.application.enums.embedding_distance import EmbeddingDistance
from inframeld_backend.shared.application.enums.embedding_normalization import (
    EmbeddingNormalization,
)
from inframeld_backend.shared.application.enums.model_call_outcome import ModelCallOutcome
from inframeld_backend.shared.application.enums.model_metadata_source_kind import (
    ModelMetadataSourceKind,
)
from inframeld_backend.shared.application.enums.model_property_state import ModelPropertyState
from inframeld_backend.shared.application.enums.model_role import ModelRole
from inframeld_backend.shared.application.enums.model_token_bound_kind import ModelTokenBoundKind
from inframeld_backend.shared.application.enums.reviewed_model_property import ReviewedModelProperty
from inframeld_backend.shared.application.value_objects.model_call_id import ModelCallId
from inframeld_backend.shared.application.value_objects.model_connection_id import ModelConnectionId
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.http.mappers.model_settings_mapper import ModelSettingsMapper
from inframeld_backend.shared.http.requests.generation_model_settings_request import (
    GenerationModelSettingsRequest,
)
from inframeld_backend.shared.http.requests.model_rate_request import ModelRateRequest

_PROJECT = ProjectId(UUID("00000000-0000-0000-0000-000000000001"))
_CONNECTION = ModelConnectionId(UUID("00000000-0000-0000-0000-000000000002"))
_OTHER_CONNECTION = ModelConnectionId(UUID("00000000-0000-0000-0000-000000000003"))
_OPERATION = OperationId("operation:query-4")
_CALL = ModelCallId(UUID("00000000-0000-0000-0000-000000000005"))
_PROVIDER = "openai-compatible"
_OBSERVED_AT = datetime(2026, 11, 13, 12, tzinfo=UTC)
_CATALOGUE = ModelMetadataSourceDTO(
    ModelMetadataSourceKind.CATALOGUE, "pinned-model-catalogue", "2026-11-01", _OBSERVED_AT
)
_SERVER = ModelMetadataSourceDTO(
    ModelMetadataSourceKind.SELECTED_SERVER, "gateway-metadata-adapter", "1.2", _OBSERVED_AT
)
_TOKEN_BOUND = ModelTokenBoundDTO(ModelTokenBoundKind.EXACT, "gateway-tokenizer", "v4")
_GENERATION = ModelSelectionDTO(_PROJECT, _CONNECTION, "private/Chat-A", ModelRole.GENERATION)


def _reviewed_generation() -> ReviewedModelSettingsDTO:
    return ReviewedModelSettingsDTO(
        _GENERATION,
        EffectiveModelSettingsDTO(
            32_768,
            _TOKEN_BOUND,
            GenerationModelSettingsDTO(1024, None, False, role=ModelRole.GENERATION),
        ),
        "generation-settings-revision-1",
    )


def _generation_metadata() -> ModelMetadataDTO:
    unknown = UnknownModelPropertyDTO(state=ModelPropertyState.UNKNOWN)
    return ModelMetadataDTO(
        selection=_GENERATION,
        provider=_PROVIDER,
        access_revision=7,
        context_tokens=KnownModelPropertyDTO(131_072, _CATALOGUE, state=ModelPropertyState.KNOWN),
        token_bound=unknown,
        output_tokens=KnownModelPropertyDTO(1024, _SERVER, state=ModelPropertyState.KNOWN),
        temperature_supported=unknown,
        structured_output=KnownModelPropertyDTO(True, _SERVER, state=ModelPropertyState.KNOWN),
        embedding_dimensions=unknown,
        embedding_normalization=unknown,
        embedding_distance=unknown,
        document_prefix=unknown,
        query_prefix=unknown,
        maximum_candidates=unknown,
        pricing=unknown,
    )


def test_refresh_reports_differences_without_editing_reviewed_private_alias() -> None:
    reviewed = _reviewed_generation()
    metadata = _generation_metadata()

    assert metadata.changed_properties(
        reviewed, current_access_revision=7, current_provider=_PROVIDER
    ) == (
        "context_tokens",
        "token_bound",
        "structured_output",
    )
    assert reviewed.effective.context_tokens == 32_768
    assert reviewed.selection.model == "private/Chat-A"
    assert reviewed.suggestions is None
    with_suggestions = replace(reviewed, suggestions=metadata)
    assert with_suggestions.effective.context_tokens == 32_768
    assert with_suggestions.suggestions == metadata
    assert isinstance(metadata.pricing, UnknownModelPropertyDTO)


def test_refresh_refuses_different_connection_or_access_revision() -> None:
    reviewed = _reviewed_generation()
    metadata = _generation_metadata()
    other = replace(reviewed, selection=replace(_GENERATION, connection_id=_OTHER_CONNECTION))

    with pytest.raises(ValueError, match="current model selection"):
        metadata.changed_properties(other, current_access_revision=7, current_provider=_PROVIDER)

    with pytest.raises(ValueError, match="current model selection"):
        metadata.changed_properties(reviewed, current_access_revision=8, current_provider=_PROVIDER)


def test_conflict_retains_sources_and_only_qualified_server_can_prefill() -> None:
    catalogue = KnownModelPropertyDTO(131_072, _CATALOGUE, state=ModelPropertyState.KNOWN)
    server = KnownModelPropertyDTO(32_768, _SERVER, state=ModelPropertyState.KNOWN)
    conflict = ConflictingModelPropertyDTO((catalogue, server), state=ModelPropertyState.CONFLICT)

    assert conflict.alternatives == (catalogue, server)
    assert conflict.prefill() == server
    assert (
        replace(conflict, alternatives=(catalogue, server, replace(server, value=8192))).prefill()
        is None
    )
    with pytest.raises(ValueError, match="distinct"):
        ConflictingModelPropertyDTO(
            (catalogue, replace(catalogue, source=_SERVER)), state=ModelPropertyState.CONFLICT
        )


def test_required_model_limits_fail_closed() -> None:
    with pytest.raises(ValueError, match="positive"):
        replace(_reviewed_generation().effective, context_tokens=0)

    with pytest.raises(ValueError, match="context"):
        replace(
            _reviewed_generation().effective,
            settings=GenerationModelSettingsDTO(
                32_769, Decimal("0"), True, role=ModelRole.GENERATION
            ),
        )

    with pytest.raises(ValueError, match="supported integer range"):
        replace(
            _generation_metadata(),
            context_tokens=KnownModelPropertyDTO(-1, _SERVER, state=ModelPropertyState.KNOWN),
        )


def test_exact_pricing_categories_are_not_collapsed_into_free_execution() -> None:
    rates = (
        SpendingRateDTO("input", "token", Decimal("0.00000015")),
        SpendingRateDTO("cached-input", "token", Decimal("0")),
        SpendingRateDTO("output", "token", Decimal("0.00000045")),
    )
    pricing = KnownModelPropertyDTO(ModelPricingDTO(rates), _SERVER, state=ModelPropertyState.KNOWN)
    metadata = replace(_generation_metadata(), pricing=pricing)

    assert metadata.pricing == pricing
    assert not ModelPricingDTO((rates[1],)).qualified_local_no_external_charge
    reviewed = _reviewed_generation()
    assert "pricing" in metadata.changed_properties(
        reviewed, current_access_revision=7, current_provider=_PROVIDER
    )
    assert "pricing" not in metadata.changed_properties(
        replace(reviewed, suggestions=metadata),
        current_access_revision=7,
        current_provider=_PROVIDER,
    )
    local = ModelPricingDTO((), qualified_local_no_external_charge=True)
    assert local.qualified_local_no_external_charge
    with pytest.raises(ValueError, match="selected server"):
        replace(
            _generation_metadata(),
            pricing=KnownModelPropertyDTO(local, _CATALOGUE, state=ModelPropertyState.KNOWN),
        )
    with pytest.raises(ValueError, match="nonzero"):
        ModelPricingDTO(rates, qualified_local_no_external_charge=True)
    with pytest.raises(ValueError, match="unique"):
        ModelPricingDTO((rates[1], rates[1]))
    with pytest.raises(ValueError, match="unique"):
        ModelPricingDTO(())


def test_call_evidence_cannot_validate_replacement_credentials_or_settings() -> None:
    embedding = EmbeddingModelSettingsDTO(
        1536,
        EmbeddingNormalization.L2,
        EmbeddingDistance.COSINE,
        "doc: ",
        "q: ",
        _PROVIDER,
        role=ModelRole.EMBEDDING,
    )
    reviewed = ReviewedModelSettingsDTO(
        replace(_GENERATION, role=ModelRole.EMBEDDING),
        EffectiveModelSettingsDTO(8192, _TOKEN_BOUND, embedding),
        "embedding-settings-revision-1",
    )
    observed = ModelCallObservationDTO(
        selection=reviewed.selection,
        provider=_PROVIDER,
        operation_id=_OPERATION,
        call_id=_CALL,
        is_preflight=False,
        outcome=ModelCallOutcome.ACCEPTED,
        settings_fingerprint=reviewed.fingerprint,
        access_revision=7,
        credential_revision=3,
        adapter_revision="1.2",
        observed_at=_OBSERVED_AT,
        observed_model="private/Embedding-A",
        provider_model_revision="v2",
        observed_dimensions=1536,
        usage=(SpendingUsageDTO("input", "token", Decimal("42")),),
    )

    assert observed.validates(reviewed, 7, 3, "1.2", _PROVIDER)
    for outcome in (ModelCallOutcome.FAILED, ModelCallOutcome.UNCERTAIN):
        unsuccessful = replace(observed, outcome=outcome)
        assert unsuccessful.usage == observed.usage
        assert not unsuccessful.validates(reviewed, 7, 3, "1.2", _PROVIDER)
        assert replace(unsuccessful, observed_dimensions=None).observed_dimensions is None
    assert not observed.validates(reviewed, 7, 4, "1.2", _PROVIDER)
    assert not observed.validates(reviewed, 8, 3, "1.2", _PROVIDER)
    assert not observed.validates(reviewed, 7, 3, "1.3", _PROVIDER)
    assert not observed.validates(reviewed, 7, 3, "1.2", "other-provider")
    changed_provider = replace(observed, provider="other-provider")
    assert not changed_provider.validates(reviewed, 7, 3, "1.2", "other-provider")
    expected_revision = replace(
        reviewed,
        effective=replace(
            reviewed.effective,
            settings=replace(embedding, expected_model_revision="v2"),
        ),
    )
    assert observed.validates(expected_revision, 7, 3, "1.2", _PROVIDER)
    for revision in ("v3", None):
        mismatched = replace(observed, provider_model_revision=revision)
        assert not mismatched.validates(expected_revision, 7, 3, "1.2", _PROVIDER)
    adapter = TypeAdapter(ModelCallObservationDTO)
    assert (
        adapter.validate_json(adapter.dump_json(observed), strict=True, extra="forbid") == observed
    )
    assert not observed.validates(
        replace(reviewed, fingerprint="different"), 7, 3, "1.2", _PROVIDER
    )
    assert not replace(observed, observed_dimensions=768).validates(
        reviewed, 7, 3, "1.2", _PROVIDER
    )
    assert not observed.validates(
        replace(reviewed, selection=replace(reviewed.selection, connection_id=_OTHER_CONNECTION)),
        7,
        3,
        "1.2",
        _PROVIDER,
    )
    with pytest.raises(FrozenInstanceError):
        observed.__setattr__("observed_dimensions", 768)


def test_native_metadata_round_trips_unknown_and_conflicting_sources() -> None:
    metadata = replace(
        _generation_metadata(),
        context_tokens=ConflictingModelPropertyDTO(
            (
                KnownModelPropertyDTO(131_072, _CATALOGUE, state=ModelPropertyState.KNOWN),
                KnownModelPropertyDTO(32_768, _SERVER, state=ModelPropertyState.KNOWN),
            ),
            state=ModelPropertyState.CONFLICT,
        ),
    )
    adapter = TypeAdapter(ModelMetadataDTO)
    payload = adapter.dump_json(metadata)

    assert adapter.validate_json(payload, strict=True, extra="forbid") == metadata
    with pytest.raises(ValidationError):
        adapter.validate_json(
            payload.replace(b'"unknown"', b'"guessed"', 1), strict=True, extra="forbid"
        )
    with pytest.raises(ValidationError):
        adapter.validate_json(
            payload.replace(b'{"state":"unknown"}', b"{}", 1), strict=True, extra="forbid"
        )
    with pytest.raises(ValidationError):
        adapter.validate_json(
            payload.replace(b'"value":131072', b'"value":true'), strict=True, extra="forbid"
        )


def test_native_portable_settings_distinguish_explicit_zero_and_unset() -> None:
    reviewed = _reviewed_generation()
    unset = PortableModelSettingsDTO(
        "company-gateway", reviewed.selection.model, reviewed.effective
    )
    explicit = replace(
        unset,
        effective=replace(
            unset.effective,
            settings=GenerationModelSettingsDTO(
                1024, Decimal("0"), False, role=ModelRole.GENERATION
            ),
        ),
    )
    adapter = TypeAdapter(PortableModelSettingsDTO)
    unset_json = adapter.dump_json(unset)
    explicit_json = adapter.dump_json(explicit)

    assert adapter.validate_json(unset_json, strict=True, extra="forbid") == unset
    assert adapter.validate_json(explicit_json, strict=True, extra="forbid") == explicit
    assert unset != explicit
    assert b'"temperature":null' in unset_json
    assert b'"temperature":"0"' in explicit_json
    with pytest.raises(ValidationError):
        adapter.validate_json(
            unset_json.replace(b'"temperature":null,', b""), strict=True, extra="forbid"
        )
    with pytest.raises(ValidationError):
        adapter.validate_json(
            b'{"credential":"placeholder",' + unset_json[1:], strict=True, extra="forbid"
        )


def test_model_review_refuses_unknown_bounds_and_wrong_roles() -> None:
    reviewed = _reviewed_generation()
    adapter = TypeAdapter(ReviewedModelSettingsDTO)
    payload = adapter.dump_json(reviewed)

    assert adapter.validate_json(payload, strict=True, extra="forbid") == reviewed
    with pytest.raises(ValidationError, match="matching role"):
        adapter.validate_json(
            payload.replace(b'"role":"generation"', b'"role":"embedding"', 1),
            strict=True,
            extra="forbid",
        )
    with pytest.raises(ValidationError):
        adapter.validate_json(
            payload.replace(b'"context_tokens":32768', b'"context_tokens":null'),
            strict=True,
            extra="forbid",
        )
    with pytest.raises(ValidationError):
        adapter.validate_json(
            payload.replace(b'"kind":"exact"', b'"kind":"estimate"'),
            strict=True,
            extra="forbid",
        )


def test_generation_refresh_accepts_new_current_provider_for_stable_selection() -> None:
    reviewed = _reviewed_generation()
    fresh = replace(_generation_metadata(), provider="ollama", access_revision=8)

    assert "context_tokens" in fresh.changed_properties(reviewed, 8, "ollama")
    with pytest.raises(ValueError, match="current model selection"):
        fresh.changed_properties(reviewed, 8, _PROVIDER)


def test_review_preserves_selected_suggestion_origin_and_explicit_price_override() -> None:
    reviewed = _reviewed_generation()
    original = _generation_metadata()
    alternatives = ConflictingModelPropertyDTO(
        (
            KnownModelPropertyDTO(131_072, _CATALOGUE, state=ModelPropertyState.KNOWN),
            KnownModelPropertyDTO(32_768, _SERVER, state=ModelPropertyState.KNOWN),
        ),
        state=ModelPropertyState.CONFLICT,
    )
    snapshot = replace(original, context_tokens=alternatives)
    adopted = AdoptedModelSuggestionDTO(ReviewedModelProperty.CONTEXT_TOKENS, _SERVER)
    override = SpendingRateDTO("input", "token", Decimal(0))
    adopted_review = replace(
        reviewed, suggestions=snapshot, adopted_suggestions=(adopted,), price_overrides=(override,)
    )

    assert adopted_review.adopted_suggestions == (adopted,)
    assert adopted_review.price_overrides == (override,)
    adapter = TypeAdapter(ReviewedModelSettingsDTO)
    assert (
        adapter.validate_json(adapter.dump_json(adopted_review), strict=True, extra="forbid")
        == adopted_review
    )
    with pytest.raises(ValueError, match="adopted"):
        replace(adopted_review, adopted_suggestions=(replace(adopted, source=_CATALOGUE),))
    with pytest.raises(ValueError, match="unique"):
        replace(adopted_review, price_overrides=(override, override))


def test_native_model_input_rejects_numeric_decimals_and_preserves_exact_strings() -> None:
    precise = b'"0.123456789123456789123456789"'
    settings_json = (
        b'{"role":"generation","output_tokens":1024,"temperature":'
        + precise
        + b',"structured_output":false}'
    )
    rate_json = b'{"category":"input","unit":"token","usd_per_unit":' + precise + b"}"
    settings = GenerationModelSettingsRequest.model_validate_json(settings_json)
    rate = ModelRateRequest.model_validate_json(rate_json)

    expected = Decimal("0.123456789123456789123456789")
    assert ModelSettingsMapper.generation(settings).temperature == expected
    assert ModelSettingsMapper.rate(rate).usd_per_unit == expected
    assert precise.decode() in settings.model_dump_json()
    assert precise.decode() in rate.model_dump_json()
    with pytest.raises(ValidationError, match="decimal string"):
        GenerationModelSettingsRequest.model_validate_json(
            settings_json.replace(precise, precise[1:-1])
        )
    with pytest.raises(ValidationError, match="decimal string"):
        ModelRateRequest.model_validate_json(rate_json.replace(precise, precise[1:-1]))

    with pytest.raises(ValidationError):
        GenerationModelSettingsRequest.model_validate_json(
            settings_json.replace(b'"output_tokens":1024', b'"output_tokens":0')
        )
    with pytest.raises(ValidationError):
        ModelRateRequest.model_validate_json(rate_json.replace(precise, b'"-0.1"'))
    with pytest.raises(ValidationError):
        ModelRateRequest.model_validate_json(rate_json.replace(b'"input"', b'" "'))
