"""Exercise Embedding Profile creation, durable layout, and current scope in PostgreSQL."""

import asyncio
import os
from dataclasses import dataclass, replace
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy import Integer, column, delete, event, func, inspect, select, table, update
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from tests.support.postgres import database_session
from tests.support.project_creation_scenarios import create_project, seed_project_creator

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.domain.enums.model_connection_authentication import (
    ModelConnectionAuthentication,
)
from inframeld_backend.access.domain.enums.model_connection_provider import ModelConnectionProvider
from inframeld_backend.access.domain.enums.project_action import ProjectAction
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.access.infrastructure.rows.model_connection_row import ModelConnectionRow
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.indexing.application.commands.create_embedding_profile_command import (
    CreateEmbeddingProfileCommand,
)
from inframeld_backend.indexing.application.dtos.embedding_profile_creation_dto import (
    EmbeddingProfileCreationDTO,
)
from inframeld_backend.indexing.application.services.embedding_profile_creation_service import (
    EmbeddingProfileCreationService,
)
from inframeld_backend.indexing.application.services.embedding_profile_read_service import (
    EmbeddingProfileReadService,
)
from inframeld_backend.indexing.domain.enums.embedding_profile_action import EmbeddingProfileAction
from inframeld_backend.indexing.infrastructure.repositories.postgres_embedding_profile_creation_repository import (
    PostgresEmbeddingProfileCreationRepository,
)
from inframeld_backend.indexing.infrastructure.repositories.postgres_embedding_profile_read_repository import (
    PostgresEmbeddingProfileReadRepository,
)
from inframeld_backend.indexing.infrastructure.rows.embedding_profile_action_grant_row import (
    EmbeddingProfileActionGrantRow,
)
from inframeld_backend.indexing.infrastructure.rows.embedding_profile_creation_result_row import (
    EmbeddingProfileCreationResultRow,
)
from inframeld_backend.indexing.infrastructure.rows.embedding_profile_row import EmbeddingProfileRow
from inframeld_backend.shared.application.dtos.effective_model_settings_dto import (
    EffectiveModelSettingsDTO,
)
from inframeld_backend.shared.application.dtos.embedding_model_settings_dto import (
    EmbeddingModelSettingsDTO,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.dtos.model_selection_dto import ModelSelectionDTO
from inframeld_backend.shared.application.dtos.model_token_bound_dto import ModelTokenBoundDTO
from inframeld_backend.shared.application.enums.embedding_distance import EmbeddingDistance
from inframeld_backend.shared.application.enums.embedding_normalization import (
    EmbeddingNormalization,
)
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.enums.model_role import ModelRole
from inframeld_backend.shared.application.enums.model_token_bound_kind import ModelTokenBoundKind
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ConflictError,
    IdempotencyKeyReusedError,
    ResourceNotFoundError,
)
from inframeld_backend.shared.application.services.idempotency_service import IdempotencyService
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.model_connection_id import ModelConnectionId
from inframeld_backend.shared.application.value_objects.request_fingerprint_key import (
    RequestFingerprintKey,
)
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName
from inframeld_backend.shared.domain.value_objects.submitted_display_name import (
    SubmittedDisplayName,
)
from inframeld_backend.shared.infrastructure.migrations.migration_runner import (
    ALEMBIC_CONFIG_PATH,
    SUPPORTED_SCHEMA_REVISION,
)
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.resources.sqlalchemy_transaction_manager import (
    SqlAlchemyTransactionManager,
)
from inframeld_backend.shared.infrastructure.rows.alembic_version_row import AlembicVersionRow
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)
from inframeld_backend.shared.infrastructure.settings.database_settings import DatabaseSettings
from inframeld_backend.shared.infrastructure.writers.postgres_operation_reservation_writer import (
    PostgresOperationReservationWriter,
)

_PRIOR = "0040_model_dispatch_issuance"
_REVISION = "0041_embedding_profiles"
_TABLES = {
    "embedding_profiles",
    "embedding_profile_action_grants",
    "embedding_profile_creation_results",
}

pytestmark = pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
    reason="Requires isolated PostgreSQL integration services",
)


@dataclass(frozen=True, slots=True)
class EmbeddingProfileScenarioDTO:
    access: AccessContextDTO
    organization_id: OrganizationId
    project_id: ProjectId
    connection_id: ModelConnectionId
    other_project_id: ProjectId

    def command(self) -> CreateEmbeddingProfileCommand:
        return CreateEmbeddingProfileCommand(
            project_id=self.project_id,
            name=ResourceName("support-embeddings"),
            display_name=SubmittedDisplayName("Support embeddings"),
            selection=ModelSelectionDTO(
                self.project_id, self.connection_id, "SupportModel-v1", ModelRole.EMBEDDING
            ),
            effective=EffectiveModelSettingsDTO(
                8192,
                ModelTokenBoundDTO(
                    ModelTokenBoundKind.EXACT, "fixture-tokenizer", "fixture-revision"
                ),
                EmbeddingModelSettingsDTO(
                    dimensions=1536,
                    normalization=EmbeddingNormalization.L2,
                    distance=EmbeddingDistance.COSINE,
                    document_prefix="passage: ",
                    query_prefix="query: ",
                    expected_provider="openai",
                    expected_model_revision="fixture-model-revision",
                    role=ModelRole.EMBEDDING,
                ),
            ),
        )

    def context(self, key: str = "embedding-original") -> IdempotencyContextDTO:
        return IdempotencyContextDTO(
            HttpMethod.POST,
            f"/v1/projects/{self.project_id.value}/embedding-profiles",
            IdempotencyKey(key),
        )


@pytest_asyncio.fixture
async def scenario(database: Database) -> EmbeddingProfileScenarioDTO:
    seed = await seed_project_creator(database)
    project = (await create_project(database, seed)).project
    other_project = (await create_project(database, seed, name="other", key="other")).project
    connection_id = ModelConnectionId(uuid4())
    # A definition can reference this existing connection without its own credential or grant.
    async with database.session() as session, session.begin():
        session.add(
            ModelConnectionRow(
                id=connection_id.value,
                organization_id=project.organization_id.value,
                project_id=project.project_id.value,
                name="embedding-fixture",
                display_name="Embedding Fixture",
                provider=ModelConnectionProvider.OPENAI.value,
                base_url="https://api.openai.com/v1",
                api_version=None,
                authentication=ModelConnectionAuthentication.API_KEY.value,
            )
        )
    return EmbeddingProfileScenarioDTO(
        seed.access,
        project.organization_id,
        project.project_id,
        connection_id,
        other_project.project_id,
    )


def _creator(session: AsyncSession) -> EmbeddingProfileCreationService:
    return EmbeddingProfileCreationService(
        PostgresEmbeddingProfileCreationRepository(session),
        IdempotencyService(PostgresOperationReservationWriter(session)),
        RequestFingerprintService(RequestFingerprintKey(b"E" * 32)),
        transactions=SqlAlchemyTransactionManager(session),
    )


def _config(settings: DatabaseSettings) -> Config:
    config = Config(str(ALEMBIC_CONFIG_PATH))
    config.attributes["database_settings"] = settings
    return config


async def _create(
    database: Database, scenario: EmbeddingProfileScenarioDTO
) -> EmbeddingProfileCreationDTO:
    async with database.session() as session:
        return await _creator(session).create(
            access=scenario.access, command=scenario.command(), context=scenario.context()
        )


async def _hold_project(session: AsyncSession, project: ProjectId) -> int:
    locked = await session.scalar(
        select(ProjectRow.id).where(ProjectRow.id == project.value).with_for_update()
    )
    assert locked == project.value
    holder_pid = await session.scalar(select(func.pg_backend_pid(type_=Integer)))
    assert holder_pid is not None
    return holder_pid


async def _observe_waiter(database: Database, holder_pid: int) -> None:
    pid = column("pid", Integer)
    activity = table("pg_stat_activity", pid)
    query = (
        select(pid)
        .select_from(activity)
        .where(func.pg_blocking_pids(pid, type_=ARRAY(Integer)).contains([holder_pid]))
    )
    async with asyncio.timeout(4):
        while True:
            async with database.session() as observer:
                if await observer.scalar(query):
                    return
            await asyncio.sleep(0.01)


async def _assert_profile_effects(
    database: Database,
    scenario: EmbeddingProfileScenarioDTO,
    result: EmbeddingProfileCreationDTO | None,
) -> None:
    profile_ids: list[UUID] = (
        [] if result is None else [result.profile.layout.embedding_profile_id.value]
    )
    operation_ids = [] if result is None else [result.operation.operation_id.value]
    async with database.session() as session:
        assert (await session.scalars(select(EmbeddingProfileRow.id))).all() == profile_ids
        assert (
            await session.scalars(select(EmbeddingProfileCreationResultRow.operation_id))
        ).all() == operation_ids
        grants = (await session.scalars(select(EmbeddingProfileActionGrantRow))).all()
        assert {
            (row.embedding_profile_id, row.recipient_principal_id, row.action, row.can_grant)
            for row in grants
        } == {
            (profile_id, scenario.access.actor_principal_id.value, action.value, True)
            for profile_id in profile_ids
            for action in EmbeddingProfileAction
        }
        assert (
            await session.scalars(
                select(AccessAuditEventRow.correlation_id).where(
                    AccessAuditEventRow.event_type == "embedding_profile_created"
                )
            )
        ).all() == operation_ids
        assert (
            await session.scalars(
                select(IdempotencyReservationRow.operation_id).where(
                    IdempotencyReservationRow.requested_route == scenario.context().requested_route
                )
            )
        ).all() == operation_ids
        assert await session.scalar(
            select(ProjectRow.access_revision).where(ProjectRow.id == scenario.project_id.value)
        ) == (1 if result is None else result.project_access_revision)


def test_additive_schema_preserves_0040_in_both_directions(
    temporary_postgres_settings: DatabaseSettings,
) -> None:
    config = _config(temporary_postgres_settings)
    command.upgrade(config, _PRIOR)
    with database_session(temporary_postgres_settings) as session:
        original = set(inspect(session.connection()).get_table_names())
        assert "model_dispatch_issuance" in original

    command.upgrade(config, _REVISION)
    with database_session(temporary_postgres_settings) as session:
        assert session.scalar(select(AlembicVersionRow.version_num)) == SUPPORTED_SCHEMA_REVISION
        assert set(inspect(session.connection()).get_table_names()) == original | _TABLES

    command.downgrade(config, _PRIOR)
    with database_session(temporary_postgres_settings) as session:
        assert session.scalar(select(AlembicVersionRow.version_num)) == _PRIOR
        assert set(inspect(session.connection()).get_table_names()) == original


@pytest.mark.asyncio
async def test_creates_reads_and_replays_original_without_restoring_view(
    database: Database, scenario: EmbeddingProfileScenarioDTO
) -> None:
    result = await _create(database, scenario)
    profile_id = result.profile.layout.embedding_profile_id
    project = scenario.project_id
    actor = scenario.access.actor_principal_id.value

    async with database.session() as session:
        reader = EmbeddingProfileReadService(
            SqlAlchemyTransactionManager(session),
            PostgresEmbeddingProfileReadRepository(session, None),
        )
        assert await reader.get(scenario.access, project, profile_id) == result.profile
        with pytest.raises(ResourceNotFoundError):
            await reader.get(scenario.access, scenario.other_project_id, profile_id)

    assert result.profile.reviewed.effective == scenario.command().effective
    assert result.profile.reviewed.selection == scenario.command().selection

    async with database.session() as session, session.begin():
        grants = (
            await session.scalars(
                select(EmbeddingProfileActionGrantRow).where(
                    EmbeddingProfileActionGrantRow.embedding_profile_id == profile_id.value
                )
            )
        ).all()
        assert {(row.recipient_principal_id, row.action, row.can_grant) for row in grants} == {
            (actor, action.value, True) for action in EmbeddingProfileAction
        }
        row = await session.get(EmbeddingProfileRow, profile_id.value)
        assert row is not None
        assert row.vector_index_id == result.profile.vector_index_id.value
        assert row.vector_layout_id == result.profile.layout.layout_id.value
        assert (row.placement_version, row.shard_count) == (1, 2)
        assert (row.shard_zero_name, row.shard_one_name) == result.profile.shard_names
        receipt = await session.get(
            EmbeddingProfileCreationResultRow, result.operation.operation_id.value
        )
        assert receipt is not None and receipt.embedding_profile_id == profile_id.value
        assert (
            receipt.before_revision + 1
            == receipt.project_access_revision
            == result.project_access_revision
        )
        audit = await session.scalar(
            select(AccessAuditEventRow).where(
                AccessAuditEventRow.target_id == profile_id.value,
                AccessAuditEventRow.event_type == "embedding_profile_created",
            )
        )
        assert audit is not None and audit.correlation_id == result.operation.operation_id.value
        await session.execute(
            delete(EmbeddingProfileActionGrantRow).where(
                EmbeddingProfileActionGrantRow.embedding_profile_id == profile_id.value,
                EmbeddingProfileActionGrantRow.action == EmbeddingProfileAction.VIEW.value,
            )
        )
        await session.execute(
            update(ProjectRow)
            .where(ProjectRow.id == project.value)
            .values(access_revision=result.project_access_revision + 1)
        )

    async with database.session() as session:
        replay = await _creator(session).create(
            access=scenario.access, command=scenario.command(), context=scenario.context()
        )
        assert replay == replace(result, operation=replace(result.operation, created=False))
        reader = EmbeddingProfileReadService(
            SqlAlchemyTransactionManager(session),
            PostgresEmbeddingProfileReadRepository(session, None),
        )
        with pytest.raises(ResourceNotFoundError):
            await reader.get(scenario.access, project, profile_id)

    async with database.session() as session, session.begin():
        assert (await session.scalars(select(EmbeddingProfileActionGrantRow.action))).all() == [
            EmbeddingProfileAction.USE.value,
        ]
        await session.execute(
            delete(ProjectActionGrantRow).where(
                ProjectActionGrantRow.project_id == project.value,
                ProjectActionGrantRow.recipient_principal_id == actor,
                ProjectActionGrantRow.action == ProjectAction.CREATE_EMBEDDING_PROFILES.value,
            )
        )
    async with database.session() as session:
        with pytest.raises(AccessDeniedError):
            await _creator(session).create(
                access=scenario.access, command=scenario.command(), context=scenario.context()
            )


@pytest.mark.asyncio
async def test_retained_profile_refuses_downgrade(
    database: Database,
    scenario: EmbeddingProfileScenarioDTO,
    temporary_postgres_settings: DatabaseSettings,
) -> None:
    result = await _create(database, scenario)

    with pytest.raises(RuntimeError, match="Retained Embedding Profiles"):
        command.downgrade(_config(temporary_postgres_settings), _PRIOR)

    async with database.session() as session:
        assert await session.scalar(select(AlembicVersionRow.version_num)) == _REVISION
    await _assert_profile_effects(database, scenario, result)


@pytest.mark.asyncio
async def test_failed_commit_rolls_back_profile_grants_audit_and_reservation(
    database: Database,
    scenario: EmbeddingProfileScenarioDTO,
) -> None:
    def reject_commit(session: Session) -> None:
        raise RuntimeError("Injected commit refusal")

    async with database.session() as session:
        event.listen(session.sync_session, "before_commit", reject_commit, once=True)
        with pytest.raises(RuntimeError, match="Injected commit refusal"):
            await _creator(session).create(
                access=scenario.access,
                command=scenario.command(),
                context=scenario.context(),
            )

    await _assert_profile_effects(database, scenario, None)
    assert (await _create(database, scenario)).operation.created


@pytest.mark.asyncio
async def test_duplicate_name_and_changed_original_leave_first_profile_intact(
    database: Database,
    scenario: EmbeddingProfileScenarioDTO,
) -> None:
    result = await _create(database, scenario)
    original = scenario.command()
    changed = replace(original, display_name=SubmittedDisplayName("Changed title"))

    async with database.session() as session:
        creator = _creator(session)
        with pytest.raises(ConflictError, match="Name is unavailable"):
            await creator.create(
                access=scenario.access, command=original, context=scenario.context("duplicate")
            )
        with pytest.raises(IdempotencyKeyReusedError):
            await creator.create(
                access=scenario.access, command=changed, context=scenario.context()
            )

    await _assert_profile_effects(database, scenario, result)


@pytest.mark.asyncio
@pytest.mark.parametrize("distinct_keys", [False, True], ids=["same-key", "distinct-keys"])
async def test_competing_creates_wait_at_project_gate_and_recover_one_original(
    database: Database,
    scenario: EmbeddingProfileScenarioDTO,
    distinct_keys: bool,
) -> None:
    async def compete(key: str, started: asyncio.Event) -> EmbeddingProfileCreationDTO | None:
        async with database.session() as session:
            started.set()
            try:
                return await _creator(session).create(
                    access=scenario.access,
                    command=scenario.command(),
                    context=scenario.context(key),
                )
            except ConflictError as error:
                assert distinct_keys and "Name is unavailable" in str(error)
                return None

    first_started, second_started = asyncio.Event(), asyncio.Event()
    async with (
        asyncio.timeout(10),
        asyncio.TaskGroup() as tasks,
        database.session() as holder,
        holder.begin(),
    ):
        holder_pid = await _hold_project(holder, scenario.project_id)
        first = tasks.create_task(compete("embedding-original", first_started))
        second_key = "embedding-competitor" if distinct_keys else "embedding-original"
        second = tasks.create_task(compete(second_key, second_started))
        await first_started.wait()
        await second_started.wait()
        await _observe_waiter(database, holder_pid)

    results = first.result(), second.result()
    (original,) = [result for result in results if result is not None and result.operation.created]
    if distinct_keys:
        assert results.count(None) == 1
    else:
        assert replace(original, operation=replace(original.operation, created=False)) in results

    assert original.project_access_revision == 2
    await _assert_profile_effects(database, scenario, original)


@pytest.mark.asyncio
async def test_connection_liveness_is_refreshed_under_project_gate_and_rejects_foreign_selection(
    database: Database,
    scenario: EmbeddingProfileScenarioDTO,
) -> None:
    async def rejected() -> None:
        with pytest.raises(ResourceNotFoundError, match="selected Model Connection"):
            await _create(database, scenario)

    async with asyncio.TaskGroup() as tasks, database.session() as holder, holder.begin():
        holder_pid = await _hold_project(holder, scenario.project_id)
        await holder.execute(
            update(ModelConnectionRow)
            .where(ModelConnectionRow.id == scenario.connection_id.value)
            .values(retired_at=func.now())
        )
        tasks.create_task(rejected())
        await _observe_waiter(database, holder_pid)

    # This valid connection belongs to the other Project even though the caller is its member.
    foreign = ModelConnectionId(uuid4())
    async with database.session() as session, session.begin():
        session.add(
            ModelConnectionRow(
                id=foreign.value,
                organization_id=scenario.organization_id.value,
                project_id=scenario.other_project_id.value,
                name="foreign-fixture",
                display_name="Foreign Fixture",
                provider=ModelConnectionProvider.OPENAI.value,
                base_url="https://api.openai.com/v1",
                api_version=None,
                authentication=ModelConnectionAuthentication.API_KEY.value,
            )
        )
    original = scenario.command()
    foreign_request = replace(
        original, selection=replace(original.selection, connection_id=foreign)
    )
    async with database.session() as session:
        with pytest.raises(ResourceNotFoundError, match="selected Model Connection"):
            await _creator(session).create(
                access=scenario.access, command=foreign_request, context=scenario.context()
            )
    await _assert_profile_effects(database, scenario, None)
