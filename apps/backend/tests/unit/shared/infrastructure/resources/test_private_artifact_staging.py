import asyncio
import os
from collections.abc import AsyncGenerator, Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import override
from uuid import UUID

import pytest

from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.dtos.artifact_cleanup_target_dto import (
    ArtifactCleanupTargetDTO,
)
from inframeld_backend.shared.application.dtos.artifact_scope_dto import ArtifactScopeDTO
from inframeld_backend.shared.application.dtos.artifact_staging_reservation_dto import (
    ArtifactStagingReservationDTO,
)
from inframeld_backend.shared.application.errors.artifact_errors import (
    ArtifactCapacityError,
    ArtifactIntegrityError,
    ArtifactReservationError,
)
from inframeld_backend.shared.application.protocols.artifact_staging_reservation_reader import (
    ArtifactStagingReservationReader,
)
from inframeld_backend.shared.application.value_objects.artifact_attempt_id import ArtifactAttemptId
from inframeld_backend.shared.application.value_objects.artifact_content_digest import (
    ArtifactContentDigest,
)
from inframeld_backend.shared.application.value_objects.artifact_id import ArtifactId
from inframeld_backend.shared.application.value_objects.artifact_staging_reservation_id import (
    ArtifactStagingReservationId,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.infrastructure.resources.private_artifact_staging import (
    PrivateArtifactStaging,
)

SCOPE = ArtifactScopeDTO(
    InstallationId(UUID(int=1)), OrganizationId(UUID(int=2)), ProjectId(UUID(int=3))
)
NOW = datetime.now(UTC)
RESERVATION = ArtifactStagingReservationDTO(
    ArtifactStagingReservationId(UUID(int=4)),
    ArtifactId(UUID(int=5)),
    ArtifactAttemptId(UUID(int=6)),
    SCOPE,
    25 * 1024**2,
    NOW + timedelta(hours=1),
    NOW,
)


class MockReservations(ArtifactStagingReservationReader):
    def __init__(self, facts: ArtifactStagingReservationDTO = RESERVATION) -> None:
        self.facts = facts

    @override
    async def read(
        self, reservation_id: ArtifactStagingReservationId
    ) -> ArtifactStagingReservationDTO | None:
        return self.facts

    @override
    async def read_attempt(
        self, attempt_id: ArtifactAttemptId
    ) -> ArtifactStagingReservationDTO | None:
        return self.facts


async def chunks(*parts: bytes) -> AsyncGenerator[bytes]:
    for part in parts:
        yield part


@pytest.mark.asyncio
async def test_seals_complete_bytes_and_preserves_the_private_file(tmp_path: Path) -> None:
    root = tmp_path / "staging"
    root.mkdir(mode=0o700)
    reader = MockReservations()
    staging = PrivateArtifactStaging(root, reader)
    await staging.startup()
    attempt = await staging.stage(
        RESERVATION.reservation_id,
        artifact_id=RESERVATION.artifact_id,
        attempt_id=RESERVATION.attempt_id,
        scope=SCOPE,
        chunks=chunks(b"a", b"bc"),
    )
    assert attempt.length == 3 and attempt.digest == ArtifactContentDigest.from_content(b"abc")
    reader.facts = replace(reader.facts, length=attempt.length, digest=attempt.digest)
    async with staging.open(attempt) as content:
        assert content.read() == b"abc"
        assert os.fstat(content.fileno()).st_mode & 0o777 == 0o600


@pytest.mark.asyncio
async def test_partial_overflow_is_owned_and_never_sealed(tmp_path: Path) -> None:
    await asyncio.to_thread(tmp_path.chmod, 0o700)
    staging = PrivateArtifactStaging(
        tmp_path, MockReservations(replace(RESERVATION, limit_bytes=2))
    )
    await staging.startup()
    with pytest.raises(ArtifactCapacityError):
        await staging.stage(
            RESERVATION.reservation_id,
            artifact_id=RESERVATION.artifact_id,
            attempt_id=RESERVATION.attempt_id,
            scope=SCOPE,
            chunks=chunks(b"ab", b"c"),
        )
    file = tmp_path.joinpath(
        *(x.value.hex for x in (SCOPE.installation_id, SCOPE.organization_id, SCOPE.project_id)),
        RESERVATION.attempt_id.value.hex,
    )
    assert file.read_bytes() == b"ab"


@pytest.mark.asyncio
async def test_unlink_fsync_failure_retries_with_durable_parent_even_when_name_is_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    await asyncio.to_thread(tmp_path.chmod, 0o700)
    reader = MockReservations()
    storage = PrivateArtifactStaging(tmp_path, reader)
    await storage.startup()
    attempt = await storage.stage(
        RESERVATION.reservation_id,
        artifact_id=RESERVATION.artifact_id,
        attempt_id=RESERVATION.attempt_id,
        scope=SCOPE,
        chunks=chunks(b"abc"),
    )
    reader.facts = replace(reader.facts, retired=True, length=attempt.length, digest=attempt.digest)
    directory = tmp_path.joinpath(
        *(x.value.hex for x in (SCOPE.installation_id, SCOPE.organization_id, SCOPE.project_id))
    )
    inode = directory.stat().st_ino
    original = os.fsync
    calls = 0

    def fsync(descriptor: int) -> None:
        nonlocal calls
        if os.fstat(descriptor).st_ino == inode:
            calls += 1
            if calls == 1:
                raise OSError("controlled directory sync failure")
        original(descriptor)

    monkeypatch.setattr(os, "fsync", fsync)
    target = ArtifactCleanupTargetDTO(
        attempt.artifact_id, attempt.attempt_id, attempt.scope, attempt.length, attempt.digest
    )
    with pytest.raises(ArtifactIntegrityError):
        await storage.remove(target)
    assert not (directory / attempt.attempt_id.value.hex).exists()
    await storage.remove(target)
    assert calls == 2


@pytest.mark.asyncio
async def test_never_started_unsealed_target_fsyncs_nearest_existing_parent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    await asyncio.to_thread(tmp_path.chmod, 0o700)
    reader = MockReservations(replace(RESERVATION, retired=True))
    storage = PrivateArtifactStaging(tmp_path, reader)
    await storage.startup()
    inode, original = (await asyncio.to_thread(tmp_path.stat)).st_ino, os.fsync
    synced: list[int] = []

    def fsync(descriptor: int) -> None:
        synced.append(os.fstat(descriptor).st_ino)
        original(descriptor)

    monkeypatch.setattr(os, "fsync", fsync)
    await storage.remove(
        ArtifactCleanupTargetDTO(RESERVATION.artifact_id, RESERVATION.attempt_id, SCOPE, None, None)
    )
    assert inode in synced
    assert not (tmp_path / SCOPE.installation_id.value.hex).exists()


@pytest.mark.asyncio
async def test_retirement_excludes_new_stage_and_open_before_local_io(tmp_path: Path) -> None:
    await asyncio.to_thread(tmp_path.chmod, 0o700)
    reader = MockReservations(replace(RESERVATION, retired=True))
    storage = PrivateArtifactStaging(tmp_path, reader)
    await storage.startup()
    with pytest.raises(ArtifactReservationError):
        await storage.stage(
            RESERVATION.reservation_id,
            artifact_id=RESERVATION.artifact_id,
            attempt_id=RESERVATION.attempt_id,
            scope=SCOPE,
            chunks=chunks(b"abc"),
        )
    assert not (tmp_path / SCOPE.installation_id.value.hex).exists()


@pytest.mark.asyncio
async def test_stream_and_handle_close_failures_are_both_preserved(tmp_path: Path) -> None:
    await asyncio.to_thread(tmp_path.chmod, 0o700)

    class MockFailingCloseStaging(PrivateArtifactStaging):
        @staticmethod
        @override
        async def _run_io[T](
            action: Callable[[], T], *, on_cancel: Callable[[T], None] | None = None
        ) -> T:
            result = await PrivateArtifactStaging._run_io(action, on_cancel=on_cancel)
            if getattr(action, "__name__", "") == "close":
                raise OSError("controlled post-close failure")
            return result

    storage = MockFailingCloseStaging(tmp_path, MockReservations())
    await storage.startup()

    async def interrupted() -> AsyncGenerator[bytes]:
        yield b"ab"
        raise ValueError("controlled source failure")

    with pytest.raises(BaseExceptionGroup) as caught:
        await storage.stage(
            RESERVATION.reservation_id,
            artifact_id=RESERVATION.artifact_id,
            attempt_id=RESERVATION.attempt_id,
            scope=SCOPE,
            chunks=interrupted(),
        )
    assert any(isinstance(error, ValueError) for error in caught.value.exceptions)
    assert any(isinstance(error, OSError) for error in caught.value.exceptions)
