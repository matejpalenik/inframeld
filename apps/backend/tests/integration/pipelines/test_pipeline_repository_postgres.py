"""Check one private saved Pipeline against real scoped PostgreSQL records."""

import asyncio
import os
from dataclasses import dataclass, replace
from typing import override
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import Integer, column, delete, func, select, table
from sqlalchemy.dialects.postgresql import ARRAY
from tests.support.project_creation_scenarios import create_project, seed_project_creator

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.admitted_work_authority_dto import (
    AdmittedWorkAuthorityDTO,
)
from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
    HumanOAuthCredentialBindingDTO,
)
from inframeld_backend.access.application.services.admitted_work_authorization_service import (
    AdmittedWorkAuthorizationService,
)
from inframeld_backend.access.domain.enums.model_connection_action import ModelConnectionAction
from inframeld_backend.access.domain.enums.model_connection_authentication import (
    ModelConnectionAuthentication,
)
from inframeld_backend.access.domain.enums.model_connection_provider import ModelConnectionProvider
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.project_action import ProjectAction
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.readers.postgres_admitted_work_facts_reader import (
    PostgresAdmittedWorkFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_project_scope_lock import (
    PostgresProjectScopeLock,
)
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.access.infrastructure.rows.model_connection_action_grant_row import (
    ModelConnectionActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.model_connection_row import ModelConnectionRow
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.bootstrap.pipeline_pdf_preparation_composition import (
    open_pipeline_pdf_preparation,
)
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
from inframeld_backend.knowledge.application.value_objects.collection_id import CollectionId
from inframeld_backend.knowledge.application.value_objects.collection_revision_id import (
    CollectionRevisionId,
)
from inframeld_backend.knowledge.infrastructure.rows.collection_action_grant_row import (
    CollectionActionGrantRow,
)
from inframeld_backend.knowledge.infrastructure.rows.collection_revision_row import (
    CollectionRevisionRow,
)
from inframeld_backend.knowledge.infrastructure.rows.collection_row import CollectionRow
from inframeld_backend.pipelines.application.dtos.pipeline_creation_dto import PipelineCreationDTO
from inframeld_backend.pipelines.application.value_objects.pipeline_configuration import (
    PipelineConfiguration,
)
from inframeld_backend.pipelines.domain.enums.pipeline_action import PipelineAction
from inframeld_backend.pipelines.domain.enums.pipeline_reranker import PipelineReranker
from inframeld_backend.pipelines.infrastructure.repositories.postgres_pipeline_repository import (
    PostgresPipelineRepository,
)
from inframeld_backend.pipelines.infrastructure.rows.pipeline_action_grant_row import (
    PipelineActionGrantRow,
)
from inframeld_backend.pipelines.infrastructure.rows.pipeline_configuration_revision_row import (
    PipelineConfigurationRevisionRow,
)
from inframeld_backend.pipelines.infrastructure.rows.pipeline_creation_result_row import (
    PipelineCreationResultRow,
)
from inframeld_backend.pipelines.infrastructure.rows.pipeline_row import PipelineRow
from inframeld_backend.releases.infrastructure.readers.postgres_deployment_association_reader import (
    PostgresDeploymentAssociationReader,
)
from inframeld_backend.releases.infrastructure.rows.deployment_row import DeploymentRow
from inframeld_backend.shared.application.commands.restored_job_quarantine_command import (
    RestoredJobQuarantineCommand,
)
from inframeld_backend.shared.application.dtos.artifact_scope_dto import ArtifactScopeDTO
from inframeld_backend.shared.application.dtos.generation_model_settings_dto import (
    GenerationModelSettingsDTO,
)
from inframeld_backend.shared.application.dtos.operation_reservation_request_dto import (
    OperationReservationRequestDTO,
)
from inframeld_backend.shared.application.dtos.product_job_binding_dto import (
    ProductJobBindingDTO,
)
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.enums.model_role import ModelRole
from inframeld_backend.shared.application.enums.operation_lookup_authority_family import (
    OperationLookupAuthorityFamily,
)
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.enums.restored_job_quarantine_intent import (
    RestoredJobQuarantineIntent,
)
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ConflictError,
    InvalidInputError,
    ResourceNotFoundError,
    StaleRevisionError,
)
from inframeld_backend.shared.application.protocols.retained_history_safety_headroom import (
    RetainedHistorySafetyHeadroom,
)
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.job_payload import JobPayload
from inframeld_backend.shared.application.value_objects.model_connection_id import ModelConnectionId
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.application.value_objects.operation_lookup_authority import (
    OperationLookupAuthority,
)
from inframeld_backend.shared.application.value_objects.request_fingerprint_key import (
    RequestFingerprintKey,
)
from inframeld_backend.shared.application.value_objects.request_id import RequestId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName
from inframeld_backend.shared.domain.value_objects.submitted_display_name import (
    SubmittedDisplayName,
)
from inframeld_backend.shared.infrastructure.repositories.postgres_job_store import (
    PostgresJobStore,
)
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.rows.durable_job_row import DurableJobRow
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)
from inframeld_backend.shared.infrastructure.rows.retained_history_reservation_row import (
    RetainedHistoryReservationRow,
)
from inframeld_backend.shared.infrastructure.writers.postgres_operation_reservation_writer import (
    PostgresOperationReservationWriter,
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1", reason="Requires isolated PostgreSQL"
    ),
]
_ACTIONS = (
    "query",
    "inspect-query-traces",
    "build-pipeline",
    "view-pipeline-configuration",
    "edit-pipeline-configuration",
    "delete-pipeline",
    "generate-evaluation-cases",
    "view-evaluation-cases",
    "edit-evaluation-cases",
    "review-evaluation-cases",
    "run-evaluation",
    "inspect-evaluation-results",
    "manage-evaluation-case-audiences",
)
_KEY = IdempotencyKey("fixture-pipeline-original")


@dataclass(frozen=True, slots=True)
class _Scenario:
    access: AccessContextDTO
    scope: ArtifactScopeDTO
    other_project: ProjectId
    configuration: PipelineConfiguration
    binding: HumanOAuthCredentialBindingDTO


@pytest_asyncio.fixture
async def scenario(database: Database) -> _Scenario:
    actor = await seed_project_creator(database)
    project = (await create_project(database, actor)).project.project_id
    other = (
        await create_project(database, actor, name="other", key="other-pipeline")
    ).project.project_id
    organization = actor.organization_id
    installation = actor.binding.installation_id
    scope = ArtifactScopeDTO(installation, organization, project)
    configuration = PipelineConfiguration(
        collection_id=CollectionId(uuid4()),
        processing_profile_id=ProcessingProfileId(uuid4()),
        embedding_profile_id=EmbeddingProfileId(uuid4()),
        model_connection_id=ModelConnectionId(uuid4()),
        model_alias="fixture-generation-model",
        prompt="Answer from the permitted evidence.",
        reranker=PipelineReranker.NONE,
        top_k=20,
        max_passages=5,
        generation=GenerationModelSettingsDTO(256, None, False, role=ModelRole.GENERATION),
    )
    project_id, org_id, install_id = project.value, organization.value, installation.value
    principal = actor.access.actor_principal_id.value
    collection, revision, model, processing, embedding = (
        configuration.collection_id.value,
        uuid4(),
        configuration.model_connection_id.value,
        configuration.processing_profile_id.value,
        configuration.embedding_profile_id.value,
    )
    async with database.session() as session, session.begin():
        session.add_all(
            [
                CollectionRow(
                    id=collection,
                    installation_id=install_id,
                    organization_id=org_id,
                    project_id=project_id,
                    name="corpus",
                    display_name="Corpus",
                    current_revision_id=revision,
                ),
                ModelConnectionRow(
                    id=model,
                    organization_id=org_id,
                    project_id=project_id,
                    name="provider",
                    display_name="Provider",
                    provider=ModelConnectionProvider.OPENAI.value,
                    base_url="https://api.openai.com/v1",
                    api_version=None,
                    authentication=ModelConnectionAuthentication.API_KEY.value,
                ),
                ProcessingProfileRow(
                    id=processing,
                    project_id=project_id,
                    organization_id=org_id,
                    name="processor",
                    display_name="Processor",
                    docling_slim_version="2.148.0",
                    docling_core_version="2.106.0",
                    asset_manifest_sha256="7ea9f3c967a7bc66d2501e466334e7aef46a639e01a11376888321e0f0a51d0e",
                    max_content_tokens=8,
                    merge_peers=False,
                    repeat_table_header=True,
                    ocr_enabled=False,
                ),
            ]
        )
        await session.flush()
        session.add_all(
            [
                CollectionRevisionRow(
                    id=revision,
                    collection_id=collection,
                    installation_id=install_id,
                    organization_id=org_id,
                    project_id=project_id,
                    operation_id="fixture-corpus",
                    actor_principal_id=principal,
                ),
                EmbeddingProfileRow(
                    id=embedding,
                    project_id=project_id,
                    organization_id=org_id,
                    name="embeddings",
                    display_name="Embeddings",
                    model_connection_id=model,
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
                ),
                CollectionActionGrantRow(
                    project_id=project_id,
                    collection_id=collection,
                    recipient_principal_id=principal,
                    recipient_kind=PrincipalKind.HUMAN,
                    action="view-collection",
                    can_grant=True,
                ),
                ModelConnectionActionGrantRow(
                    project_id=project_id,
                    model_connection_id=model,
                    recipient_principal_id=principal,
                    recipient_kind=PrincipalKind.HUMAN,
                    action=ModelConnectionAction.USE.value,
                    can_grant=True,
                ),
                ProcessingProfileActionGrantRow(
                    project_id=project_id,
                    processing_profile_id=processing,
                    recipient_principal_id=principal,
                    recipient_kind=PrincipalKind.HUMAN,
                    action=ProcessingProfileAction.USE.value,
                    can_grant=True,
                ),
            ]
        )
        await session.flush()
        session.add(
            EmbeddingProfileActionGrantRow(
                project_id=project_id,
                embedding_profile_id=embedding,
                recipient_principal_id=principal,
                recipient_kind=PrincipalKind.HUMAN,
                action=EmbeddingProfileAction.USE.value,
                can_grant=True,
            )
        )
    return _Scenario(actor.access, scope, other, configuration, actor.binding)


async def _create(
    database: Database,
    scenario: _Scenario,
    *,
    configuration: PipelineConfiguration | None = None,
    reservation_action: ProjectAction = ProjectAction.CREATE_PIPELINES,
    reservation_route: str | None = None,
) -> PipelineCreationDTO:
    async with database.session() as session, session.begin():
        scope = scenario.scope
        assert (
            await PostgresProjectScopeLock.acquire(
                session, scenario.access.actor_principal_id, scope.project_id, shared=False
            )
            == scope.organization_id.value
        )
        writer = PostgresOperationReservationWriter(session)
        reservation = await writer.reserve(
            OperationReservationRequestDTO(
                principal_id=scenario.access.actor_principal_id,
                organization_id=scope.organization_id,
                project_id=scope.project_id,
                method=HttpMethod.POST,
                requested_route=reservation_route
                or f"/internal/projects/{scope.project_id.value}/pipelines",
                key=_KEY,
                fingerprint=b"p" * 32,
                lookup_authority=OperationLookupAuthority(
                    OperationLookupAuthorityFamily.PROJECT_ACTION_USE,
                    ActionId(reservation_action.value),
                ),
            )
        )
        result = await PostgresPipelineRepository(session).create(
            access=scenario.access,
            project_id=scope.project_id,
            name=ResourceName("support"),
            display_name=SubmittedDisplayName("Support"),
            configuration=scenario.configuration if configuration is None else configuration,
            operation_id=reservation.operation_id,
        )
        assert result.operation_id == reservation.operation_id
        if reservation.created:
            await writer.mark_replayable(reservation.operation_id, OperationReplayKind.SAFE_RESULT)
        return result


async def test_creates_exact_configuration_grants_audit_and_original(
    database: Database, scenario: _Scenario
) -> None:
    original = await _create(database, scenario)
    saved = original.pipeline
    assert saved.configuration == scenario.configuration and saved.revision == 1
    assert (saved.installation_id, saved.organization_id, saved.project_id) == (
        scenario.scope.installation_id,
        scenario.scope.organization_id,
        scenario.scope.project_id,
    )
    assert tuple(action.value for action in original.initial_actions) == _ACTIONS
    assert original.can_grant
    async with database.session() as session, session.begin():
        reservation = await session.get(IdempotencyReservationRow, original.operation_id.value)
        assert reservation is not None and reservation.request_key == _KEY.value
        rows = (await session.scalars(select(PipelineActionGrantRow))).all()
        assert {row.action for row in rows} == set(_ACTIONS)
        assert all(row.can_grant and row.pipeline_id == saved.pipeline_id.value for row in rows)
        audit = await session.scalar(
            select(AccessAuditEventRow).where(
                AccessAuditEventRow.correlation_id == original.operation_id.value
            )
        )
        assert audit is not None and audit.target_id == saved.pipeline_id.value
        assert "Answer from" not in repr(audit.after_values)
        build = await PostgresPipelineRepository(session).load_for_build(
            access=scenario.access,
            project_id=saved.project_id,
            pipeline_id=saved.pipeline_id,
            expected_revision=saved.revision,
        )
        assert build == saved
        assert (
            await session.scalar(
                select(ProjectRow.access_revision).where(ProjectRow.id == saved.project_id.value)
            )
            == original.project_access_revision
        )


async def test_revoked_build_and_exact_replay_do_not_recreate_grants(
    database: Database, scenario: _Scenario
) -> None:
    original = await _create(database, scenario)
    saved = original.pipeline
    async with database.session() as session, session.begin():
        with pytest.raises(StaleRevisionError):
            await PostgresPipelineRepository(session).load_for_build(
                access=scenario.access,
                project_id=saved.project_id,
                pipeline_id=saved.pipeline_id,
                expected_revision=saved.revision + 1,
            )
        await session.execute(
            delete(PipelineActionGrantRow).where(
                PipelineActionGrantRow.pipeline_id == saved.pipeline_id.value,
                PipelineActionGrantRow.action == PipelineAction.BUILD.value,
            )
        )
        await session.execute(
            delete(CollectionActionGrantRow).where(
                CollectionActionGrantRow.collection_id == saved.configuration.collection_id.value
            )
        )
    assert await _create(database, scenario) == original
    with pytest.raises(ConflictError):
        await _create(
            database,
            scenario,
            configuration=replace(scenario.configuration, prompt="A different original request."),
        )

    async with database.session() as session, session.begin():
        with pytest.raises(AccessDeniedError):
            await PostgresPipelineRepository(session).load_for_build(
                access=scenario.access,
                project_id=saved.project_id,
                pipeline_id=saved.pipeline_id,
                expected_revision=saved.revision,
            )
        assert await session.scalar(select(func.count()).select_from(PipelineActionGrantRow)) == 12
        assert (
            await session.scalar(select(func.count()).select_from(PipelineCreationResultRow)) == 1
        )
        assert (
            await session.scalar(select(func.count()).select_from(PipelineConfigurationRevisionRow))
            == 1
        )
        await session.execute(
            delete(ProjectActionGrantRow).where(
                ProjectActionGrantRow.project_id == saved.project_id.value,
                ProjectActionGrantRow.action == ProjectAction.CREATE_PIPELINES.value,
            )
        )
    with pytest.raises(AccessDeniedError):
        await _create(database, scenario)


async def test_missing_collection_keeps_all_pipeline_rows_absent(
    database: Database, scenario: _Scenario
) -> None:
    with pytest.raises(ResourceNotFoundError):
        await _create(
            database,
            scenario,
            configuration=replace(scenario.configuration, collection_id=CollectionId(uuid4())),
        )
    with pytest.raises(ConflictError, match="creation reservation is unavailable"):
        await _create(database, scenario, reservation_action=ProjectAction.CREATE_COLLECTIONS)
    async with database.session() as session:
        for table in (
            PipelineRow,
            PipelineActionGrantRow,
            PipelineCreationResultRow,
            PipelineConfigurationRevisionRow,
        ):
            assert await session.scalar(select(func.count()).select_from(table)) == 0


async def test_same_action_reservation_on_another_route_cannot_create_pipeline(
    database: Database, scenario: _Scenario
) -> None:
    other_route = f"/internal/projects/{scenario.scope.project_id.value}/pipeline-preview"
    with pytest.raises(ConflictError, match="creation reservation is unavailable"):
        await _create(database, scenario, reservation_route=other_route)

    async with database.session() as session:
        assert await session.scalar(select(func.count()).select_from(PipelineRow)) == 0


async def test_no_deployment_check_uses_exact_locked_pipeline_scope(
    database: Database, scenario: _Scenario
) -> None:
    saved = (await _create(database, scenario)).pipeline
    scope = scenario.scope
    waiting_pid: asyncio.Future[int] = asyncio.get_running_loop().create_future()

    async def observe_association() -> None:
        async with database.session() as session, session.begin():
            pid = await session.scalar(select(func.pg_backend_pid(type_=Integer())))
            assert pid is not None
            waiting_pid.set_result(pid)
            with pytest.raises(ConflictError, match="now has a Deployment"):
                await PostgresDeploymentAssociationReader(session).require_absent(
                    scope=scope, pipeline_id=saved.pipeline_id
                )

    async with (
        asyncio.timeout(5),
        asyncio.TaskGroup() as tasks,
        database.session() as session,
        session.begin(),
    ):
        repository = PostgresPipelineRepository(session)
        assert (
            await repository.load_for_build(
                access=scenario.access,
                project_id=scope.project_id,
                pipeline_id=saved.pipeline_id,
                expected_revision=saved.revision,
            )
            == saved
        )
        await PostgresDeploymentAssociationReader(session).require_absent(
            scope=scope, pipeline_id=saved.pipeline_id
        )
        session.add(
            DeploymentRow(
                id=uuid4(),
                installation_id=scope.installation_id.value,
                organization_id=scope.organization_id.value,
                project_id=scope.project_id.value,
                pipeline_id=saved.pipeline_id.value,
            )
        )
        await session.flush()
        holder = await session.scalar(select(func.pg_backend_pid(type_=Integer())))
        assert holder is not None
        tasks.create_task(observe_association())
        waiter = await waiting_pid
        pid_column = column("pid", Integer)
        activity = table("pg_stat_activity", pid_column)
        while True:
            async with database.session() as observer:
                blocked = await observer.scalar(
                    select(pid_column)
                    .select_from(activity)
                    .where(
                        pid_column == waiter,
                        func.pg_blocking_pids(pid_column, type_=ARRAY(Integer())).contains(
                            [holder]
                        ),
                    )
                )
            if blocked is not None:
                break
            await asyncio.sleep(0.01)

    async with database.session() as session, session.begin():
        assert (
            await PostgresProjectScopeLock.acquire(
                session, scenario.access.actor_principal_id, scenario.other_project, shared=False
            )
            == scope.organization_id.value
        )
        with pytest.raises(ResourceNotFoundError):
            await PostgresDeploymentAssociationReader(session).require_absent(
                scope=replace(scope, project_id=scenario.other_project),
                pipeline_id=saved.pipeline_id,
            )


async def test_admitted_build_loses_authority_when_its_exact_pipeline_grant_is_revoked(
    database: Database, scenario: _Scenario
) -> None:
    saved = (await _create(database, scenario)).pipeline
    authority = AdmittedWorkAuthorityDTO(
        principal_id=scenario.access.actor_principal_id,
        principal_kind=PrincipalKind.HUMAN,
        installation_id=saved.installation_id,
        organization_id=saved.organization_id,
        project_id=saved.project_id,
        action_id=ActionId(PipelineAction.BUILD.value),
        human_binding=scenario.binding,
        pipeline_id=saved.pipeline_id,
    )
    request_id = RequestId(uuid4())
    payload = JobPayload("test.pipeline-build", 1, b"reviewed")
    async with database.session() as session, session.begin():
        await AdmittedWorkAuthorizationService(
            PostgresAdmittedWorkFactsReader(session)
        ).require_current(authority)
        writer = PostgresOperationReservationWriter(session)
        original = await writer.reserve(
            OperationReservationRequestDTO(
                principal_id=authority.principal_id,
                organization_id=authority.organization_id,
                project_id=authority.project_id,
                method=HttpMethod.POST,
                requested_route=(
                    f"/internal/projects/{saved.project_id.value}"
                    f"/pipelines/{saved.pipeline_id.value}/builds"
                ),
                key=IdempotencyKey("fixture-build"),
                fingerprint=b"B" * 32,
            )
        )
        admission = await PostgresJobStore(session).admit(
            operation_id=original.operation_id,
            request_id=request_id,
            authority=authority,
            payload=payload,
            capacity=8,
        )
        await writer.mark_replayable(original.operation_id, OperationReplayKind.ASYNC_JOB)

    async with database.session() as session, session.begin():
        store = PostgresJobStore(session)
        durable = await store.find(original.operation_id)
        assert durable is not None and durable.job_id == admission.job_id
        assert durable.binding == ProductJobBindingDTO(original.operation_id, request_id, authority)
        assert durable.payload == payload
        restored = await store.observe_restored_job(
            RestoredJobQuarantineCommand(
                operation_id=OperationId(str(uuid4())),
                expected_installation_id=saved.installation_id,
                job_id=admission.job_id,
                job_operation_id=original.operation_id,
                intent=RestoredJobQuarantineIntent.INSPECT,
            )
        )
        assert restored == replace(durable, observed_at=restored.observed_at)
        authorizer = AdmittedWorkAuthorizationService(PostgresAdmittedWorkFactsReader(session))
        await authorizer.require_current(authority)
        with pytest.raises(AccessDeniedError):
            await authorizer.require_current(replace(authority, project_id=scenario.other_project))

    async with database.session() as session, session.begin():
        assert (
            await PostgresProjectScopeLock.acquire(
                session, authority.principal_id, authority.project_id, shared=False
            )
            == authority.organization_id.value
        )
        await session.execute(
            delete(PipelineActionGrantRow).where(
                PipelineActionGrantRow.pipeline_id == saved.pipeline_id.value,
                PipelineActionGrantRow.recipient_principal_id == authority.principal_id.value,
                PipelineActionGrantRow.action == authority.action_id.value,
            )
        )

    async with database.session() as session, session.begin():
        durable = await PostgresJobStore(session).find(original.operation_id)
        assert durable is not None and isinstance(durable.binding, ProductJobBindingDTO)
        with pytest.raises(AccessDeniedError):
            await AdmittedWorkAuthorizationService(
                PostgresAdmittedWorkFactsReader(session)
            ).require_current(durable.binding.authority)


class _NoHistoryForRejectedBuild(RetainedHistorySafetyHeadroom):
    @override
    async def require_headroom(self, *, installation_id: InstallationId) -> None:
        raise AssertionError("A rejected Build must never reach capacity admission.")


async def test_private_build_rejects_empty_or_stale_selection_before_any_commit(
    database: Database, scenario: _Scenario
) -> None:
    saved = (await _create(database, scenario)).pipeline
    access = AccessContextDTO(scenario.access.actor_principal_id, scenario.binding)
    async with database.session() as session:
        collection = await session.get(CollectionRow, scenario.configuration.collection_id.value)
        assert collection is not None
        reviewed = CollectionRevisionId(collection.current_revision_id)

    async with open_pipeline_pdf_preparation(
        database,
        RequestFingerprintService(
            RequestFingerprintKey(b"fixture build fingerprint key".ljust(32))
        ),
        _NoHistoryForRejectedBuild(),
    ) as admission:
        with pytest.raises(StaleRevisionError):
            await admission.admit(
                access=access,
                project_id=saved.project_id,
                pipeline_id=saved.pipeline_id,
                configuration_revision=saved.revision + 1,
                collection_revision_id=reviewed,
                key=IdempotencyKey("stale-build"),
                request_id=RequestId(uuid4()),
            )
        with pytest.raises(InvalidInputError, match="exactly one selected PDF"):
            await admission.admit(
                access=access,
                project_id=saved.project_id,
                pipeline_id=saved.pipeline_id,
                configuration_revision=saved.revision,
                collection_revision_id=reviewed,
                key=IdempotencyKey("empty-build"),
                request_id=RequestId(uuid4()),
            )

    async with database.session() as session:
        original = await session.scalar(
            select(IdempotencyReservationRow.operation_id).where(
                IdempotencyReservationRow.requested_route
                == f"/internal/projects/{saved.project_id.value}/pipelines/{saved.pipeline_id.value}/builds"
            )
        )
        assert original is None
        assert await session.scalar(select(func.count()).select_from(DurableJobRow)) == 0
        assert (
            await session.scalar(select(func.count()).select_from(RetainedHistoryReservationRow))
            == 0
        )
