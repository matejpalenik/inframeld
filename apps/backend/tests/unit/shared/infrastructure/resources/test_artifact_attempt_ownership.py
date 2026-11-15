import asyncio
import threading
from pathlib import Path
from typing import override
from uuid import UUID

import pytest

from inframeld_backend.shared.application.errors.artifact_errors import (
    ArtifactIntegrityError,
    ArtifactReservationError,
    ArtifactStagingBusyError,
)
from inframeld_backend.shared.application.value_objects.artifact_attempt_id import ArtifactAttemptId
from inframeld_backend.shared.infrastructure.resources.artifact_attempt_ownership import (
    ArtifactAttemptOwnership,
)

ATTEMPT = ArtifactAttemptId(UUID(int=1))


@pytest.mark.asyncio
async def test_independent_holders_cannot_enter_the_same_attempt(tmp_path: Path) -> None:
    await asyncio.to_thread(tmp_path.chmod, 0o700)
    first, second = ArtifactAttemptOwnership(tmp_path), ArtifactAttemptOwnership(tmp_path)
    await first.startup()
    await second.startup()
    async with first.hold(ATTEMPT):
        with pytest.raises(ArtifactStagingBusyError) as caught:
            async with second.hold(ATTEMPT):
                pytest.fail("A live local holder must exclude cleanup.")
        assert isinstance(caught.value.__cause__, BlockingIOError)
    async with second.hold(ATTEMPT):
        pass
    locks = list((tmp_path / ".locks").iterdir())
    assert len(locks) == 1 and locks[0].stat().st_mode & 0o777 == 0o600


@pytest.mark.asyncio
async def test_missing_existing_root_cannot_be_recreated_as_an_empty_store(tmp_path: Path) -> None:
    root = tmp_path / "missing"
    with pytest.raises(ArtifactIntegrityError):
        await ArtifactAttemptOwnership(root).startup()
    assert not root.exists()


@pytest.mark.asyncio
async def test_interrupted_native_failure_preserves_both_errors() -> None:
    entered, release = threading.Event(), threading.Event()
    ready = asyncio.Event()
    loop = asyncio.get_running_loop()

    def fail() -> None:
        entered.set()
        loop.call_soon_threadsafe(ready.set)
        if not release.wait(1):
            raise AssertionError("The native test holder was not released.")
        raise OSError("controlled native failure")

    task = asyncio.create_task(ArtifactAttemptOwnership.run_io(fail))
    try:
        await asyncio.wait_for(ready.wait(), 1)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        release.set()
        with pytest.raises(BaseExceptionGroup) as caught:
            await asyncio.wait_for(task, 1)
        assert any(isinstance(e, asyncio.CancelledError) for e in caught.value.exceptions)
        assert any(isinstance(e, OSError) for e in caught.value.exceptions)
    finally:
        release.set()
        await asyncio.wait_for(asyncio.gather(task, return_exceptions=True), 1)


@pytest.mark.asyncio
async def test_resource_claim_excludes_another_attempt_while_native_acquisition_is_pending(
    tmp_path: Path,
) -> None:
    await asyncio.to_thread(tmp_path.chmod, 0o700)
    entered, release = asyncio.Event(), threading.Event()
    loop = asyncio.get_running_loop()

    class MockPausedOwnership(ArtifactAttemptOwnership):
        @override
        def _acquire(self, attempt_id: ArtifactAttemptId) -> int:
            if attempt_id == ATTEMPT:
                loop.call_soon_threadsafe(entered.set)
                assert release.wait(1), "The original acquisition was not released."
            return super()._acquire(attempt_id)

    owner = MockPausedOwnership(tmp_path)
    await owner.startup()

    async def first() -> None:
        async with owner.hold(ATTEMPT):
            pass

    task = asyncio.create_task(first())
    try:
        await asyncio.wait_for(entered.wait(), 1)
        with pytest.raises(ArtifactReservationError):
            async with owner.hold(ArtifactAttemptId(UUID(int=2))):
                pytest.fail("The resource already has an acquiring owner.")
    finally:
        release.set()
        await asyncio.wait_for(task, 1)
