"""Verify private PDF admission with real PostgreSQL, staging and SeaweedFS."""

import asyncio
import os
from collections.abc import AsyncIterable, AsyncIterator
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

import pytest
from sqlalchemy import Connection, delete, event, func, select
from sqlalchemy.orm import Mapper
from tests.support.artifact_scenarios import MockArtifactCapacityReader
from tests.support.project_creation_scenarios import (
    ProjectCreationSeedDTO,
    create_project,
    seed_project_creator,
)
from tests.support.seaweedfs_fixture import SeaweedFixture, storage_settings

from inframeld_backend.access.domain.enums.access_group_action import AccessGroupAction
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.domain.value_objects.upload_audience import UploadAudience
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.access.infrastructure.rows.access_group_row import AccessGroupRow
from inframeld_backend.access.infrastructure.rows.group_action_grant_row import GroupActionGrantRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.bootstrap.document_upload_composition import open_document_upload
from inframeld_backend.knowledge.application.commands.upload_document_command import (
    UploadDocumentCommand,
)
from inframeld_backend.knowledge.application.dtos.document_upload_result_dto import (
    DocumentUploadResultDTO,
)
from inframeld_backend.knowledge.application.enums.document_upload_state import DocumentUploadState
from inframeld_backend.knowledge.application.errors.document_upload_errors import (
    InvalidPdfUploadError,
)
from inframeld_backend.knowledge.infrastructure.rows.document_group_row import DocumentGroupRow
from inframeld_backend.knowledge.infrastructure.rows.document_row import DocumentRow
from inframeld_backend.knowledge.infrastructure.rows.document_upload_group_row import (
    DocumentUploadGroupRow,
)
from inframeld_backend.knowledge.infrastructure.rows.document_upload_row import DocumentUploadRow
from inframeld_backend.knowledge.infrastructure.rows.document_version_row import DocumentVersionRow
from inframeld_backend.shared.application.dtos.artifact_attempt_dto import ArtifactAttemptDTO
from inframeld_backend.shared.application.dtos.artifact_cleanup_target_dto import (
    ArtifactCleanupTargetDTO,
)
from inframeld_backend.shared.application.dtos.artifact_scope_dto import ArtifactScopeDTO
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ConflictError,
    IdempotencyInProgressError,
    IdempotencyKeyReusedError,
    ResourceNotFoundError,
)
from inframeld_backend.shared.application.value_objects.artifact_attempt_id import ArtifactAttemptId
from inframeld_backend.shared.application.value_objects.artifact_content_digest import (
    ArtifactContentDigest,
)
from inframeld_backend.shared.application.value_objects.artifact_id import ArtifactId
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.job_effect_id import JobEffectId
from inframeld_backend.shared.application.value_objects.request_id import RequestId
from inframeld_backend.shared.infrastructure.mappers.postgres_job_binding_mapper import (
    PostgresJobBindingMapper,
)
from inframeld_backend.shared.infrastructure.repositories.postgres_artifact_attempt_repository import (
    PostgresArtifactAttemptRepository,
)
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.resources.s3_artifact_store import S3ArtifactStore
from inframeld_backend.shared.infrastructure.rows.artifact_attempt_row import ArtifactAttemptRow
from inframeld_backend.shared.infrastructure.rows.artifact_cleanup_obligation_row import (
    ArtifactCleanupObligationRow,
)
from inframeld_backend.shared.infrastructure.rows.artifact_staging_reservation_row import (
    ArtifactStagingReservationRow,
)
from inframeld_backend.shared.infrastructure.rows.artifact_storage_capacity_row import (
    ArtifactStorageCapacityRow,
)
from inframeld_backend.shared.infrastructure.rows.durable_job_row import DurableJobRow
from inframeld_backend.shared.infrastructure.settings.artifact_staging_settings import (
    ArtifactStagingSettings,
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("INFRAMELD_RUN_ARTIFACT_INTEGRATION") != "1",
        reason="Requires the private maintained PostgreSQL and SeaweedFS fixture.",
    ),
]


@dataclass(frozen=True, slots=True)
class _UploadScenario:
    database: Database
    seed: ProjectCreationSeedDTO
    staging: ArtifactStagingSettings
    capacity_reader: MockArtifactCapacityReader
    command: UploadDocumentCommand

    async def upload(
        self,
        chunks: AsyncIterable[bytes],
        *,
        command: UploadDocumentCommand | None = None,
    ) -> DocumentUploadResultDTO:
        async with open_document_upload(
            self.database, self.staging, storage_settings(), self.capacity_reader
        ) as uploader:
            return await uploader.upload(
                access=self.seed.access, command=command or self.command, chunks=chunks
            )


async def _group(
    database: Database,
    seed: ProjectCreationSeedDTO,
    project_id: ProjectId,
    action: AccessGroupAction = AccessGroupAction.ADD_DOCUMENTS,
) -> AccessGroupId:
    group = AccessGroupId(uuid4())
    async with database.session() as session, session.begin():
        session.add(AccessGroupRow(id=group.value, project_id=project_id.value, name="Support"))
        await session.flush()
        session.add(
            GroupActionGrantRow(
                project_id=project_id.value,
                group_id=group.value,
                recipient_principal_id=seed.access.actor_principal_id.value,
                recipient_kind=PrincipalKind.HUMAN,
                action=action.value,
                can_grant=False,
            )
        )
    return group


async def _scenario(database: Database, tmp_path: Path) -> _UploadScenario:
    seed = await seed_project_creator(database)
    project = (await create_project(database, seed)).project.project_id
    group = await _group(database, seed, project)
    staging = tmp_path / "staging"
    staging.mkdir(mode=0o700)
    return _UploadScenario(
        database,
        seed,
        ArtifactStagingSettings(root=staging),
        MockArtifactCapacityReader(),
        UploadDocumentCommand(
            project,
            UploadAudience((group,)),
            "alice-in-wonderland.pdf",
            IdempotencyKey("original"),
            RequestId(uuid4()),
        ),
    )


async def _stream(content: bytes) -> AsyncIterator[bytes]:
    for start in range(0, len(content), 509):
        yield content[start : start + 509]


async def _must_not_read() -> AsyncIterator[bytes]:
    yield pytest.fail("This rejected request must not consume PDF bytes.")


async def test_pdf_admission_recovers_one_original_without_new_capacity_or_put(
    database: Database,
    tmp_path: Path,
    seaweed: SeaweedFixture,
    alice_pdf: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = await _scenario(database, tmp_path)
    content = seaweed.body(alice_pdf)
    put = S3ArtifactStore.put
    sent: list[ArtifactAttemptDTO] = []

    async def observe(
        store: S3ArtifactStore,
        attempt: ArtifactAttemptDTO,
        source: BinaryIO,
        *,
        observation: JobEffectId | None = None,
    ) -> None:
        await put(store, attempt, source, observation=observation)
        sent.append(attempt)

    monkeypatch.setattr(S3ArtifactStore, "put", observe)
    original = await scenario.upload(_stream(content))
    replay_command = replace(scenario.command, request_id=RequestId(uuid4()))
    scenario.capacity_reader.unavailable = True
    assert await scenario.upload(_stream(content), command=replay_command) == original
    with pytest.raises(IdempotencyKeyReusedError):
        await scenario.upload(_stream(content + b"changed"), command=replay_command)
    assert scenario.capacity_reader.reads == 1
    assert len(sent) == 1
    assert sent[0].digest == ArtifactContentDigest.from_content(content)

    async with seaweed.open_store() as store:
        assert b"".join([chunk async for chunk in store.read(sent[0])]) == content
    async with database.session() as session:
        document = await session.get(DocumentRow, original.document_id.value)
        version = await session.get(DocumentVersionRow, original.version_id.value)
        attempted = await session.get(ArtifactAttemptRow, sent[0].attempt_id.value)
        assert document is not None and document.project_id == scenario.command.project_id.value
        assert version is not None and version.document_id == document.id
        assert (version.digest, version.filename, version.length) == (
            sent[0].digest.value,
            scenario.command.filename,
            len(content),
        )
        assert attempted is not None and attempted.published and attempted.put_pending
        groups = tuple(await session.scalars(select(DocumentGroupRow.group_id)))
        assert groups == (scenario.command.audience.group_ids[0].value,)
        assert await session.scalar(select(func.count()).select_from(DocumentUploadRow)) == 1
        assert await session.scalar(select(func.count()).select_from(DurableJobRow)) == 1
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AccessAuditEventRow)
                .where(
                    AccessAuditEventRow.event_type == "document_uploaded",
                    AccessAuditEventRow.correlation_id == original.operation_id.value,
                )
            )
            == 1
        )


async def test_every_group_requires_current_add_before_body_or_reservation(
    database: Database,
    tmp_path: Path,
    seaweed: SeaweedFixture,
) -> None:
    scenario = await _scenario(database, tmp_path)
    update_only = await _group(
        database, scenario.seed, scenario.command.project_id, AccessGroupAction.UPDATE_DOCUMENTS
    )
    command = replace(
        scenario.command,
        audience=UploadAudience((*scenario.command.audience.group_ids, update_only)),
    )

    with pytest.raises(AccessDeniedError):
        await scenario.upload(_must_not_read(), command=command)

    async with database.session() as session:
        assert await session.scalar(select(func.count()).select_from(DocumentUploadRow)) == 0
        assert await session.scalar(select(func.count()).select_from(ArtifactAttemptRow)) == 0
    assert scenario.capacity_reader.reads == 0


@pytest.mark.parametrize("lose_project", [False, True])
async def test_verified_put_cannot_publish_after_current_authority_changes(
    database: Database,
    tmp_path: Path,
    seaweed: SeaweedFixture,
    alice_pdf: bytes,
    monkeypatch: pytest.MonkeyPatch,
    lose_project: bool,
) -> None:
    scenario = await _scenario(database, tmp_path)
    content = seaweed.body(alice_pdf)
    original_put = S3ArtifactStore.put

    async def change_authority(
        store: S3ArtifactStore,
        attempt: ArtifactAttemptDTO,
        source: BinaryIO,
        *,
        observation: JobEffectId | None = None,
    ) -> None:
        await original_put(store, attempt, source, observation=observation)
        async with database.session() as session, session.begin():
            project = await session.get(
                ProjectRow, scenario.command.project_id.value, with_for_update=True
            )
            assert project is not None
            if lose_project:
                project.status = ProjectStatus.DELETING
            else:
                await session.execute(
                    delete(GroupActionGrantRow).where(
                        GroupActionGrantRow.project_id == project.id,
                        GroupActionGrantRow.group_id
                        == scenario.command.audience.group_ids[0].value,
                        GroupActionGrantRow.action == AccessGroupAction.ADD_DOCUMENTS.value,
                    )
                )

    monkeypatch.setattr(S3ArtifactStore, "put", change_authority)
    with pytest.raises(ResourceNotFoundError if lose_project else AccessDeniedError):
        await scenario.upload(_stream(content))

    async with database.session() as session:
        attempt = (await session.scalars(select(ArtifactAttemptRow))).one()
        pending = (await session.scalars(select(DocumentUploadRow))).one()
        assert attempt.put_confirmed and attempt.put_pending and not attempt.published
        assert pending.state == DocumentUploadState.PENDING.value
        assert await session.scalar(select(func.count()).select_from(DocumentVersionRow)) == 0


async def test_malformed_pdf_releases_only_the_document_slot(
    database: Database,
    tmp_path: Path,
    seaweed: SeaweedFixture,
) -> None:
    scenario = await _scenario(database, tmp_path)
    with pytest.raises(InvalidPdfUploadError):
        await scenario.upload(_stream(b"not a PDF"))
    with pytest.raises(ConflictError):
        await scenario.upload(_must_not_read())

    async with database.session() as session:
        original = (await session.scalars(select(DocumentUploadRow))).one()
        attempt = (await session.scalars(select(ArtifactAttemptRow))).one()
        capacity = (await session.scalars(select(ArtifactStorageCapacityRow))).one()
        assert original.state == DocumentUploadState.UNUSED.value
        assert not attempt.put_pending and not attempt.published
        assert capacity.spool_reserved_bytes == 25 * 1024**2
        assert await session.scalar(select(func.count()).select_from(DocumentUploadGroupRow)) == 0
        assert await session.scalar(select(func.count()).select_from(DocumentRow)) == 0


async def test_confirmed_retirement_reconciles_interrupted_pending_occupancy(
    database: Database,
    tmp_path: Path,
    seaweed: SeaweedFixture,
    alice_pdf: bytes,
) -> None:
    scenario = await _scenario(database, tmp_path)

    async def disconnected() -> AsyncIterator[bytes]:
        yield b"%PDF-1.7\n"
        raise OSError("Controlled sender disconnect")

    with pytest.raises(OSError, match="Controlled sender disconnect"):
        await scenario.upload(disconnected())

    async with database.session() as session, session.begin():
        original = (await session.scalars(select(DocumentUploadRow))).one()
        assert original.state == DocumentUploadState.PENDING.value
        original_id = original.operation_id
        obligation = await session.get(ArtifactCleanupObligationRow, original.obligation_id)
        reservation = await session.get(ArtifactStagingReservationRow, original.reservation_id)
        assert obligation is not None and reservation is not None
        # Model the original deadline already elapsed before its normal retirement.
        expired = datetime.now(UTC) - timedelta(seconds=1)
        obligation.transfer_deadline = reservation.expires_at = expired
        await session.flush()
        binding = PostgresJobBindingMapper.cleanup(obligation)
        assert binding.scope == ArtifactScopeDTO(
            scenario.seed.binding.installation_id,
            scenario.seed.organization_id,
            scenario.command.project_id,
        )
        await PostgresArtifactAttemptRepository(session).retire_local(
            binding,
            ArtifactCleanupTargetDTO(
                ArtifactId(original.artifact_id),
                ArtifactAttemptId(original.attempt_id),
                binding.scope,
                None,
                None,
            ),
        )

    with pytest.raises(ConflictError, match="did not admit a Document"):
        await scenario.upload(_must_not_read())
    assert scenario.capacity_reader.reads == 1
    async with database.session() as session:
        original = await session.get(DocumentUploadRow, original_id)
        attempt = (await session.scalars(select(ArtifactAttemptRow))).one()
        assert original is not None and original.state == DocumentUploadState.UNUSED.value
        assert attempt.id == original.attempt_id and attempt.retired and not attempt.put_pending
        assert await session.scalar(select(func.count()).select_from(DurableJobRow)) == 1
        assert await session.scalar(select(func.count()).select_from(DocumentVersionRow)) == 0

    replacement = replace(scenario.command, key=IdempotencyKey("new-operation"))
    result = await scenario.upload(_stream(seaweed.body(alice_pdf)), command=replacement)
    assert result.operation_id.value != original_id
    async with database.session() as session:
        original = await session.get(DocumentUploadRow, original_id)
        capacity = (await session.scalars(select(ArtifactStorageCapacityRow))).one()
        assert original is not None and original.state == DocumentUploadState.UNUSED.value
        assert capacity.spool_reserved_bytes == 2 * 25 * 1024**2
        assert await session.scalar(select(func.count()).select_from(DurableJobRow)) == 2
        assert await session.scalar(select(func.count()).select_from(DocumentVersionRow)) == 1


async def test_audit_failure_rolls_back_publication_and_exact_retry_recovers(
    database: Database,
    tmp_path: Path,
    seaweed: SeaweedFixture,
    alice_pdf: bytes,
) -> None:
    scenario = await _scenario(database, tmp_path)
    content = seaweed.body(alice_pdf)

    def fail_audit(
        mapper: Mapper[AccessAuditEventRow],
        connection: Connection,
        row: AccessAuditEventRow,
    ) -> None:
        if row.event_type == "document_uploaded":
            raise ValueError("Controlled upload audit failure")

    event.listen(AccessAuditEventRow, "before_insert", fail_audit)
    try:
        with pytest.raises(ValueError, match="Controlled upload audit failure"):
            await scenario.upload(_stream(content))
    finally:
        event.remove(AccessAuditEventRow, "before_insert", fail_audit)

    async with database.session() as session:
        attempt = (await session.scalars(select(ArtifactAttemptRow))).one()
        pending = (await session.scalars(select(DocumentUploadRow))).one()
        assert attempt.put_confirmed and not attempt.published
        assert pending.state == DocumentUploadState.PENDING.value
        expected_document = pending.document_id
        assert await session.scalar(select(func.count()).select_from(DocumentRow)) == 0

    scenario.capacity_reader.unavailable = True
    result = await scenario.upload(_stream(content))
    assert result.document_id.value == expected_document
    assert scenario.capacity_reader.reads == 1


async def test_competing_projects_cannot_take_the_last_document_slot(
    database: Database,
    tmp_path: Path,
    seaweed: SeaweedFixture,
    alice_pdf: bytes,
) -> None:
    scenario = await _scenario(database, tmp_path)
    content = seaweed.body(alice_pdf)
    other_project = (
        await create_project(database, scenario.seed, name="other", key="other")
    ).project
    other_group = await _group(database, scenario.seed, other_project.project_id)
    other_command = replace(
        scenario.command,
        project_id=other_project.project_id,
        audience=UploadAudience((other_group,)),
        key=IdempotencyKey("contender"),
    )
    async with database.session() as session, session.begin():
        # Seed committed occupancy without uploading 199 unrelated test objects.
        session.add_all(
            DocumentRow(
                id=uuid4(),
                installation_id=scenario.seed.binding.installation_id.value,
                organization_id=scenario.seed.organization_id.value,
                project_id=scenario.command.project_id.value,
            )
            for _ in range(199)
        )

    reading = asyncio.Event()
    finish = asyncio.Event()

    async def held() -> AsyncIterator[bytes]:
        reading.set()
        await finish.wait()
        yield content

    async with asyncio.timeout(20), asyncio.TaskGroup() as tasks:
        kept = tasks.create_task(scenario.upload(held()))
        try:
            await reading.wait()
            with pytest.raises(IdempotencyInProgressError):
                await scenario.upload(_must_not_read())
            with pytest.raises(ConflictError, match="no available Document slots"):
                await scenario.upload(_must_not_read(), command=other_command)
        finally:
            finish.set()

    assert kept.result().project_id == scenario.command.project_id
    async with database.session() as session:
        assert await session.scalar(select(func.count()).select_from(DocumentRow)) == 200
        assert await session.scalar(select(func.count()).select_from(DocumentVersionRow)) == 1
