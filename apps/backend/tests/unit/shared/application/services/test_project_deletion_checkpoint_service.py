"""Observe child-only checkpoint behavior with the existing controlled job mechanics."""

from dataclasses import replace
from datetime import timedelta
from typing import override
from uuid import UUID

import pytest
from tests.support.job_effect_recovery_handler import (
    MockEffectStore,
    MockEffectTransactions,
    original_effect,
)
from tests.unit.shared.application.services.test_project_deletion_job_authorization_service import (
    BINDING,
    FACTS,
    MockFacts,
)

from inframeld_backend.shared.application.dtos.job_attempt_context_dto import JobAttemptContextDTO
from inframeld_backend.shared.application.dtos.project_deletion_job_facts_dto import (
    ProjectDeletionJobFactsDTO,
)
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ConflictError,
    DependencyUnavailableError,
)
from inframeld_backend.shared.application.errors.job_errors import (
    JobFenceLostError,
    JobStoppedError,
)
from inframeld_backend.shared.application.services.project_deletion_checkpoint_service import (
    ProjectDeletionCheckpointService,
)
from inframeld_backend.shared.application.services.project_deletion_job_authorization_service import (
    ProjectDeletionJobAuthorizationService,
)
from inframeld_backend.shared.domain.enums.job_status import JobStatus


class MockChildStore(MockEffectStore):
    """Reuse controlled mechanics with an actual deletion binding and no artifact invocation."""

    def __init__(self) -> None:
        original = original_effect()
        super().__init__(original)
        self.context = replace(original.context, binding=BINDING, payload=FACTS.payload)
        self.job = replace(
            self.job,
            binding=BINDING,
            payload=FACTS.payload,
            pending_effect=None,
            cancel_requested=False,
        )
        self.observation = None
        self.finished: tuple[JobStatus, str | None] | None = None
        self.renewed: tuple[bytes, float] | None = None

    @override
    async def checkpoint(
        self, context: JobAttemptContextDTO, data: bytes, *, lease_seconds: float
    ) -> None:
        self.events.append("renew-child")
        self.renewed = data, lease_seconds
        self.job = replace(self.job, checkpoint=data)

    @override
    async def finish(
        self, context: JobAttemptContextDTO, *, status: JobStatus, reason: str | None
    ) -> None:
        self.events.append("finish-child")
        self.finished = status, reason
        self.job = replace(self.job, status=status, reason=reason)


class MockParentFacts(MockFacts):
    def __init__(self, store: MockChildStore) -> None:
        super().__init__()
        self.store = store
        self.result = replace(FACTS, job_id=store.job.job_id, observed_at=store.job.observed_at)

    @override
    async def read(self, obligation_id: UUID) -> ProjectDeletionJobFactsDTO | None:
        self.store.events.append("parent-read")
        return await super().read(obligation_id)


class CheckpointScenario:
    def __init__(self) -> None:
        self.store = MockChildStore()
        self.reader = MockParentFacts(self.store)
        self.transactions = MockEffectTransactions(self.store.events)
        self.service = ProjectDeletionCheckpointService(
            self.transactions,
            self.store,
            ProjectDeletionJobAuthorizationService(self.reader),
        )


@pytest.mark.asyncio
async def test_renewal_reads_parent_then_owns_and_renews_only_original_child() -> None:
    scenario = CheckpointScenario()
    before = scenario.reader.result
    await scenario.service.check(scenario.store.context)
    assert scenario.store.events == ["begin", "parent-read", "fence", "renew-child", "commit"]
    assert scenario.store.renewed == (scenario.store.context.checkpoint, 30)
    assert scenario.reader.result == before and scenario.store.finished is None


@pytest.mark.asyncio
async def test_local_success_releases_child_without_completing_physical_parent() -> None:
    scenario = CheckpointScenario()
    assert scenario.reader.result is not None
    parent = replace(
        scenario.reader.result,
        shutdown_completed_at=FACTS.admitted_at + timedelta(seconds=5),
        source_revision=2,
    )
    scenario.reader.result = parent
    await scenario.service.succeed(scenario.store.context)
    assert scenario.store.finished == (JobStatus.SUCCEEDED, None)
    assert scenario.store.events == ["begin", "parent-read", "fence", "finish-child", "commit"]
    assert scenario.reader.result == parent
    assert parent.physical_cleanup_completed_at is None


@pytest.mark.asyncio
async def test_checkpoint_bytes_cannot_substitute_for_committed_parent_shutdown() -> None:
    scenario = CheckpointScenario()
    context = replace(scenario.store.context, checkpoint=b"shutdown-complete")
    scenario.store.job = replace(scenario.store.job, checkpoint=context.checkpoint)
    with pytest.raises(JobStoppedError):
        await scenario.service.succeed(context)
    assert scenario.store.finished is None and scenario.store.events[-1] == "rollback"


@pytest.mark.asyncio
async def test_local_failure_keeps_parent_and_original_meaning_unchanged() -> None:
    scenario = CheckpointScenario()
    parent = scenario.reader.result
    await scenario.service.fail(scenario.store.context)
    assert scenario.store.finished == (JobStatus.FAILED, "handler_failed")
    assert scenario.reader.result == parent
    assert scenario.store.events == ["begin", "parent-read", "fence", "finish-child", "commit"]


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["save", "begin-effect", "confirm-effect"])
async def test_generic_checkpoint_and_external_effect_calls_cannot_change_parent(
    operation: str,
) -> None:
    scenario = CheckpointScenario()
    parent = scenario.reader.result
    with pytest.raises(JobStoppedError):
        if operation == "save":
            await scenario.service.save(scenario.store.context, b"forged-completion")
        elif operation == "begin-effect":
            await scenario.service.begin_effect(scenario.store.context, "delete")
        else:
            await scenario.service.confirm_effect(scenario.store.context, "delete", b"done")
    assert scenario.reader.result == parent
    assert scenario.store.finished is None and scenario.store.renewed is None


@pytest.mark.asyncio
async def test_stale_fence_propagates_without_child_or_parent_success() -> None:
    scenario = CheckpointScenario()
    scenario.store.fence_error = True
    with pytest.raises(JobFenceLostError):
        await scenario.service.check(scenario.store.context)
    assert scenario.store.finished is None and scenario.store.renewed is None
    assert scenario.store.events[-1] == "rollback"


@pytest.mark.asyncio
async def test_missing_parent_stops_before_job_ownership_or_renewal() -> None:
    scenario = CheckpointScenario()
    scenario.reader.result = None
    with pytest.raises(AccessDeniedError):
        await scenario.service.check(scenario.store.context)
    assert "fence" not in scenario.store.events and scenario.store.renewed is None


@pytest.mark.asyncio
async def test_unresolved_effect_never_becomes_local_success() -> None:
    scenario = CheckpointScenario()
    scenario.store.job = replace(scenario.store.job, pending_effect="unexpected-effect")
    with pytest.raises(JobStoppedError):
        await scenario.service.succeed(scenario.store.context)
    assert scenario.store.finished is None


@pytest.mark.asyncio
async def test_product_cancellation_flag_does_not_cancel_original_deletion() -> None:
    scenario = CheckpointScenario()
    scenario.store.job = replace(scenario.store.job, cancel_requested=True)
    await scenario.service.check(scenario.store.context)
    assert scenario.store.renewed is not None and scenario.store.finished is None


@pytest.mark.asyncio
async def test_foreign_current_child_cannot_receive_a_checkpoint() -> None:
    scenario = CheckpointScenario()
    scenario.store.job = replace(scenario.store.job, payload=replace(FACTS.payload, data=b"other"))
    with pytest.raises(ConflictError):
        await scenario.service.check(scenario.store.context)
    assert scenario.store.renewed is None and scenario.store.finished is None


@pytest.mark.asyncio
async def test_artifact_context_cannot_use_deletion_checkpoints() -> None:
    scenario = CheckpointScenario()
    with pytest.raises(JobStoppedError):
        await scenario.service.check(original_effect().context)
    assert scenario.store.renewed is None and scenario.reader.calls == []


@pytest.mark.asyncio
async def test_uncertain_child_commit_propagates_without_repeating_the_step() -> None:
    scenario = CheckpointScenario()
    error = DependencyUnavailableError("Child commit acknowledgment missing.")
    scenario.transactions.commit_error = error
    parent = scenario.reader.result
    with pytest.raises(DependencyUnavailableError) as caught:
        await scenario.service.fail(scenario.store.context)
    assert caught.value is error and scenario.store.events.count("finish-child") == 1
    assert scenario.reader.result == parent
