"""Provision the reviewed resources for one uploaded-PDF worker fixture."""

from uuid import UUID, uuid4

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.domain.enums.model_connection_action import ModelConnectionAction
from inframeld_backend.access.domain.enums.model_connection_authentication import (
    ModelConnectionAuthentication,
)
from inframeld_backend.access.domain.enums.model_connection_provider import ModelConnectionProvider
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.project_action import ProjectAction
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.document_version_id import DocumentVersionId
from inframeld_backend.access.infrastructure.rows.group_membership_row import GroupMembershipRow
from inframeld_backend.access.infrastructure.rows.model_connection_action_grant_row import (
    ModelConnectionActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.model_connection_row import ModelConnectionRow
from inframeld_backend.indexing.domain.enums.embedding_profile_action import EmbeddingProfileAction
from inframeld_backend.indexing.domain.enums.processing_profile_action import (
    ProcessingProfileAction,
)
from inframeld_backend.indexing.domain.value_objects.embedding_profile_id import EmbeddingProfileId
from inframeld_backend.indexing.domain.value_objects.processing_profile_id import (
    ProcessingProfileId,
)
from inframeld_backend.indexing.infrastructure.rows.embedding_profile_action_grant_row import (
    EmbeddingProfileActionGrantRow,
)
from inframeld_backend.indexing.infrastructure.rows.embedding_profile_row import EmbeddingProfileRow
from inframeld_backend.indexing.infrastructure.rows.processing_profile_action_grant_row import (
    ProcessingProfileActionGrantRow,
)
from inframeld_backend.indexing.infrastructure.rows.processing_profile_row import (
    ProcessingProfileRow,
)
from inframeld_backend.knowledge.application.value_objects.collection_revision_id import (
    CollectionRevisionId,
)
from inframeld_backend.knowledge.infrastructure.repositories.postgres_collection_repository import (
    PostgresCollectionRepository,
)
from inframeld_backend.pipelines.application.dtos.saved_pipeline_dto import SavedPipelineDTO
from inframeld_backend.pipelines.application.value_objects.pipeline_configuration import (
    PipelineConfiguration,
)
from inframeld_backend.pipelines.domain.enums.pipeline_reranker import PipelineReranker
from inframeld_backend.pipelines.infrastructure.repositories.postgres_pipeline_repository import (
    PostgresPipelineRepository,
)
from inframeld_backend.shared.application.dtos.artifact_scope_dto import ArtifactScopeDTO
from inframeld_backend.shared.application.dtos.generation_model_settings_dto import (
    GenerationModelSettingsDTO,
)
from inframeld_backend.shared.application.dtos.operation_reservation_request_dto import (
    OperationReservationRequestDTO,
)
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.enums.model_role import ModelRole
from inframeld_backend.shared.application.enums.operation_lookup_authority_family import (
    OperationLookupAuthorityFamily,
)
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.model_connection_id import ModelConnectionId
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.application.value_objects.operation_lookup_authority import (
    OperationLookupAuthority,
)
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName
from inframeld_backend.shared.domain.value_objects.submitted_display_name import (
    SubmittedDisplayName,
)
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.writers.postgres_operation_reservation_writer import (
    PostgresOperationReservationWriter,
)


async def seed_pdf_pipeline(
    database: Database,
    *,
    access: AccessContextDTO,
    scope: ArtifactScopeDTO,
    group_id: UUID,
    version_id: DocumentVersionId,
) -> tuple[SavedPipelineDTO, CollectionRevisionId]:
    """Save real Collection and Pipeline originals with scoped fixture profiles."""
    project_id = scope.project_id.value
    organization_id = scope.organization_id.value
    principal_id = access.actor_principal_id.value
    model_id, processing_id, embedding_id = uuid4(), uuid4(), uuid4()
    async with database.session() as session, session.begin():
        session.add_all(
            (
                GroupMembershipRow(
                    project_id=scope.project_id.value,
                    group_id=group_id,
                    principal_id=access.actor_principal_id.value,
                ),
                ModelConnectionRow(
                    id=model_id,
                    name="provider",
                    display_name="Provider",
                    provider=ModelConnectionProvider.OPENAI.value,
                    base_url="https://api.openai.com/v1",
                    api_version=None,
                    authentication=ModelConnectionAuthentication.API_KEY.value,
                    project_id=project_id,
                    organization_id=organization_id,
                ),
                ProcessingProfileRow(
                    id=processing_id,
                    name="alice-prose",
                    display_name="Alice prose",
                    docling_slim_version="2.148.0",
                    docling_core_version="2.106.0",
                    asset_manifest_sha256=(
                        "7ea9f3c967a7bc66d2501e466334e7aef46a639e01a11376888321e0f0a51d0e"
                    ),
                    max_content_tokens=8,
                    merge_peers=False,
                    repeat_table_header=True,
                    ocr_enabled=False,
                    project_id=project_id,
                    organization_id=organization_id,
                ),
            )
        )
        await session.flush()
        session.add_all(
            (
                ModelConnectionActionGrantRow(
                    model_connection_id=model_id,
                    action=ModelConnectionAction.USE.value,
                    project_id=project_id,
                    recipient_principal_id=principal_id,
                    recipient_kind=PrincipalKind.HUMAN,
                    can_grant=True,
                ),
                ProcessingProfileActionGrantRow(
                    processing_profile_id=processing_id,
                    action=ProcessingProfileAction.USE.value,
                    project_id=project_id,
                    recipient_principal_id=principal_id,
                    recipient_kind=PrincipalKind.HUMAN,
                    can_grant=True,
                ),
                EmbeddingProfileRow(
                    id=embedding_id,
                    name="embeddings",
                    display_name="Embeddings",
                    model_connection_id=model_id,
                    model_alias="text-embedding-3-small",
                    expected_provider="openai",
                    expected_model_revision=None,
                    dimensions=1536,
                    normalization="l2",
                    distance="cosine",
                    document_prefix="",
                    query_prefix="",
                    context_tokens=8191,
                    token_bound_kind="exact",
                    token_bound_implementation="tiktoken",
                    token_bound_revision="fixture-revision",
                    settings_fingerprint="a" * 64,
                    vector_index_id=uuid4(),
                    vector_layout_id=uuid4(),
                    placement_version=1,
                    shard_count=2,
                    shard_zero_name="im-v1-" + "a" * 52,
                    shard_one_name="im-v1-" + "b" * 52,
                    project_id=project_id,
                    organization_id=organization_id,
                ),
            )
        )
        await session.flush()
        session.add(
            EmbeddingProfileActionGrantRow(
                embedding_profile_id=embedding_id,
                action=EmbeddingProfileAction.USE.value,
                project_id=project_id,
                recipient_principal_id=principal_id,
                recipient_kind=PrincipalKind.HUMAN,
                can_grant=True,
            )
        )
        await session.flush()
        collections = PostgresCollectionRepository(session)
        collection = await collections.create(
            access=access,
            project_id=scope.project_id,
            name=ResourceName("alice-corpus"),
            display_name=SubmittedDisplayName("Alice corpus"),
            operation_id=OperationId(str(uuid4())),
        )
        selected = await collections.select(
            access=access,
            project_id=scope.project_id,
            collection_id=collection.collection_id,
            expected_base=collection.revision_id,
            version_ids=(version_id,),
            operation_id=OperationId(str(uuid4())),
        )
        writer = PostgresOperationReservationWriter(session)
        original = await writer.reserve(
            OperationReservationRequestDTO(
                principal_id=access.actor_principal_id,
                organization_id=scope.organization_id,
                project_id=scope.project_id,
                method=HttpMethod.POST,
                requested_route=f"/internal/projects/{scope.project_id.value}/pipelines",
                key=IdempotencyKey("alice-pipeline"),
                fingerprint=b"P" * 32,
                lookup_authority=OperationLookupAuthority(
                    OperationLookupAuthorityFamily.PROJECT_ACTION_USE,
                    ActionId(ProjectAction.CREATE_PIPELINES.value),
                ),
            )
        )
        saved = await PostgresPipelineRepository(session).create(
            access=access,
            project_id=scope.project_id,
            name=ResourceName("alice-pipeline"),
            display_name=SubmittedDisplayName("Alice Pipeline"),
            configuration=PipelineConfiguration(
                collection_id=selected.collection_id,
                processing_profile_id=ProcessingProfileId(processing_id),
                embedding_profile_id=EmbeddingProfileId(embedding_id),
                model_connection_id=ModelConnectionId(model_id),
                model_alias="fixture-generation-model",
                prompt="Answer from the permitted evidence.",
                reranker=PipelineReranker.NONE,
                top_k=20,
                max_passages=5,
                generation=GenerationModelSettingsDTO(256, None, False, role=ModelRole.GENERATION),
            ),
            operation_id=original.operation_id,
        )
        await writer.mark_replayable(original.operation_id, OperationReplayKind.SAFE_RESULT)
    return saved.pipeline, selected.revision_id
