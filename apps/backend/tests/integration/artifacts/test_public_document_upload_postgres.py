"""Verify human PDF admission through the registered API and the production worker."""

import asyncio
import os
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import datetime, timedelta
from functools import partial
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

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
from tests.support.postgres import database_session
from tests.support.project_creation_scenarios import ProjectCreationSeedDTO, create_project
from tests.support.seaweedfs_fixture import SeaweedFixture, storage_settings

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.domain.enums.access_group_action import AccessGroupAction
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.value_objects.document_version_id import DocumentVersionId
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.rows.access_group_row import AccessGroupRow
from inframeld_backend.access.infrastructure.rows.group_action_grant_row import GroupActionGrantRow
from inframeld_backend.access.infrastructure.settings.csrf_settings import CSRFSettings
from inframeld_backend.access.infrastructure.settings.kratos_settings import KratosSettings
from inframeld_backend.bootstrap.application_factory import create_app
from inframeld_backend.bootstrap.application_settings import get_settings
from inframeld_backend.bootstrap.document_upload_composition import open_document_upload
from inframeld_backend.indexing.application.services.sealed_pdf_processing_service import (
    SealedPdfProcessingService,
)
from inframeld_backend.indexing.domain.value_objects.docling_processing_definition import (
    DoclingProcessingDefinition,
)
from inframeld_backend.indexing.infrastructure.resources.unix_pdf_parser import UnixPdfParser
from inframeld_backend.knowledge.infrastructure.readers.postgres_sealed_pdf_source_reader import (
    PostgresSealedPdfSourceReader,
)
from inframeld_backend.knowledge.infrastructure.rows.document_upload_row import DocumentUploadRow
from inframeld_backend.knowledge.infrastructure.rows.document_version_row import DocumentVersionRow
from inframeld_backend.shared.application.dtos.artifact_attempt_dto import ArtifactAttemptDTO
from inframeld_backend.shared.application.dtos.artifact_scope_dto import ArtifactScopeDTO
from inframeld_backend.shared.application.value_objects.artifact_attempt_id import ArtifactAttemptId
from inframeld_backend.shared.application.value_objects.artifact_content_digest import (
    ArtifactContentDigest,
)
from inframeld_backend.shared.application.value_objects.artifact_id import ArtifactId
from inframeld_backend.shared.application.value_objects.job_effect_id import JobEffectId
from inframeld_backend.shared.domain.enums.job_status import JobStatus
from inframeld_backend.shared.infrastructure.migrations.migration_runner import (
    ALEMBIC_CONFIG_PATH,
    run_migrations,
)
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.resources.s3_artifact_store import S3ArtifactStore
from inframeld_backend.shared.infrastructure.rows.alembic_version_row import AlembicVersionRow
from inframeld_backend.shared.infrastructure.rows.artifact_attempt_row import ArtifactAttemptRow
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
from inframeld_backend.shared.infrastructure.settings.database_settings import DatabaseSettings

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
        if parse_uploaded_pdf:
            parser = UnixPdfParser(
                Path("/run/inframeld-parser/parser.sock"), expected_peer_uid=10001
            )
            attempt_id = uuid4()
            result = await SealedPdfProcessingService(store, parser).process(
                source,
                attempt_id=attempt_id,
                definition=DoclingProcessingDefinition(
                    docling_slim_version="2.148.0",
                    docling_core_version="2.106.0",
                    asset_manifest_sha256=(
                        "7ea9f3c967a7bc66d2501e466334e7aef46a639e01a11376888321e0f0a51d0e"
                    ),
                    max_content_tokens=8,
                    merge_peers=False,
                    repeat_table_header=True,
                    ocr_enabled=False,
                ),
                deadline=asyncio.get_running_loop().time() + 300,
            )
            assert (result.attempt_id, result.source_digest) == (attempt_id, digest)
            assert result.canonical_digest == ArtifactContentDigest.from_content(
                result.canonical_bytes
            )
            assert b"Oh dear! Oh dear! I shall be late!" in result.canonical_bytes
            assert len(result.chunk_ranges) > 1
        else:
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
