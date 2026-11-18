"""Exercise the private Document erasure fence against PostgreSQL."""

import asyncio
import os
from dataclasses import replace
from datetime import UTC, datetime
from typing import TypedDict
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Integer, column, func, select, table, update
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from tests.support.artifact_scenarios import seed_artifact_scope

from inframeld_backend.access.domain.value_objects.document_version_id import DocumentVersionId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.knowledge.infrastructure.readers.postgres_sealed_pdf_source_reader import (
    PostgresSealedPdfSourceReader,
)
from inframeld_backend.knowledge.infrastructure.rows.document_row import DocumentRow
from inframeld_backend.knowledge.infrastructure.rows.document_version_row import DocumentVersionRow
from inframeld_backend.shared.application.dtos.artifact_attempt_dto import ArtifactAttemptDTO
from inframeld_backend.shared.application.dtos.artifact_scope_dto import ArtifactScopeDTO
from inframeld_backend.shared.application.value_objects.artifact_attempt_id import ArtifactAttemptId
from inframeld_backend.shared.application.value_objects.artifact_content_digest import (
    ArtifactContentDigest,
)
from inframeld_backend.shared.application.value_objects.artifact_id import ArtifactId
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.infrastructure.migrations.migration_runner import (
    ALEMBIC_CONFIG_PATH,
    SUPPORTED_SCHEMA_REVISION,
    run_migrations,
)
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.rows.alembic_version_row import AlembicVersionRow
from inframeld_backend.shared.infrastructure.rows.artifact_attempt_row import ArtifactAttemptRow
from inframeld_backend.shared.infrastructure.settings.database_settings import DatabaseSettings

pytestmark = pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
    reason="Requires PostgreSQL integration services",
)

_ERASURE = OperationId("fixture-document-erasure")


class _ScopeIds(TypedDict):
    installation_id: UUID
    organization_id: UUID
    project_id: UUID


async def _seed_pdf(
    database: Database, scope: ArtifactScopeDTO
) -> tuple[UUID, tuple[tuple[DocumentVersionId, ArtifactAttemptDTO], ...]]:
    document_id = uuid4()
    scope_ids: _ScopeIds = {
        "installation_id": scope.installation_id.value,
        "organization_id": scope.organization_id.value,
        "project_id": scope.project_id.value,
    }
    versions: list[tuple[DocumentVersionId, ArtifactAttemptDTO]] = []
    async with database.session() as session, session.begin():
        session.add(DocumentRow(id=document_id, **scope_ids))
        for pdf in (b"%PDF-1.7\nfirst\n", b"%PDF-1.7\nsecond\n"):
            version = DocumentVersionId(uuid4())
            attempt = ArtifactAttemptDTO(
                ArtifactId(uuid4()),
                ArtifactAttemptId(uuid4()),
                scope,
                len(pdf),
                ArtifactContentDigest.from_content(pdf),
            )
            session.add(
                ArtifactAttemptRow(
                    id=attempt.attempt_id.value,
                    artifact_id=attempt.artifact_id.value,
                    **scope_ids,
                    state="published",
                    length=attempt.length,
                    digest=attempt.digest.value,
                    published=True,
                    put_pending=True,
                    put_confirmed=True,
                )
            )
            versions.append((version, attempt))
        await session.flush()
        session.add_all(
            [
                DocumentVersionRow(
                    id=version.value,
                    **scope_ids,
                    document_id=document_id,
                    attempt_id=attempt.attempt_id.value,
                    filename="fixture.pdf",
                    media_type="application/pdf",
                    length=attempt.length,
                    digest=attempt.digest.value,
                )
                for version, attempt in versions
            ]
        )
    return document_id, tuple(versions)


async def _record_marker(session: AsyncSession, document_id: UUID) -> None:
    # Act as a test-controlled erasure writer without granting any product authority.
    await session.execute(
        update(DocumentRow)
        .where(DocumentRow.id == document_id)
        .values(erasure_operation_id=_ERASURE.value, erasure_blocked_at=datetime.now(UTC))
    )


async def _wait_for_blocked_session(database: Database, holder_pid: int, waiter_pid: int) -> None:
    pid = column("pid", Integer)
    activity = table("pg_stat_activity", pid)
    async with asyncio.timeout(3):
        while True:
            # Each observation uses a new transaction because PostgreSQL caches activity.
            async with database.session() as observer:
                blocked = await observer.scalar(
                    select(pid)
                    .select_from(activity)
                    .where(
                        pid == waiter_pid,
                        func.pg_blocking_pids(pid, type_=ARRAY(Integer())).contains([holder_pid]),
                    )
                )
            if blocked is not None:
                return
            await asyncio.sleep(0.01)


@pytest.mark.asyncio
async def test_marker_blocks_every_version_without_affecting_another_document(
    database: Database,
) -> None:
    scope = await seed_artifact_scope(database)
    document, versions = await _seed_pdf(database, scope)
    _, other = await _seed_pdf(database, scope)
    foreign_scope = replace(scope, project_id=ProjectId(uuid4()))
    async with database.session() as session:
        reader = PostgresSealedPdfSourceReader(session)
        for version, expected in versions:
            assert await reader.read(scope, version) == expected
            assert await reader.read(foreign_scope, version) is None

    async with database.session() as session, session.begin():
        await _record_marker(session, document)

    async with database.session() as session, session.begin():
        reader = PostgresSealedPdfSourceReader(session)
        for version, _ in versions:
            assert await reader.read(scope, version) is None
            assert await reader.read_for_publication(scope, version) is None
        other_version, other_seal = other[0]
        assert await reader.read_for_publication(scope, other_version) == other_seal


@pytest.mark.asyncio
@pytest.mark.parametrize("mark_first", [True, False], ids=["marker-first", "publication-first"])
async def test_publication_and_marker_share_the_document_row(
    database: Database, mark_first: bool
) -> None:
    scope = await seed_artifact_scope(database)
    document, versions = await _seed_pdf(database, scope)
    version, seal = versions[0]
    async with (
        asyncio.timeout(10),
        database.session() as holder,
        holder.begin(),
        database.session() as waiter,
        waiter.begin(),
        asyncio.TaskGroup() as tasks,
    ):
        holder_pid = await holder.scalar(select(func.pg_backend_pid(type_=Integer())))
        waiter_pid = await waiter.scalar(select(func.pg_backend_pid(type_=Integer())))
        assert holder_pid is not None and waiter_pid is not None
        holder_reader = PostgresSealedPdfSourceReader(holder)
        waiter_reader = PostgresSealedPdfSourceReader(waiter)
        if mark_first:
            await _record_marker(holder, document)
            pending = tasks.create_task(waiter_reader.read_for_publication(scope, version))
        else:
            assert await holder_reader.read_for_publication(scope, version) == seal
            pending = tasks.create_task(_record_marker(waiter, document))
        # Yield one turn before observing the real blocked connection.
        await asyncio.sleep(0)
        assert not pending.done(), "The competing operation bypassed the Document row lock."
        try:
            await _wait_for_blocked_session(database, holder_pid, waiter_pid)
        except TimeoutError:
            pytest.fail("The competing operation did not wait on the Document row.")
        await holder.commit()
        assert await pending is None
    async with database.session() as session:
        assert await PostgresSealedPdfSourceReader(session).read(scope, version) is None


@pytest.mark.asyncio
async def test_upgrade_keeps_legacy_source_live_and_downgrade_cannot_remove_a_marker(
    database: Database, temporary_postgres_settings: DatabaseSettings
) -> None:
    scope = await seed_artifact_scope(database)
    document, versions = await _seed_pdf(database, scope)
    config = Config(str(ALEMBIC_CONFIG_PATH))
    config.attributes["database_settings"] = temporary_postgres_settings

    command.downgrade(config, "0041_embedding_profiles")
    run_migrations(temporary_postgres_settings)
    async with database.session() as session, session.begin():
        reader = PostgresSealedPdfSourceReader(session)
        for version, seal in versions:
            assert await reader.read(scope, version) == seal
        await _record_marker(session, document)

    with pytest.raises(RuntimeError, match="Retained Document erasure"):
        command.downgrade(config, "0041_embedding_profiles")

    async with database.session() as session, session.begin():
        assert (
            await session.scalar(select(AlembicVersionRow.version_num)) == SUPPORTED_SCHEMA_REVISION
        )
        for version, _ in versions:
            assert await PostgresSealedPdfSourceReader(session).read(scope, version) is None
        with pytest.raises(IntegrityError):
            async with session.begin_nested():
                await session.execute(
                    update(DocumentRow)
                    .where(DocumentRow.id == document)
                    .values(erasure_operation_id=None)
                )
        assert (
            await session.scalar(
                select(DocumentRow.erasure_operation_id).where(DocumentRow.id == document)
            )
            == _ERASURE.value
        )


@pytest.mark.asyncio
async def test_publication_read_requires_an_active_read_committed_transaction(
    database: Database,
) -> None:
    scope = await seed_artifact_scope(database)
    _, versions = await _seed_pdf(database, scope)
    version, _ = versions[0]
    async with database.session() as session:
        reader = PostgresSealedPdfSourceReader(session)
        with pytest.raises(RuntimeError, match="transaction"):
            await reader.read_for_publication(scope, version)
        async with session.begin():
            await session.connection(execution_options={"isolation_level": "REPEATABLE READ"})
            with pytest.raises(RuntimeError, match="READ COMMITTED"):
                await reader.read_for_publication(scope, version)
