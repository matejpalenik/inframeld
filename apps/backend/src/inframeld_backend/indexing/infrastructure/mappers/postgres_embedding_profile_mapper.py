from uuid import UUID

from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.indexing.application.dtos.embedding_profile_dto import EmbeddingProfileDTO
from inframeld_backend.indexing.domain.value_objects.embedding_profile_id import EmbeddingProfileId
from inframeld_backend.indexing.domain.value_objects.vector_index_id import VectorIndexId
from inframeld_backend.indexing.domain.value_objects.vector_layout_id import VectorLayoutId
from inframeld_backend.indexing.domain.value_objects.vector_shard_layout import VectorShardLayout
from inframeld_backend.indexing.infrastructure.rows.embedding_profile_row import EmbeddingProfileRow
from inframeld_backend.shared.application.dtos.effective_model_settings_dto import (
    EffectiveModelSettingsDTO,
)
from inframeld_backend.shared.application.dtos.embedding_model_settings_dto import (
    EmbeddingModelSettingsDTO,
)
from inframeld_backend.shared.application.dtos.model_selection_dto import ModelSelectionDTO
from inframeld_backend.shared.application.dtos.model_token_bound_dto import ModelTokenBoundDTO
from inframeld_backend.shared.application.dtos.reviewed_model_settings_dto import (
    ReviewedModelSettingsDTO,
)
from inframeld_backend.shared.application.enums.embedding_distance import EmbeddingDistance
from inframeld_backend.shared.application.enums.embedding_normalization import (
    EmbeddingNormalization,
)
from inframeld_backend.shared.application.enums.model_role import ModelRole
from inframeld_backend.shared.application.enums.model_token_bound_kind import ModelTokenBoundKind
from inframeld_backend.shared.application.value_objects.model_connection_id import ModelConnectionId
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName
from inframeld_backend.shared.domain.value_objects.submitted_display_name import (
    SubmittedDisplayName,
)


class PostgresEmbeddingProfileMapper:
    """Translate the stored explicit definition and its retained physical layout."""

    @staticmethod
    def profile(row: EmbeddingProfileRow) -> EmbeddingProfileDTO:
        if row.placement_version != 1 or row.shard_count != 2 or not 1 <= row.dimensions <= 1536:
            raise ValueError("The stored Embedding Profile has unsupported settings.")

        project_id = ProjectId(row.project_id)
        profile = EmbeddingProfileDTO(
            name=ResourceName(row.name),
            display_name=SubmittedDisplayName(row.display_name),
            reviewed=ReviewedModelSettingsDTO(
                selection=ModelSelectionDTO(
                    project_id,
                    ModelConnectionId(row.model_connection_id),
                    row.model_alias,
                    ModelRole.EMBEDDING,
                ),
                effective=EffectiveModelSettingsDTO(
                    context_tokens=row.context_tokens,
                    token_bound=ModelTokenBoundDTO(
                        ModelTokenBoundKind(row.token_bound_kind),
                        row.token_bound_implementation,
                        row.token_bound_revision,
                    ),
                    settings=EmbeddingModelSettingsDTO(
                        dimensions=row.dimensions,
                        normalization=EmbeddingNormalization(row.normalization),
                        distance=EmbeddingDistance(row.distance),
                        document_prefix=row.document_prefix,
                        query_prefix=row.query_prefix,
                        expected_provider=row.expected_provider,
                        expected_model_revision=row.expected_model_revision,
                        role=ModelRole.EMBEDDING,
                    ),
                ),
                fingerprint=row.settings_fingerprint,
            ),
            vector_index_id=VectorIndexId(row.vector_index_id),
            layout=VectorShardLayout(
                organization_id=OrganizationId(row.organization_id),
                project_id=project_id,
                embedding_profile_id=EmbeddingProfileId(row.id),
                layout_id=VectorLayoutId(row.vector_layout_id),
                shard_count=row.shard_count,
                version=row.placement_version,
            ),
            shard_names=(row.shard_zero_name, row.shard_one_name),
        )
        if not profile.has_coherent_layout():
            raise ValueError("The stored Embedding Profile has incoherent shard references.")
        return profile

    @staticmethod
    def insert_values(profile: EmbeddingProfileDTO) -> dict[str, UUID | str | int | None]:
        reviewed = profile.reviewed
        selection = reviewed.selection
        effective = reviewed.effective
        embedding = effective.settings
        if (
            not isinstance(embedding, EmbeddingModelSettingsDTO)
            or selection.role is not ModelRole.EMBEDDING
            or reviewed.suggestions is not None
            or reviewed.adopted_suggestions
            or reviewed.price_overrides
        ):
            raise ValueError("Only explicit reviewed embedding settings can be stored.")

        layout = profile.layout
        first_name, second_name = profile.shard_names
        return {
            "id": layout.embedding_profile_id.value,
            "project_id": layout.project_id.value,
            "organization_id": layout.organization_id.value,
            "name": profile.name.value,
            "display_name": profile.display_name.value,
            "model_connection_id": selection.connection_id.value,
            "model_alias": selection.model,
            "expected_provider": embedding.expected_provider,
            "expected_model_revision": embedding.expected_model_revision,
            "dimensions": embedding.dimensions,
            "normalization": embedding.normalization.value,
            "distance": embedding.distance.value,
            "document_prefix": embedding.document_prefix,
            "query_prefix": embedding.query_prefix,
            "context_tokens": effective.context_tokens,
            "token_bound_kind": effective.token_bound.kind.value,
            "token_bound_implementation": effective.token_bound.implementation,
            "token_bound_revision": effective.token_bound.revision,
            "settings_fingerprint": reviewed.fingerprint,
            "vector_index_id": profile.vector_index_id.value,
            "vector_layout_id": layout.layout_id.value,
            "placement_version": layout.version,
            "shard_count": layout.shard_count,
            "shard_zero_name": first_name,
            "shard_one_name": second_name,
        }
