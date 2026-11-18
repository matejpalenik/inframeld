"""Verify human PDF admission through the registered API and the production worker."""

import asyncio
import os
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import datetime, timedelta
from functools import partial
from pathlib import Path
from typing import BinaryIO, override
from uuid import UUID, uuid4

import httpx2
import pytest
from alembic import command
from alembic.config import Config
from pydantic import HttpUrl, TypeAdapter
from sqlalchemy import DateTime, func, select
from tests.support.application_worker_process import application_worker_process
from tests.support.artifact_scenarios import MockArtifactCapacityReader
from tests.support.authentication_evidence import MockAuthenticationEvidence
from tests.support.first_administrator_bootstrap_scenarios import (
    bootstrap_scenario,
    bootstrap_service,
)
from tests.support.integration_services import KRATOS_ADMIN_URL, KRATOS_PUBLIC_URL
from tests.support.kratos_browser import create_browser, register_human
from tests.support.pipeline_pdf_preparation_scenarios import seed_pdf_pipeline
from tests.support.postgres import database_session
from tests.support.project_creation_scenarios import ProjectCreationSeedDTO, create_project
from tests.support.seaweedfs_fixture import SeaweedFixture, storage_settings

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.services.admitted_work_authorization_service import (
    AdmittedWorkAuthorizationService,
)
from inframeld_backend.access.domain.enums.access_group_action import AccessGroupAction
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.value_objects.document_version_id import DocumentVersionId
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.readers.postgres_admitted_work_facts_reader import (
    PostgresAdmittedWorkFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_project_scope_lock import (
    PostgresProjectScopeLock,
)
from inframeld_backend.access.infrastructure.rows.access_group_row import AccessGroupRow
from inframeld_backend.access.infrastructure.rows.group_action_grant_row import GroupActionGrantRow
from inframeld_backend.access.infrastructure.settings.csrf_settings import CSRFSettings
from inframeld_backend.access.infrastructure.settings.kratos_settings import KratosSettings
from inframeld_backend.bootstrap.application_factory import create_app
from inframeld_backend.bootstrap.application_settings import get_settings
from inframeld_backend.bootstrap.application_worker import run_application_worker
from inframeld_backend.bootstrap.application_worker_application_settings import (
    ApplicationWorkerApplicationSettings,
)
from inframeld_backend.bootstrap.application_worker_operations import ApplicationWorkerOperations
from inframeld_backend.bootstrap.document_upload_composition import open_document_upload
from inframeld_backend.bootstrap.pipeline_pdf_preparation_composition import (
    create_pipeline_pdf_preparation_handler,
    open_pipeline_pdf_preparation,
)
from inframeld_backend.indexing.application.dtos.parsed_pdf_dto import ParsedPdfDTO
from inframeld_backend.indexing.domain.value_objects.docling_processing_definition import (
    DoclingProcessingDefinition,
)
from inframeld_backend.indexing.infrastructure.repositories.postgres_pipeline_pdf_preparation_records import (
    PostgresPipelinePdfPreparationRecords,
)
from inframeld_backend.indexing.infrastructure.resources.unix_pdf_parser import UnixPdfParser
from inframeld_backend.indexing.infrastructure.rows.parsed_pdf_chunk_row import ParsedPdfChunkRow
from inframeld_backend.indexing.infrastructure.rows.parsed_pdf_generation_row import (
    ParsedPdfGenerationRow,
)
from inframeld_backend.knowledge.infrastructure.readers.postgres_sealed_pdf_source_reader import (
    PostgresSealedPdfSourceReader,
)
from inframeld_backend.knowledge.infrastructure.rows.document_row import DocumentRow
from inframeld_backend.knowledge.infrastructure.rows.document_upload_row import DocumentUploadRow
from inframeld_backend.knowledge.infrastructure.rows.document_version_row import DocumentVersionRow
from inframeld_backend.pipelines.application.value_objects.pipeline_pdf_preparation_input import (
    PipelinePdfPreparationInput,
)
from inframeld_backend.shared.application.dtos.artifact_attempt_dto import ArtifactAttemptDTO
from inframeld_backend.shared.application.dtos.artifact_scope_dto import ArtifactScopeDTO
from inframeld_backend.shared.application.dtos.product_job_binding_dto import ProductJobBindingDTO
from inframeld_backend.shared.application.errors.application_errors import AccessDeniedError
from inframeld_backend.shared.application.protocols.retained_history_safety_headroom import (
    RetainedHistorySafetyHeadroom,
)
from inframeld_backend.shared.application.services.artifact_cleanup_job_handler import (
    ArtifactCleanupJobHandler,
)
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.artifact_attempt_id import ArtifactAttemptId
from inframeld_backend.shared.application.value_objects.artifact_content_digest import (
    ArtifactContentDigest,
)
from inframeld_backend.shared.application.value_objects.artifact_id import ArtifactId
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.job_effect_id import JobEffectId
from inframeld_backend.shared.application.value_objects.job_id import JobId
from inframeld_backend.shared.application.value_objects.request_fingerprint_key import (
    RequestFingerprintKey,
)
from inframeld_backend.shared.application.value_objects.request_id import RequestId
from inframeld_backend.shared.domain.enums.job_status import JobStatus
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.infrastructure.migrations.migration_runner import (
    ALEMBIC_CONFIG_PATH,
    run_migrations,
)
from inframeld_backend.shared.infrastructure.readers.postgres_artifact_staging_reservation_reader import (
    PostgresArtifactStagingReservationReader,
)
from inframeld_backend.shared.infrastructure.repositories.postgres_job_store import (
    PostgresJobStore,
)
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.resources.private_artifact_staging import (
    PrivateArtifactStaging,
)
from inframeld_backend.shared.infrastructure.resources.s3_artifact_store import S3ArtifactStore
from inframeld_backend.shared.infrastructure.rows.alembic_version_row import AlembicVersionRow
from inframeld_backend.shared.infrastructure.rows.artifact_attempt_row import ArtifactAttemptRow
from inframeld_backend.shared.infrastructure.rows.artifact_cleanup_target_row import (
    ArtifactCleanupTargetRow,
)
from inframeld_backend.shared.infrastructure.rows.artifact_staging_reservation_row import (
    ArtifactStagingReservationRow,
)
from inframeld_backend.shared.infrastructure.rows.artifact_storage_capacity_row import (
    ArtifactStorageCapacityRow,
)
from inframeld_backend.shared.infrastructure.rows.durable_job_attempt_row import (
    DurableJobAttemptRow,
)
from inframeld_backend.shared.infrastructure.rows.durable_job_effect_row import DurableJobEffectRow
from inframeld_backend.shared.infrastructure.rows.durable_job_row import DurableJobRow
from inframeld_backend.shared.infrastructure.rows.retained_history_reservation_row import (
    RetainedHistoryReservationRow,
)
from inframeld_backend.shared.infrastructure.settings.artifact_staging_settings import (
    ArtifactStagingSettings,
)
from inframeld_backend.shared.infrastructure.settings.database_settings import DatabaseSettings
from inframeld_backend.shared.infrastructure.settings.job_settings import JobSettings

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("INFRAMELD_RUN_ARTIFACT_INTEGRATION") != "1"
        or os.getenv("INFRAMELD_RUN_KRATOS_INTEGRATION") != "1",
        reason="Requires the maintained PostgreSQL, Kratos and SeaweedFS fixture.",
    ),
]
_AUTHORITY = IdentityAuthority("kratos:test")
_ORIGIN = "http://upload-test-ui.invalid"
_LEGACY_REVISION = "0038_document_upload"
_REPLAY_REVISION = "0039_document_upload_replay"


async def _must_not_read() -> AsyncIterator[bytes]:
    yield pytest.fail("A request without Add must never consume PDF bytes.")


def _migrate_legacy_receipt(
    settings: DatabaseSettings, original: DocumentUploadRow, past_deadline: datetime
) -> None:
    """Reject erasure of a saved receipt deadline and preserve the legacy upload row."""
    config = Config(str(ALEMBIC_CONFIG_PATH))
    config.attributes["database_settings"] = settings
    revision = select(AlembicVersionRow.version_num)
    command.downgrade(config, _REPLAY_REVISION)
    with pytest.raises(RuntimeError, match="Retained upload receipt deadlines"):
        command.downgrade(config, _LEGACY_REVISION)
    with database_session(settings) as session, session.begin():
        assert session.scalar(revision) == _REPLAY_REVISION
        retained = session.get(DocumentUploadRow, original.operation_id)
        assert retained is not None and retained.replay_expires_at == past_deadline
        retained.replay_expires_at = None

    command.downgrade(config, _LEGACY_REVISION)
    legacy = select(
        DocumentUploadRow.operation_id,
        DocumentUploadRow.document_id,
        DocumentUploadRow.version_id,
        DocumentUploadRow.attempt_id,
        DocumentUploadRow.state,
    ).where(DocumentUploadRow.operation_id == original.operation_id)
    with database_session(settings) as session:
        assert session.scalar(revision) == _LEGACY_REVISION
        assert session.execute(legacy).one() == (
            original.operation_id,
            original.document_id,
            original.version_id,
            original.attempt_id,
            "admitted",
        )
    run_migrations(settings)


@pytest.mark.parametrize(
    "parse_uploaded_pdf",
    [
        pytest.param(False, id="upload"),
        pytest.param(
            True,
            id="native-parser",
            marks=pytest.mark.skipif(
                os.getenv("INFRAMELD_TEST_PDF_PARSER_SOCKET") != "1",
                reason="Requires the separately confined native parser socket.",
            ),
        ),
    ],
)
async def test_registered_human_upload_preserves_original_after_worker_settlement(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
    tmp_path: Path,
    seaweed: SeaweedFixture,
    alice_pdf: bytes,
    monkeypatch: pytest.MonkeyPatch,
    parse_uploaded_pdf: bool,
) -> None:
    staging = ArtifactStagingSettings(root=tmp_path / "staging")
    staging.root.mkdir(mode=0o700)
    capacity = MockArtifactCapacityReader()
    settings = get_settings().model_copy(
        update={
            "database": temporary_postgres_settings,
            "kratos": KratosSettings(
                public_url=HttpUrl(KRATOS_PUBLIC_URL),
                admin_url=HttpUrl(KRATOS_ADMIN_URL),
                authority=_AUTHORITY,
            ),
            "csrf": CSRFSettings(trusted_origins=(HttpUrl(_ORIGIN),)),
        },
    )
    open_uploader = partial(
        open_document_upload,
        staging_settings=staging,
        storage_settings=storage_settings(),
        capacity_reader=capacity,
    )
    app = create_app(settings, open_document_uploader=open_uploader)
    put = S3ArtifactStore.put
    sent: list[ArtifactAttemptId] = []

    async def observe_put(
        store: S3ArtifactStore,
        attempt: ArtifactAttemptDTO,
        source: BinaryIO,
        *,
        observation: JobEffectId | None = None,
    ) -> None:
        sent.append(attempt.attempt_id)
        await put(store, attempt, source, observation=observation)

    monkeypatch.setattr(S3ArtifactStore, "put", observe_put)
    async with create_browser() as browser:
        alice = await register_human(browser)
    bootstrap = await bootstrap_scenario(
        database, identity=VerifiedHumanIdentityDTO(_AUTHORITY, alice.subject)
    )
    binding = bootstrap.binding
    async with database.session() as session:
        admitted = await bootstrap_service(session, binding).bootstrap(bootstrap.command)
    seed = ProjectCreationSeedDTO(
        AccessContextDTO(
            admitted.recipient_id,
            MockAuthenticationEvidence.browser(
                binding.identity, installation_id=binding.installation_id, version=binding.version
            ),
        ),
        admitted.organization_id,
        admitted.access_revision,
        binding,
    )
    project = (await create_project(database, seed)).project.project_id
    group = uuid4()
    async with database.session() as session, session.begin():
        session.add(AccessGroupRow(id=group, project_id=project.value, name="Support"))

    async with (
        app.router.lifespan_context(app),
        httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app), base_url=_ORIGIN, timeout=10
        ) as api,
    ):
        path = f"/v1/projects/{project.value}/documents"
        filename = "Alice au pays des merveilles + été.pdf"
        params = {"groupIds": str(group), "filename": filename}
        headers = {
            "Content-Type": "application/pdf",
            "Cookie": f"ory_kratos_session={alice.credential.value}",
            "Idempotency-Key": "alice-original-upload",
            "Origin": _ORIGIN,
            "X-Inframeld-CSRF": "1",
        }
        denied = await api.post(path, params=params, headers=headers, content=_must_not_read())
        assert denied.status_code == 403
        assert capacity.reads == 0
        async with database.session() as session, session.begin():
            assert await session.scalar(select(func.count()).select_from(DocumentUploadRow)) == 0
            session.add(
                GroupActionGrantRow(
                    project_id=project.value,
                    group_id=group,
                    recipient_principal_id=admitted.recipient_id.value,
                    recipient_kind=PrincipalKind.HUMAN,
                    action=AccessGroupAction.ADD_DOCUMENTS.value,
                    can_grant=False,
                )
            )

        content = seaweed.body(alice_pdf)
        clock = select(func.clock_timestamp(type_=DateTime(timezone=True)))
        async with database.session() as session:
            earliest = await session.scalar(clock)
        first = await api.post(path, params=params, headers=headers, content=content)
        assert first.status_code == 201
        receipt_type = TypeAdapter(dict[str, str | None])
        receipt = receipt_type.validate_json(first.content)
        operation_id, expiry = receipt["operationId"], receipt["idempotencyExpiresAt"]
        assert operation_id is not None and expiry is not None
        deadline = datetime.fromisoformat(expiry)
        digest = ArtifactContentDigest.from_content(content)
        async with database.session() as session:
            latest = await session.scalar(clock)
            assert earliest is not None and latest is not None
            guarantee = timedelta(hours=24)
            assert earliest + guarantee <= deadline <= latest + guarantee
            original = await session.get(DocumentUploadRow, operation_id)
            assert original is not None
            version = await session.get(DocumentVersionRow, original.version_id)
            assert version is not None and version.digest == digest.value
            assert (version.filename, version.length, version.media_type) == (
                filename,
                len(content),
                "application/pdf",
            )
            assert original.replay_expires_at == deadline
            assert receipt == {
                "operationId": operation_id,
                "projectId": str(project.value),
                "documentId": str(original.document_id),
                "documentVersionId": str(version.id),
                "idempotencyExpiresAt": expiry,
            }
            before = await session.get(DurableJobRow, original.cleanup_job_id)
            assert before is not None and before.status == JobStatus.QUEUED.value
            reserved = await session.get(ArtifactStagingReservationRow, original.reservation_id)
            assert reserved is not None and reserved.remote_reserved_bytes > 0

        monkeypatch.setenv("INFRAMELD_ARTIFACT_STAGING__ROOT", str(staging.root))
        async with application_worker_process(temporary_postgres_settings, artifact_cleanup=True):
            async with asyncio.timeout(10):
                while True:
                    async with database.session() as session:
                        job = await session.get(DurableJobRow, original.cleanup_job_id)
                        if job is not None and job.status == JobStatus.SUCCEEDED.value:
                            break
                    await asyncio.sleep(0.02)

        capacity_query = select(
            ArtifactStorageCapacityRow.spool_reserved_bytes,
            ArtifactStorageCapacityRow.protected_reserved_bytes,
            ArtifactStorageCapacityRow.occupied_bytes,
        ).where(ArtifactStorageCapacityRow.installation_id == binding.installation_id.value)
        async with database.session() as session:
            settled_capacity = (await session.execute(capacity_query)).one()
        capacity.unavailable = True
        replay = await api.post(path, params=params, headers=headers, content=content)
        assert replay.status_code == 201 and replay.content == first.content
        conflict = await api.post(
            path, params=params, headers=headers, content=content + b"changed"
        )
        assert conflict.status_code == 409
        assert conflict.json()["code"] == "idempotency_key_reused"
        async with database.session() as session, session.begin():
            retained = await session.get(DocumentUploadRow, operation_id)
            assert retained is not None and retained.replay_expires_at == deadline
            past_deadline = latest - timedelta(days=1)
            retained.replay_expires_at = past_deadline
        expired = await api.post(path, params=params, headers=headers, content=content)
        assert expired.status_code == 201
        expired_receipt = receipt_type.validate_json(expired.content)
        expired_value = expired_receipt["idempotencyExpiresAt"]
        assert expired_value is not None and datetime.fromisoformat(expired_value) == past_deadline
        assert expired_receipt == {**receipt, "idempotencyExpiresAt": expired_value}

    await database.shutdown()
    _migrate_legacy_receipt(temporary_postgres_settings, original, past_deadline)
    app = create_app(settings, open_document_uploader=open_uploader)
    async with (
        app.router.lifespan_context(app),
        httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app), base_url=_ORIGIN, timeout=10
        ) as api,
    ):
        legacy = await api.post(path, params=params, headers=headers, content=content)
    assert legacy.status_code == 201
    assert receipt_type.validate_json(legacy.content) == {**receipt, "idempotencyExpiresAt": None}
    assert capacity.reads == 1

    scope = ArtifactScopeDTO(binding.installation_id, admitted.organization_id, project)
    stored = ArtifactAttemptDTO(
        ArtifactId(original.artifact_id),
        ArtifactAttemptId(original.attempt_id),
        scope,
        len(content),
        digest,
    )
    owned_directory = staging.root.joinpath(
        scope.installation_id.value.hex,
        scope.organization_id.value.hex,
        scope.project_id.value.hex,
        stored.attempt_id.value.hex,
    )
    assert not owned_directory.exists()
    version_id = DocumentVersionId(original.version_id)
    async with database.session() as session:
        reader = PostgresSealedPdfSourceReader(session)
        source = await reader.read(scope, version_id)
        assert source is not None and source == stored
        assert await reader.read(scope, DocumentVersionId(uuid4())) is None
        assert await reader.read(replace(scope, project_id=ProjectId(uuid4())), version_id) is None
        attempt = await session.get(ArtifactAttemptRow, stored.attempt_id.value)
        assert attempt is not None
        attempt.digest = ArtifactContentDigest.from_content(b"other bytes").value
        await session.flush()
        assert await reader.read(scope, version_id) is None
        attempt.digest = digest.value
        attempt.published = False
        attempt.retired = True
        attempt.state = "retired"
        await session.flush()
        assert await reader.read(scope, version_id) is None
        await session.rollback()
    async with seaweed.open_store() as store:
        assert b"".join([chunk async for chunk in store.read(source)]) == content
    assert sent == [stored.attempt_id]
    with database_session(temporary_postgres_settings) as session:
        retained = session.get(DocumentUploadRow, operation_id)
        assert retained is not None and retained.replay_expires_at is None
        assert retained.attempt_id == original.attempt_id and retained.cleanup_job_id == job.id
        assert session.execute(capacity_query).one() == settled_capacity
        reservation = session.get(ArtifactStagingReservationRow, original.reservation_id)
        assert reservation is not None and reservation.released and reservation.staging_removed
        assert reservation.local_reserved_bytes == 0
        assert reservation.remote_reserved_bytes == reserved.remote_reserved_bytes
        attempt = session.get(ArtifactAttemptRow, original.attempt_id)
        assert attempt is not None and attempt.published and attempt.put_confirmed
        assert not attempt.retired and not attempt.remote_removed
        assert job.attempt_count == 1 and job.queued_deadline == before.queued_deadline
        assert session.scalar(select(func.count()).select_from(ArtifactAttemptRow)) == 1
        assert session.scalar(select(func.count()).select_from(DocumentUploadRow)) == 1
        assert session.scalar(select(func.count()).select_from(DocumentVersionRow)) == 1
        assert session.scalar(select(func.count()).select_from(DurableJobRow)) == 1

    if parse_uploaded_pdf:
        # Use the bootstrap fixture's verified OAuth generation for the same
        # human. The cookie was used only for the real Kratos upload above.
        await _build_uploaded_pdf(
            database=database,
            worker_database_settings=temporary_postgres_settings,
            staging_settings=staging,
            access=AccessContextDTO(seed.access.actor_principal_id, seed.binding),
            group_id=group,
            version_id=version_id,
            source=source,
            sent=sent,
            seaweed=seaweed,
            monkeypatch=monkeypatch,
        )


class MockBuildHistoryHeadroom(RetainedHistorySafetyHeadroom):
    """Supply only the isolated fixture's known admission headroom."""

    def __init__(self, installation_id: InstallationId) -> None:
        self._installation_id = installation_id
        self.checks = 0

    @override
    async def require_headroom(self, *, installation_id: InstallationId) -> None:
        assert installation_id == self._installation_id
        self.checks += 1


async def _build_uploaded_pdf(
    *,
    database: Database,
    worker_database_settings: DatabaseSettings,
    staging_settings: ArtifactStagingSettings,
    access: AccessContextDTO,
    group_id: UUID,
    version_id: DocumentVersionId,
    source: ArtifactAttemptDTO,
    sent: list[ArtifactAttemptId],
    seaweed: SeaweedFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Build the exact uploaded PDF and verify its independently read stored output."""
    scope = source.scope
    pipeline, selection = await seed_pdf_pipeline(
        database, access=access, scope=scope, group_id=group_id, version_id=version_id
    )
    fingerprint = RequestFingerprintService(RequestFingerprintKey(b"B" * 32))
    safety = MockBuildHistoryHeadroom(scope.installation_id)
    request_id = RequestId(uuid4())
    async with open_pipeline_pdf_preparation(database, fingerprint, safety) as build:
        admit = partial(
            build.admit,
            access=access,
            project_id=scope.project_id,
            pipeline_id=pipeline.pipeline_id,
            configuration_revision=pipeline.revision,
            collection_revision_id=selection,
            key=IdempotencyKey("alice-private-build"),
        )
        admitted = await admit(request_id=request_id)
    assert admitted.created

    parser = UnixPdfParser(Path("/run/inframeld-parser/parser.sock"), expected_peer_uid=10001)
    parse = parser.parse
    parsed: list[ParsedPdfDTO] = []

    async def observe_parse(
        source: bytes,
        *,
        attempt_id: UUID,
        source_digest: ArtifactContentDigest,
        definition: DoclingProcessingDefinition,
        deadline: float,
    ) -> ParsedPdfDTO:
        result = await parse(
            source,
            attempt_id=attempt_id,
            source_digest=source_digest,
            definition=definition,
            deadline=deadline,
        )
        parsed.append(result)
        return result

    monkeypatch.setattr(parser, "parse", observe_parse)
    capacity = MockArtifactCapacityReader()
    storage = storage_settings()
    settings = ApplicationWorkerApplicationSettings(
        database=worker_database_settings,
        artifact_staging=staging_settings,
        artifact_storage=storage,
        jobs=JobSettings(poll_seconds=0.1),
    )
    stopped = asyncio.Event()
    worker_database = Database(worker_database_settings)
    operations = ApplicationWorkerOperations(worker_database, settings.jobs, stopped)
    staging = PrivateArtifactStaging(
        staging_settings.root, PostgresArtifactStagingReservationReader(worker_database)
    )
    await staging.startup()
    worker_store = S3ArtifactStore(storage, effect_observation_recorder=operations)
    try:
        cleanup = ArtifactCleanupJobHandler(operations, worker_store, operations, staging)
        prepare = create_pipeline_pdf_preparation_handler(
            worker_database,
            jobs=settings.jobs,
            storage=storage,
            staging=staging,
            capacity=capacity,
            source_store=worker_store,
            parser=parser,
            observations=operations,
        )
        async with asyncio.TaskGroup() as tasks:
            tasks.create_task(
                run_application_worker(
                    settings,
                    stopped,
                    (cleanup, prepare),
                    database=worker_database,
                    operations=operations,
                )
            )
            try:
                async with asyncio.timeout(300):
                    while True:
                        async with database.session() as session:
                            job = await session.get(DurableJobRow, admitted.job_id.value)
                            assert job is not None
                            assert job.status in (
                                JobStatus.QUEUED.value,
                                JobStatus.RUNNING.value,
                                JobStatus.SUCCEEDED.value,
                            ), "The native Build worker did not succeed."
                            if job.status == JobStatus.SUCCEEDED.value:
                                generation = await session.get(ParsedPdfGenerationRow, job.id)
                                assert generation is not None
                                local_cleanup = await session.scalar(
                                    select(DurableJobRow.status)
                                    .join(
                                        ArtifactCleanupTargetRow,
                                        ArtifactCleanupTargetRow.obligation_id
                                        == DurableJobRow.cleanup_obligation_id,
                                    )
                                    .where(
                                        ArtifactCleanupTargetRow.attempt_id
                                        == generation.canonical_artifact_attempt_id
                                    )
                                )
                                if local_cleanup == JobStatus.SUCCEEDED.value:
                                    break
                        await asyncio.sleep(0.02)
            finally:
                stopped.set()
    finally:
        await worker_store.close()

    assert len(parsed) == 1 and parsed[0].source_digest == source.digest
    assert len(parsed[0].chunk_ranges) > 1
    assert job.attempt_count == 1 and job.pending_effect is None
    assert job.request_id == request_id.value
    assert generation.document_version_id == version_id.value
    assert generation.processing_profile_id == pipeline.configuration.processing_profile_id.value
    async with database.session() as session:
        attempt = await session.get(DurableJobAttemptRow, (job.id, 1))
        assert attempt is not None and attempt.ended_at is not None
        assert parsed[0].attempt_id == attempt.fence
        version = await session.get(DocumentVersionRow, version_id.value)
        assert version is not None and generation.document_id == version.document_id
        row = await session.get(ArtifactAttemptRow, generation.canonical_artifact_attempt_id)
        assert row is not None and row.length is not None and row.digest is not None
        assert row.published and row.put_confirmed and not row.remote_removed and not row.retired
        assert (row.installation_id, row.organization_id, row.project_id) == (
            scope.installation_id.value,
            scope.organization_id.value,
            scope.project_id.value,
        )
        output = ArtifactAttemptDTO(
            ArtifactId(row.artifact_id),
            ArtifactAttemptId(row.id),
            scope,
            row.length,
            ArtifactContentDigest(row.digest),
        )
        effect = await session.scalar(
            select(DurableJobEffectRow).where(DurableJobEffectRow.job_id == job.id)
        )
        assert effect is not None and effect.admitted_at is not None
        assert effect.action == "put" and effect.aborted_at is None and effect.consumed_at is None
        assert (effect.attempt, effect.fence, effect.artifact_attempt_id, effect.digest) == (
            1,
            attempt.fence,
            output.attempt_id.value,
            output.digest.value,
        )
        chunks = (
            await session.scalars(
                select(ParsedPdfChunkRow)
                .where(ParsedPdfChunkRow.generation_id == generation.id)
                .order_by(ParsedPdfChunkRow.ordinal)
            )
        ).all()
        assert [chunk.ordinal for chunk in chunks] == list(range(len(chunks)))
        assert (
            tuple((chunk.start_codepoint, chunk.end_codepoint) for chunk in chunks)
            == parsed[0].chunk_ranges
        )
        assert (
            job.checkpoint
            == output.attempt_id.value.bytes
            + generation.canonical_identity
            + len(chunks).to_bytes(4, "big")
        )
        reservation = await session.scalar(
            select(ArtifactStagingReservationRow).where(
                ArtifactStagingReservationRow.attempt_id == row.id
            )
        )
        assert reservation is not None and reservation.released and reservation.staging_removed
        assert reservation.local_reserved_bytes == 0 and reservation.remote_reserved_bytes > 0
        history = await session.get(RetainedHistoryReservationRow, admitted.operation_id.value)
        assert history is not None and history.reserved_bytes == 1024**2
    assert output.attempt_id != source.attempt_id and output.digest == parsed[0].canonical_digest
    assert not staging_settings.root.joinpath(
        scope.installation_id.value.hex,
        scope.organization_id.value.hex,
        scope.project_id.value.hex,
        output.attempt_id.value.hex,
    ).exists()

    async with open_pipeline_pdf_preparation(database, fingerprint, safety) as build:
        replay = await build.admit(
            access=access,
            project_id=scope.project_id,
            pipeline_id=pipeline.pipeline_id,
            configuration_revision=pipeline.revision,
            collection_revision_id=selection,
            key=IdempotencyKey("alice-private-build"),
            request_id=RequestId(uuid4()),
        )
    assert replay == replace(admitted, created=False)
    assert sent == [source.attempt_id, output.attempt_id]
    assert capacity.reads == 1 and safety.checks == 1
    async with seaweed.open_store() as store:
        assert output.length == len(parsed[0].canonical_bytes)
        stored = b"".join([chunk async for chunk in store.read(output)])
        assert ArtifactContentDigest.from_content(stored) == output.digest
        contents = TypeAdapter(dict[str, object]).validate_json(stored)
        text = contents.get("text")
        assert isinstance(text, str)
        alice_present = "Oh dear! Oh dear! I shall be late!" in text
        assert alice_present
        assert all(0 <= start < end <= len(text) for start, end in parsed[0].chunk_ranges)
        listing = await store.list(scope, after=None, limit=3)
        assert listing.after is None
        assert {entry.attempt_id for entry in listing.objects} == {
            source.attempt_id,
            output.attempt_id,
        }
    async with database.session() as session:
        assert await session.scalar(select(func.count()).select_from(ArtifactAttemptRow)) == 2
        assert await session.scalar(select(func.count()).select_from(ParsedPdfGenerationRow)) == 1
        assert (
            await session.scalar(select(func.count()).select_from(RetainedHistoryReservationRow))
            == 1
        )
        assert await session.scalar(select(func.count()).select_from(DurableJobRow)) == 3

    async with open_pipeline_pdf_preparation(database, fingerprint, safety) as build:
        blocked = await build.admit(
            access=access,
            project_id=scope.project_id,
            pipeline_id=pipeline.pipeline_id,
            configuration_revision=pipeline.revision,
            collection_revision_id=selection,
            key=IdempotencyKey("alice-erased-before-put"),
            request_id=RequestId(uuid4()),
        )
    assert blocked.created
    rejected = await _deny_erased_source_before_put(
        database, settings.jobs, staging_settings.root, capacity, source, job_id=blocked.job_id
    )
    assert sent == [source.attempt_id, output.attempt_id]
    async with seaweed.open_store() as store:
        assert await store.head(scope, rejected) is None
        listing_after_denial = await store.list(scope, after=None, limit=3)
        assert listing_after_denial == listing


async def _deny_erased_source_before_put(
    database: Database,
    jobs: JobSettings,
    staging_root: Path,
    capacity: MockArtifactCapacityReader,
    source: ArtifactAttemptDTO,
    *,
    job_id: JobId,
) -> ArtifactAttemptId:
    """Use real intent and erasure turns without contacting the one-shot parser again."""
    async with database.session() as session, session.begin():
        store = PostgresJobStore(session)
        observed = await store.peek_candidate()
        assert observed is not None and observed.job_id == job_id
        assert isinstance(observed.binding, ProductJobBindingDTO)
        authority = observed.binding.authority
        await AdmittedWorkAuthorizationService(
            PostgresAdmittedWorkFactsReader(session)
        ).require_current(authority)
        candidate = await store.next_candidate()
        assert candidate is not None
        assert candidate == replace(observed, observed_at=candidate.observed_at)
        context = await store.start_attempt(
            candidate,
            worker_id=uuid4(),
            lease_seconds=jobs.lease_seconds,
            work_seconds=jobs.work_seconds,
        )

    records = PostgresPipelinePdfPreparationRecords(
        database, capacity, database_seconds=jobs.database_timeout_seconds
    )
    inputs = PipelinePdfPreparationInput.from_payload(context.payload)
    fixture_bytes = b"Unpublished output for the erasure fence fixture."
    allocation = await records.allocate(context, inputs, source, len(fixture_bytes), 1)
    reservation = allocation.reservation

    async def content() -> AsyncIterator[bytes]:
        yield fixture_bytes

    staging = PrivateArtifactStaging(
        staging_root, PostgresArtifactStagingReservationReader(database)
    )
    await staging.startup()
    sealed = await staging.stage(
        reservation.reservation_id,
        artifact_id=reservation.artifact_id,
        attempt_id=reservation.attempt_id,
        scope=source.scope,
        chunks=content(),
    )
    observation = await records.begin_put(context, inputs, source, allocation, sealed)

    async with database.session() as session, session.begin():
        # Record the fixture erasure marker under the ordinary Project and Document turns.
        scope = source.scope
        assert (
            await PostgresProjectScopeLock.acquire(
                session, authority.principal_id, scope.project_id, shared=False
            )
            == scope.organization_id.value
        )
        document = await session.get(
            DocumentRow, inputs.source.document_id.value, with_for_update=True
        )
        assert document is not None and document.erasure_operation_id is None
        assert (document.installation_id, document.organization_id, document.project_id) == (
            scope.installation_id.value,
            scope.organization_id.value,
            scope.project_id.value,
        )
        blocked_at = await session.scalar(
            select(func.clock_timestamp(type_=DateTime(timezone=True)))
        )
        assert blocked_at is not None
        document.erasure_operation_id = str(uuid4())
        document.erasure_blocked_at = blocked_at

    with pytest.raises(AccessDeniedError, match="The original PDF source is unavailable"):
        await ApplicationWorkerOperations(database, jobs, asyncio.Event()).admit_put(
            observation, sealed
        )

    async with database.session() as session:
        pending = await session.get(DurableJobEffectRow, observation.value)
        assert pending is not None and pending.admitted_at is None
        row = await session.get(ArtifactAttemptRow, sealed.attempt_id.value)
        assert row is not None and not row.published and not row.put_confirmed
        assert await session.get(ParsedPdfGenerationRow, job_id.value) is None
        assert await session.scalar(select(func.count()).select_from(ParsedPdfGenerationRow)) == 1
    return sealed.attempt_id
