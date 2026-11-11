"""Keep the worker adapter on one original shutdown and the existing checkpoint boundary."""

import asyncio
from dataclasses import replace
from typing import override

import pytest
from tests.support.job_effect_recovery_handler import original_effect
from tests.unit.shared.application.services.test_project_deletion_checkpoint_service import (
    MockChildStore,
)

from inframeld_backend.access.application.protocols.project_deletion_shutdown import (
    ProjectDeletionShutdown,
)
from inframeld_backend.access.application.services.project_deletion_job_handler import (
    ProjectDeletionJobHandler,
)
from inframeld_backend.shared.application.dtos.job_attempt_context_dto import JobAttemptContextDTO
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.application.errors.job_errors import JobStoppedError
from inframeld_backend.shared.application.protocols.job_checkpoints import JobCheckpoints
from inframeld_backend.shared.application.value_objects.job_payload import JobPayload

CONTEXT = MockChildStore().context


class MockShutdown(ProjectDeletionShutdown):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.calls: list[JobAttemptContextDTO] = []
        self.error: BaseException | None = None

    @override
    async def shutdown(self, context: JobAttemptContextDTO) -> None:
        self.events.append("shutdown")
        self.calls.append(context)
        if self.error is not None:
            raise self.error


class MockCheckpoints(JobCheckpoints):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.error: BaseException | None = None

    @override
    async def check(self, context: JobAttemptContextDTO) -> None:
        self.events.append("check")
        assert context == CONTEXT
        if self.error is not None:
            raise self.error

    @override
    async def save(self, context: JobAttemptContextDTO, data: bytes) -> None:
        raise AssertionError("A generic byte checkpoint cannot confirm parent shutdown.")

    @override
    async def begin_effect(self, context: JobAttemptContextDTO, effect_id: str) -> None:
        raise AssertionError("Local shutdown dispatches no external effect.")

    @override
    async def confirm_effect(
        self, context: JobAttemptContextDTO, effect_id: str, data: bytes
    ) -> None:
        raise AssertionError("Local shutdown has no external confirmation.")

    @override
    async def succeed(self, context: JobAttemptContextDTO) -> None:
        raise AssertionError("The existing worker owns child terminal success.")

    @override
    async def fail(self, context: JobAttemptContextDTO) -> None:
        raise AssertionError("The existing worker owns child terminal failure.")


def test_handler_registers_only_the_fixed_local_shutdown_payload() -> None:
    assert ProjectDeletionJobHandler(MockShutdown([])).payload_type() == (
        "project.application-shutdown",
        1,
    )


@pytest.mark.asyncio
async def test_handler_checks_then_awaits_one_exact_shutdown_without_generic_completion() -> None:
    events: list[str] = []
    operation = MockShutdown(events)
    await ProjectDeletionJobHandler(operation).run(CONTEXT, MockCheckpoints(events))
    assert operation.calls == [CONTEXT] and events == ["check", "shutdown"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "context",
    [
        original_effect().context,
        replace(CONTEXT, payload=JobPayload("other", 1, CONTEXT.payload.data)),
        replace(CONTEXT, payload=JobPayload(CONTEXT.payload.kind, 2, CONTEXT.payload.data)),
        replace(CONTEXT, payload=JobPayload(CONTEXT.payload.kind, 1, b"other")),
    ],
)
async def test_wrong_binding_or_payload_stops_before_checkpoint_or_shutdown(
    context: JobAttemptContextDTO,
) -> None:
    events: list[str] = []
    operation = MockShutdown(events)
    with pytest.raises(JobStoppedError):
        await ProjectDeletionJobHandler(operation).run(context, MockCheckpoints(events))
    assert events == [] and operation.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [asyncio.CancelledError(), DependencyUnavailableError()])
async def test_checkpoint_failure_prevents_a_shutdown_attempt(error: BaseException) -> None:
    events: list[str] = []
    operation = MockShutdown(events)
    checkpoints = MockCheckpoints(events)
    checkpoints.error = error
    with pytest.raises(type(error)) as caught:
        await ProjectDeletionJobHandler(operation).run(CONTEXT, checkpoints)
    assert caught.value is error and operation.calls == [] and events == ["check"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        asyncio.CancelledError(),
        DependencyUnavailableError("Unknown commit."),
    ],
)
async def test_shutdown_failure_propagates_without_retry_or_terminal_fabrication(
    error: BaseException,
) -> None:
    events: list[str] = []
    operation = MockShutdown(events)
    operation.error = error
    with pytest.raises(type(error)) as caught:
        await ProjectDeletionJobHandler(operation).run(CONTEXT, MockCheckpoints(events))
    assert caught.value is error
    assert operation.calls == [CONTEXT] and events == ["check", "shutdown"]
