import asyncio
from collections.abc import AsyncGenerator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import BinaryIO, override
from uuid import UUID

import pytest

from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.dtos.artifact_allocation_dto import ArtifactAllocationDTO
from inframeld_backend.shared.application.dtos.artifact_attempt_dto import ArtifactAttemptDTO
from inframeld_backend.shared.application.dtos.artifact_cleanup_job_binding_dto import (
    ArtifactCleanupJobBindingDTO,
)
from inframeld_backend.shared.application.dtos.artifact_scope_dto import ArtifactScopeDTO
from inframeld_backend.shared.application.dtos.artifact_staging_reservation_dto import (
    ArtifactStagingReservationDTO,
)
from inframeld_backend.shared.application.dtos.unadmitted_staging_artifact_origin_dto import (
    UnadmittedStagingArtifactOriginDTO,
)
from inframeld_backend.shared.application.enums.artifact_cleanup_kind import ArtifactCleanupKind
from inframeld_backend.shared.application.errors.artifact_errors import (
    ArtifactWriteOutcomeUnknownError,
)
from inframeld_backend.shared.application.protocols.artifact_staging_reservation_reader import (
    ArtifactStagingReservationReader,
)
from inframeld_backend.shared.application.value_objects.artifact_attempt_id import ArtifactAttemptId
from inframeld_backend.shared.application.value_objects.artifact_cleanup_obligation_id import (
    ArtifactCleanupObligationId,
)
from inframeld_backend.shared.application.value_objects.artifact_id import ArtifactId
from inframeld_backend.shared.application.value_objects.artifact_staging_reservation_id import (
    ArtifactStagingReservationId,
)
from inframeld_backend.shared.application.value_objects.job_effect_id import JobEffectId
from inframeld_backend.shared.application.value_objects.job_id import JobId
from inframeld_backend.shared.application.value_objects.request_id import RequestId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.infrastructure.resources.private_artifact_preparation import (
    PrivateArtifactPreparation,
)
from inframeld_backend.shared.infrastructure.resources.private_artifact_staging import (
    PrivateArtifactStaging,
)
from inframeld_backend.shared.infrastructure.resources.s3_artifact_store import S3ArtifactStore

NOW = datetime.now(UTC)
SCOPE = ArtifactScopeDTO(
    InstallationId(UUID(int=1)), OrganizationId(UUID(int=2)), ProjectId(UUID(int=3))
)
RESERVATION = ArtifactStagingReservationDTO(
    ArtifactStagingReservationId(UUID(int=4)),
    ArtifactId(UUID(int=5)),
    ArtifactAttemptId(UUID(int=6)),
    SCOPE,
    25 * 1024**2,
    NOW + timedelta(hours=1),
    NOW,
)
ALLOCATION = ArtifactAllocationDTO(
    RESERVATION,
    ArtifactCleanupJobBindingDTO(
        ArtifactCleanupObligationId(UUID(int=7)),
        SCOPE,
        ArtifactCleanupKind.ABANDONED_STAGING,
        UnadmittedStagingArtifactOriginDTO(RESERVATION.attempt_id, RequestId(UUID(int=8))),
    ),
    JobId(UUID(int=9)),
)


class MockReservations(ArtifactStagingReservationReader):
    def __init__(self) -> None:
        self.facts = RESERVATION

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


class MockLateStorage(S3ArtifactStore):
    """Hold the borrowed body until the controlled drain acknowledges native completion."""

    def __init__(self) -> None:
        self.entered, self.release = asyncio.Event(), asyncio.Event()
        self.body: BinaryIO | None = None
        self.drain_closed = False
        self.close_failure = False

    @override
    async def put(
        self,
        attempt: ArtifactAttemptDTO,
        content: BinaryIO,
        *,
        observation: JobEffectId | None = None,
    ) -> None:
        self.body = content
        raise ArtifactWriteOutcomeUnknownError("The original native write remains in flight.")

    @override
    async def close(self) -> None:
        self.entered.set()
        await self.release.wait()
        assert self.body is not None and not self.body.closed
        self.drain_closed = True
        if self.close_failure:
            raise OSError("controlled client closure failure")


async def _chunks() -> AsyncGenerator[bytes]:
    yield b"abc"


@pytest.mark.asyncio
@pytest.mark.parametrize("interruption", ["none", "cancel", "close_error"])
async def test_unknown_put_drains_before_borrowed_file_and_lock_close(
    tmp_path: Path, interruption: str
) -> None:
    await asyncio.to_thread(tmp_path.chmod, 0o700)
    reader = MockReservations()
    staging = PrivateArtifactStaging(tmp_path, reader)
    await staging.startup()
    attempt = await staging.stage(
        RESERVATION.reservation_id,
        artifact_id=RESERVATION.artifact_id,
        attempt_id=RESERVATION.attempt_id,
        scope=SCOPE,
        chunks=_chunks(),
    )
    reader.facts = replace(reader.facts, length=attempt.length, digest=attempt.digest)
    store = MockLateStorage()
    store.close_failure = interruption == "close_error"
    resource = PrivateArtifactPreparation(staging, lambda: store)

    async def execute() -> None:
        async with resource.hold(ALLOCATION):
            await resource.verify(attempt, upload=True)

    task = asyncio.create_task(execute())
    try:
        ready = asyncio.create_task(store.entered.wait())
        try:
            done, _ = await asyncio.wait(
                (task, ready), timeout=1, return_when=asyncio.FIRST_COMPLETED
            )
            assert ready in done and ready.result(), "The owned PUT drain was never entered."
        finally:
            ready.cancel()
            await asyncio.gather(ready, return_exceptions=True)
        assert store.body is not None and not store.body.closed and not task.done()
        if interruption == "cancel":
            task.cancel()
            await asyncio.sleep(0)
            assert not task.done() and not store.body.closed
        store.release.set()
        if interruption == "none":
            with pytest.raises(ArtifactWriteOutcomeUnknownError):
                await asyncio.wait_for(task, 1)
        else:
            with pytest.raises(BaseExceptionGroup) as caught:
                await asyncio.wait_for(task, 1)
            assert any(
                isinstance(error, ArtifactWriteOutcomeUnknownError)
                for error in caught.value.exceptions
            )
            assert any(
                isinstance(error, asyncio.CancelledError if interruption == "cancel" else OSError)
                for error in caught.value.exceptions
            )
        assert store.body.closed and store.drain_closed
        async with staging.hold(attempt.attempt_id):
            pass
    finally:
        store.release.set()
        if not task.done():
            task.cancel()
        await asyncio.wait_for(asyncio.gather(task, return_exceptions=True), 1)
