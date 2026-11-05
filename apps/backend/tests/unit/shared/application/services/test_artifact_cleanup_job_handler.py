import asyncio
from collections.abc import AsyncGenerator
from dataclasses import replace
from datetime import UTC, datetime
from typing import BinaryIO, override
from uuid import UUID

import pytest

from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.dtos.artifact_attempt_dto import ArtifactAttemptDTO
from inframeld_backend.shared.application.dtos.artifact_cleanup_job_binding_dto import (
    ArtifactCleanupJobBindingDTO,
)
from inframeld_backend.shared.application.dtos.artifact_listing_dto import ArtifactListingDTO
from inframeld_backend.shared.application.dtos.artifact_object_dto import ArtifactObjectDTO
from inframeld_backend.shared.application.dtos.artifact_scope_dto import ArtifactScopeDTO
from inframeld_backend.shared.application.dtos.job_attempt_context_dto import JobAttemptContextDTO
from inframeld_backend.shared.application.dtos.job_effect_binding_dto import JobEffectBindingDTO
from inframeld_backend.shared.application.dtos.unadmitted_staging_artifact_origin_dto import (
    UnadmittedStagingArtifactOriginDTO,
)
from inframeld_backend.shared.application.enums.artifact_cleanup_kind import ArtifactCleanupKind
from inframeld_backend.shared.application.enums.job_effect_action import JobEffectAction
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.application.errors.artifact_errors import (
    ArtifactWriteOutcomeUnknownError,
)
from inframeld_backend.shared.application.errors.job_errors import JobStoppedError
from inframeld_backend.shared.application.protocols.artifact_cleanup_preparer import (
    ArtifactCleanupPreparer,
)
from inframeld_backend.shared.application.protocols.artifact_store import ArtifactStore
from inframeld_backend.shared.application.protocols.job_checkpoints import JobCheckpoints
from inframeld_backend.shared.application.services.artifact_cleanup_job_handler import (
    ArtifactCleanupJobHandler,
)
from inframeld_backend.shared.application.value_objects.artifact_attempt_id import ArtifactAttemptId
from inframeld_backend.shared.application.value_objects.artifact_cleanup_obligation_id import (
    ArtifactCleanupObligationId,
)
from inframeld_backend.shared.application.value_objects.artifact_id import ArtifactId
from inframeld_backend.shared.application.value_objects.job_effect_id import JobEffectId
from inframeld_backend.shared.application.value_objects.job_fence import JobFence
from inframeld_backend.shared.application.value_objects.job_id import JobId
from inframeld_backend.shared.application.value_objects.job_payload import JobPayload
from inframeld_backend.shared.application.value_objects.request_id import RequestId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId

SCOPE = ArtifactScopeDTO(
    InstallationId(UUID(int=1)), OrganizationId(UUID(int=2)), ProjectId(UUID(int=3))
)
ARTIFACT = ArtifactId(UUID(int=4))
ATTEMPT = ArtifactAttemptId(UUID(int=5))
OBLIGATION = ArtifactCleanupObligationId(UUID(int=6))
CLEANUP = ArtifactCleanupJobBindingDTO(
    OBLIGATION,
    SCOPE,
    ArtifactCleanupKind.ABANDONED_STAGING,
    UnadmittedStagingArtifactOriginDTO(ATTEMPT, RequestId(UUID(int=7))),
)
CONTEXT = JobAttemptContextDTO(
    job_id=JobId(UUID(int=8)),
    binding=CLEANUP,
    payload=JobPayload("artifact.cleanup", 1, OBLIGATION.value.bytes),
    attempt=1,
    fence=JobFence(UUID(int=9)),
    work_deadline=datetime(2030, 1, 1, tzinfo=UTC),
    checkpoint=b"original resume context",
)
PREPARED = JobEffectBindingDTO(
    effect_id=JobEffectId(UUID(int=10)),
    context=replace(CONTEXT, checkpoint=b"latest durable progress"),
    unit="artifact.cleanup:" + ATTEMPT.value.hex,
    action=JobEffectAction.DELETE,
    artifact_id=ARTIFACT,
    artifact_attempt_id=ATTEMPT,
    scope=SCOPE,
    length=None,
    digest=None,
)


class MockPreparer(ArtifactCleanupPreparer):
    """Supply the preparation decision without claiming a database observation."""

    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.result: JobEffectBindingDTO | None = PREPARED
        self.calls: list[JobAttemptContextDTO] = []
        self.entered = asyncio.Event()
        self.release: asyncio.Event | None = None
        self.failure: Exception | None = None

    @override
    async def prepare(self, context: JobAttemptContextDTO) -> JobEffectBindingDTO | None:
        self.calls.append(context)
        self.entered.set()
        if self.release is not None:
            await self.release.wait()
        if self.failure is not None:
            raise self.failure
        self.events.append("prepared")
        return self.result


class MockArtifactStore(ArtifactStore):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.calls: list[tuple[ArtifactScopeDTO, ArtifactAttemptId, JobEffectId | None]] = []
        self.entered = asyncio.Event()
        self.release: asyncio.Event | None = None
        self.failure: Exception | None = None

    @override
    async def delete(
        self,
        scope: ArtifactScopeDTO,
        attempt_id: ArtifactAttemptId,
        *,
        observation: JobEffectId | None = None,
    ) -> None:
        self.calls.append((scope, attempt_id, observation))
        self.entered.set()
        if self.release is not None:
            await self.release.wait()
        if self.failure is not None:
            raise self.failure
        self.events.append("delete_ack")

    @override
    async def put(
        self,
        attempt: ArtifactAttemptDTO,
        content: BinaryIO,
        *,
        observation: JobEffectId | None = None,
    ) -> None:
        raise AssertionError("Cleanup cannot upload.")

    @override
    def read(self, attempt: ArtifactAttemptDTO) -> AsyncGenerator[bytes]:
        raise AssertionError("Acknowledgment cannot become readback evidence.")

    @override
    async def head(
        self, scope: ArtifactScopeDTO, attempt_id: ArtifactAttemptId
    ) -> ArtifactObjectDTO | None:
        raise AssertionError("Metadata cannot establish physical settlement.")

    @override
    async def list(
        self, scope: ArtifactScopeDTO, *, after: ArtifactAttemptId | None, limit: int
    ) -> ArtifactListingDTO:
        raise AssertionError("Cleanup cannot select another target.")


class MockCheckpoints(JobCheckpoints):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.calls: list[tuple[JobAttemptContextDTO, str, bytes]] = []
        self.entered = asyncio.Event()
        self.release: asyncio.Event | None = None
        self.failure: Exception | None = None

    @override
    async def confirm_effect(
        self, context: JobAttemptContextDTO, effect_id: str, data: bytes
    ) -> None:
        self.calls.append((context, effect_id, data))
        self.entered.set()
        if self.release is not None:
            await self.release.wait()
        if self.failure is not None:
            raise self.failure
        self.events.append("ack_checkpoint")

    @override
    async def check(self, context: JobAttemptContextDTO) -> None:
        raise AssertionError("Preparation owns the protected check.")

    @override
    async def save(self, context: JobAttemptContextDTO, data: bytes) -> None:
        raise AssertionError("Only exact effect confirmation may save this progress.")

    @override
    async def begin_effect(self, context: JobAttemptContextDTO, effect_id: str) -> None:
        raise AssertionError("Preparation already committed the pending invocation.")

    @override
    async def succeed(self, context: JobAttemptContextDTO) -> None:
        raise AssertionError("The worker owns completion and physical-pending guards.")

    @override
    async def fail(self, context: JobAttemptContextDTO) -> None:
        raise AssertionError("The worker owns the original failure outcome.")


def _collaborators() -> tuple[
    ArtifactCleanupJobHandler, MockPreparer, MockArtifactStore, MockCheckpoints, list[str]
]:
    events: list[str] = []
    preparer, store, checkpoints = (
        MockPreparer(events),
        MockArtifactStore(events),
        MockCheckpoints(events),
    )
    return ArtifactCleanupJobHandler(preparer, store), preparer, store, checkpoints, events


@pytest.mark.asyncio
async def test_dispatches_exact_prepared_delete_after_preparation_and_confirms_only_its_ack() -> (
    None
):
    handler, preparer, store, checkpoints, events = _collaborators()
    preparer.release = asyncio.Event()
    store.release = asyncio.Event()
    task = asyncio.create_task(handler.run(CONTEXT, checkpoints))
    ready = asyncio.create_task(preparer.entered.wait())
    try:
        done, _ = await asyncio.wait((task, ready), timeout=1, return_when=asyncio.FIRST_COMPLETED)
        assert ready in done and ready.result(), "The handler never entered preparation."
        assert store.calls == [] and checkpoints.calls == [] and not task.done()
        preparer.release.set()
        await asyncio.wait_for(store.entered.wait(), 1)
        assert checkpoints.calls == [] and not task.done()
        store.release.set()
        await asyncio.wait_for(task, 1)
    finally:
        preparer.release.set()
        store.release.set()
        for pending in (task, ready):
            if not pending.done():
                pending.cancel()
        await asyncio.wait_for(asyncio.gather(task, ready, return_exceptions=True), 1)
    assert preparer.calls == [CONTEXT]
    assert store.calls == [(SCOPE, ATTEMPT, PREPARED.effect_id)]
    assert checkpoints.calls == [
        (
            PREPARED.context,
            PREPARED.unit,
            b"artifact.cleanup.delete-ack.v1\0"
            + OBLIGATION.value.bytes
            + ARTIFACT.value.bytes
            + ATTEMPT.value.bytes,
        )
    ]
    assert events == ["prepared", "delete_ack", "ack_checkpoint"]
    assert handler.payload_type() == ("artifact.cleanup", 1)


@pytest.mark.asyncio
async def test_saved_ack_decision_skips_dispatch_without_trusting_stale_resume_bytes() -> None:
    handler, preparer, store, checkpoints, events = _collaborators()
    preparer.result = None
    await handler.run(CONTEXT, checkpoints)
    assert preparer.calls == [CONTEXT]
    assert store.calls == [] and checkpoints.calls == [] and events == ["prepared"]


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["prepare", "delete", "confirm"])
@pytest.mark.parametrize(
    "error_type", [DependencyUnavailableError, ArtifactWriteOutcomeUnknownError]
)
async def test_failures_propagate_without_redispatch(
    stage: str, error_type: type[Exception]
) -> None:
    handler, preparer, store, checkpoints, _ = _collaborators()
    failure = error_type("The original outcome could not be confirmed.")
    if stage == "prepare":
        preparer.failure = failure
    elif stage == "delete":
        store.failure = failure
    else:
        checkpoints.failure = failure
    with pytest.raises(error_type) as caught:
        await handler.run(CONTEXT, checkpoints)
    assert caught.value is failure and preparer.calls == [CONTEXT]
    assert len(store.calls) == (0 if stage == "prepare" else 1)
    assert len(checkpoints.calls) == (1 if stage == "confirm" else 0)


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["prepare", "delete", "confirm"])
async def test_cancellation_propagates_without_starting_another_step(stage: str) -> None:
    handler, preparer, store, checkpoints, _ = _collaborators()
    release = asyncio.Event()
    if stage == "prepare":
        preparer.release, entered = release, preparer.entered
    elif stage == "delete":
        store.release, entered = release, store.entered
    else:
        checkpoints.release, entered = release, checkpoints.entered
    task = asyncio.create_task(handler.run(CONTEXT, checkpoints))
    try:
        await asyncio.wait_for(entered.wait(), 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 1)
        assert len(store.calls) == (0 if stage == "prepare" else 1)
        assert len(checkpoints.calls) == (1 if stage == "confirm" else 0)
    finally:
        release.set()
        if not task.done():
            task.cancel()
        await asyncio.wait_for(asyncio.gather(task, return_exceptions=True), 1)


@pytest.mark.asyncio
@pytest.mark.parametrize("changed", ["action", "job", "scope", "target", "kind", "payload"])
async def test_foreign_or_unsupported_preparation_cannot_dispatch(changed: str) -> None:
    handler, preparer, store, checkpoints, _ = _collaborators()
    context = CONTEXT
    prepared = PREPARED
    if changed == "action":
        prepared = replace(prepared, action="put")
    elif changed == "job":
        prepared = replace(prepared, context=replace(prepared.context, job_id=JobId(UUID(int=20))))
    elif changed == "scope":
        prepared = replace(prepared, scope=replace(SCOPE, project_id=ProjectId(UUID(int=21))))
    elif changed == "target":
        prepared = replace(prepared, artifact_attempt_id=ArtifactAttemptId(UUID(int=22)))
    elif changed == "kind":
        context = replace(context, binding=replace(CLEANUP, kind=ArtifactCleanupKind.ERASURE))
        prepared = replace(prepared, context=context)
    else:
        context = replace(context, payload=JobPayload("artifact.cleanup", 1, b"another obligation"))
        prepared = replace(prepared, context=context)
    preparer.result = prepared
    with pytest.raises(JobStoppedError):
        await handler.run(context, checkpoints)
    assert store.calls == [] and checkpoints.calls == []
