from dataclasses import dataclass
from typing import TYPE_CHECKING, NamedTuple

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
from inframeld_backend.shared.application.dtos.model_metadata_source_dto import (
    ModelMetadataSourceDTO,
)
from inframeld_backend.shared.application.dtos.model_pricing_dto import ModelPricingDTO
from inframeld_backend.shared.application.dtos.model_property import ModelProperty
from inframeld_backend.shared.application.dtos.model_selection_dto import ModelSelectionDTO
from inframeld_backend.shared.application.dtos.model_token_bound_dto import ModelTokenBoundDTO
from inframeld_backend.shared.application.dtos.reranking_model_settings_dto import (
    RerankingModelSettingsDTO,
)
from inframeld_backend.shared.application.dtos.unknown_model_property_dto import (
    UnknownModelPropertyDTO,
)
from inframeld_backend.shared.application.enums.embedding_distance import EmbeddingDistance
from inframeld_backend.shared.application.enums.embedding_normalization import (
    EmbeddingNormalization,
)
from inframeld_backend.shared.application.enums.model_metadata_source_kind import (
    ModelMetadataSourceKind,
)
from inframeld_backend.shared.application.enums.model_role import ModelRole
from inframeld_backend.shared.application.enums.reviewed_model_property import ReviewedModelProperty
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation

if TYPE_CHECKING:
    from inframeld_backend.shared.application.dtos.reviewed_model_settings_dto import (
        ReviewedModelSettingsDTO,
    )


class _ReviewedComparison(NamedTuple):
    property: ReviewedModelProperty
    saved: object
    suggestions: tuple[tuple[ModelMetadataSourceDTO, object], ...]

    @staticmethod
    def for_property[T](
        name: ReviewedModelProperty, observation: ModelProperty[T], saved: T
    ) -> "_ReviewedComparison":
        match observation:
            case KnownModelPropertyDTO() as known:
                return _ReviewedComparison(name, saved, ((known.source, known.value),))
            case ConflictingModelPropertyDTO(alternatives=alternatives):
                return _ReviewedComparison(
                    name, saved, tuple((item.source, item.value) for item in alternatives)
                )
            case UnknownModelPropertyDTO():
                return _ReviewedComparison(name, saved, ())


@dataclass(frozen=True, slots=True)
class ModelMetadataDTO:
    """Record advisory properties for one exact selection and observed access revision."""

    selection: ModelSelectionDTO
    provider: str
    access_revision: int
    context_tokens: ModelProperty[int]
    token_bound: ModelProperty[ModelTokenBoundDTO]
    output_tokens: ModelProperty[int]
    temperature_supported: ModelProperty[bool]
    structured_output: ModelProperty[bool]
    embedding_dimensions: ModelProperty[int]
    embedding_normalization: ModelProperty[EmbeddingNormalization]
    embedding_distance: ModelProperty[EmbeddingDistance]
    document_prefix: ModelProperty[str]
    query_prefix: ModelProperty[str]
    maximum_candidates: ModelProperty[int]
    pricing: ModelProperty[ModelPricingDTO]

    def __post_init__(self) -> None:
        RevisionValidation.require(self.access_revision)
        if not self.provider.strip():
            raise ValueError("Metadata requires the provider observed for the selected connection.")

        for observation in (
            self.context_tokens,
            self.output_tokens,
            self.embedding_dimensions,
            self.maximum_candidates,
        ):
            match observation:
                case KnownModelPropertyDTO(value=value):
                    self._require_positive(value)
                case ConflictingModelPropertyDTO(alternatives=alternatives):
                    for alternative in alternatives:
                        self._require_positive(alternative.value)
                case UnknownModelPropertyDTO():
                    pass

        match self.pricing:
            case KnownModelPropertyDTO() as price:
                self._require_pricing_source(price)
            case ConflictingModelPropertyDTO(alternatives=prices):
                for price in prices:
                    self._require_pricing_source(price)
            case UnknownModelPropertyDTO():
                pass

        generation = (self.output_tokens, self.temperature_supported, self.structured_output)
        embedding = (
            self.embedding_dimensions,
            self.embedding_normalization,
            self.embedding_distance,
            self.document_prefix,
            self.query_prefix,
        )
        reranking = (self.maximum_candidates,)
        inapplicable = {
            ModelRole.GENERATION: embedding + reranking,
            ModelRole.EMBEDDING: generation + reranking,
            ModelRole.RERANKING: generation + embedding,
        }
        if any(
            not isinstance(item, UnknownModelPropertyDTO)
            for item in inapplicable[self.selection.role]
        ):
            raise ValueError("Model metadata contains a property outside its selected role.")

    def changed_properties(
        self,
        reviewed: "ReviewedModelSettingsDTO",
        current_access_revision: int,
        current_provider: str,
    ) -> tuple[str, ...]:
        """List differing properties so a consumer can present a diff without applying it."""
        if (
            self.selection != reviewed.selection
            or self.access_revision != current_access_revision
            or self.provider != current_provider
        ):
            raise ValueError(
                "Metadata refresh must use the current model selection and access revision."
            )

        changed = [
            comparison.property.value
            for comparison in self._reviewed_comparisons(reviewed.effective)
            if len(comparison.suggestions) != 1 or comparison.suggestions[0][1] != comparison.saved
        ]
        if isinstance(reviewed.effective.settings, GenerationModelSettingsDTO) and (
            reviewed.effective.settings.temperature is not None
            and (
                not isinstance(self.temperature_supported, KnownModelPropertyDTO)
                or not self.temperature_supported.value
            )
        ):
            changed.append("temperature_supported")
        previous_pricing = (
            reviewed.suggestions.pricing if reviewed.suggestions is not None else None
        )
        if self.pricing != previous_pricing and (
            previous_pricing is not None or not isinstance(self.pricing, UnknownModelPropertyDTO)
        ):
            changed.append("pricing")
        return tuple(changed)

    def has_suggestion(
        self,
        effective: EffectiveModelSettingsDTO,
        property: ReviewedModelProperty,
        source: ModelMetadataSourceDTO,
    ) -> bool:
        """Check whether a source supplied the exact value preserved in reviewed settings."""
        return any(
            candidate_source == source and candidate_value == comparison.saved
            for comparison in self._reviewed_comparisons(effective)
            if comparison.property is property
            for candidate_source, candidate_value in comparison.suggestions
        )

    def _reviewed_comparisons(
        self, effective: EffectiveModelSettingsDTO
    ) -> tuple[_ReviewedComparison, ...]:
        check = _ReviewedComparison.for_property
        props = ReviewedModelProperty
        common = (
            check(props.CONTEXT_TOKENS, self.context_tokens, effective.context_tokens),
            check(props.TOKEN_BOUND, self.token_bound, effective.token_bound),
        )
        match effective.settings:
            case GenerationModelSettingsDTO() as settings:
                return common + (
                    check(props.OUTPUT_TOKENS, self.output_tokens, settings.output_tokens),
                    check(
                        props.STRUCTURED_OUTPUT, self.structured_output, settings.structured_output
                    ),
                )
            case EmbeddingModelSettingsDTO() as settings:
                return common + (
                    check(
                        props.EMBEDDING_DIMENSIONS, self.embedding_dimensions, settings.dimensions
                    ),
                    check(
                        props.EMBEDDING_NORMALIZATION,
                        self.embedding_normalization,
                        settings.normalization,
                    ),
                    check(props.EMBEDDING_DISTANCE, self.embedding_distance, settings.distance),
                    check(props.DOCUMENT_PREFIX, self.document_prefix, settings.document_prefix),
                    check(props.QUERY_PREFIX, self.query_prefix, settings.query_prefix),
                )
            case RerankingModelSettingsDTO() as settings:
                return common + (
                    check(
                        props.MAXIMUM_CANDIDATES,
                        self.maximum_candidates,
                        settings.maximum_candidates,
                    ),
                )

    @staticmethod
    def _require_pricing_source(pricing: KnownModelPropertyDTO[ModelPricingDTO]) -> None:
        if (
            pricing.value.qualified_local_no_external_charge
            and pricing.source.kind is not ModelMetadataSourceKind.SELECTED_SERVER
        ):
            raise ValueError("A qualified local no-charge observation requires a selected server.")

    @staticmethod
    def _require_positive(value: int) -> None:
        RevisionValidation.require(value)
        if value == 0:
            raise ValueError("A model limit or dimension must be positive.")
