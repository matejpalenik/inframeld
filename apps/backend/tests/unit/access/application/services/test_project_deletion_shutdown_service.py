"""Exercise shutdown orchestration with controlled ports, not SQL admission or rollback proof."""

import asyncio
from dataclasses import replace
from datetime import timedelta
from typing import override
from uuid import UUID

import pytest
from tests.support.job_effect_recovery_handler import MockEffectTransactions, original_effect
from tests.unit.shared.application.services.test_project_deletion_checkpoint_service import (
    MockChildStore,
)
from tests.unit.shared.application.services.test_project_deletion_job_authorization_service import (
    BINDING,
    FACTS,
    MockFacts,
)

from inframeld_backend.access.application.dtos.project_deletion_shutdown_facts_dto import (
    ProjectDeletionShutdownFactsDTO,
)
from inframeld_backend.access.application.protocols.project_application_shutdown_effects_writer import (
    ProjectApplicationShutdownEffectsWriter,
)
from inframeld_backend.access.application.protocols.project_deletion_shutdown_writer import (
    ProjectDeletionShutdownWriter,
)
from inframeld_backend.access.application.services.project_deletion_shutdown_service import (
    ProjectDeletionShutdownService,
)
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.dtos.job_attempt_context_dto import JobAttemptContextDTO
from inframeld_backend.shared.application.dtos.job_snapshot_dto import JobSnapshotDTO
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
from inframeld_backend.shared.application.services.project_deletion_job_authorization_service import (
    ProjectDeletionJobAuthorizationService,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.domain.enums.job_status import JobStatus
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId

LOCKED = ProjectDeletionShutdownFactsDTO(
    installation_id=BINDING.installation_id,
    organization_id=OrganizationId(BINDING.organization_id),
    project_id=ProjectId(BINDING.project_id),
    project_status=ProjectStatus.DELETING,
    access_revision=BINDING.access_revision,
    binding=BINDING,
    source_revision=1,
    shutdown_completed_at=None,
)


class MockOwnedStore(MockChildStore):
    def __init__(self) -> None:
        super().__init__()
        self.ownership_checks = 0
        self.fail_on_check: int | None = None

    @override
    async def require_current(self, context: JobAttemptContextDTO) -> JobSnapshotDTO:
        self.ownership_checks += 1
        if self.ownership_checks == self.fail_on_check:
            self.events.append("fence")
            raise JobFenceLostError()
        return await super().require_current(context)


class MockBackingFacts(MockFacts):
    def __init__(self, store: MockOwnedStore) -> None:
        super().__init__()
        self.store = store
        self.result = replace(FACTS, job_id=store.job.job_id, observed_at=store.job.observed_at)

    @override
    async def read(self, obligation_id: UUID) -> ProjectDeletionJobFactsDTO | None:
        self.store.events.append("backing")
        return await super().read(obligation_id)


class MockShutdownWriter(ProjectDeletionShutdownWriter):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.facts = LOCKED
        self.lock_error: BaseException | None = None
        self.record_error: BaseException | None = None
        self.records: list[
            tuple[JobAttemptContextDTO, ProjectDeletionShutdownFactsDTO, bool, int]
        ] = []

    @override
    async def lock_original(self, context: JobAttemptContextDTO) -> ProjectDeletionShutdownFactsDTO:
        self.events.append("lock-original")
        if self.lock_error is not None:
            raise self.lock_error
        return self.facts

    @override
    async def record_shutdown(
        self,
        context: JobAttemptContextDTO,
        *,
        facts: ProjectDeletionShutdownFactsDTO,
        changed: bool,
        access_revision: int,
    ) -> None:
        self.events.append("record-shutdown")
        self.records.append((context, facts, changed, access_revision))
        if self.record_error is not None:
            raise self.record_error


class MockEffects(ProjectApplicationShutdownEffectsWriter):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.changed = True
        self.error: BaseException | None = None
        self.stall = False
        self.scopes: list[tuple[InstallationId, OrganizationId, ProjectId]] = []

    @override
    async def shutdown(
        self,
        *,
        installation_id: InstallationId,
        organization_id: OrganizationId,
        project_id: ProjectId,
    ) -> bool:
        self.events.append("effects")
        self.scopes.append((installation_id, organization_id, project_id))
        if self.error is not None:
            raise self.error
        if self.stall:
            await asyncio.Event().wait()
        return self.changed


class ShutdownScenario:
    def __init__(self) -> None:
        self.store = MockOwnedStore()
        self.transactions = MockEffectTransactions(self.store.events)
        self.writer = MockShutdownWriter(self.store.events)
        self.backing = MockBackingFacts(self.store)
        self.effects = MockEffects(self.store.events)
        self.service = ProjectDeletionShutdownService(
            transaction_manager=self.transactions,
            project_deletion_shutdown_writer=self.writer,
            project_deletion_job_authorizer=ProjectDeletionJobAuthorizationService(self.backing),
            job_store=self.store,
            application_shutdown_effects_writer=self.effects,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("changed", [False, True])
async def test_exact_effects_and_correlated_checkpoint_wait_for_commit(changed: bool) -> None:
    scenario = ShutdownScenario()
    scenario.effects.changed = changed
    context = scenario.store.context
    await scenario.service.shutdown(context)
    assert scenario.effects.scopes == [
        (LOCKED.installation_id, LOCKED.organization_id, LOCKED.project_id)
    ]
    assert scenario.writer.records == [(context, LOCKED, changed, 8 + int(changed))]
    assert scenario.store.events == [
        "begin",
        "lock-original",
        "backing",
        "fence",
        "effects",
        "fence",
        "record-shutdown",
        "commit",
    ]
    assert scenario.store.job.status is JobStatus.RUNNING
    assert scenario.backing.result is not None
    assert scenario.backing.result.physical_cleanup_completed_at is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "facts",
    [
        replace(LOCKED, installation_id=InstallationId(UUID(int=99))),
        replace(LOCKED, organization_id=OrganizationId(UUID(int=99))),
        replace(LOCKED, project_id=ProjectId(UUID(int=99))),
        replace(LOCKED, binding=replace(BINDING, operation_id=OperationId("other"))),
    ],
)
async def test_foreign_locked_scope_fails_before_effects_or_checkpoint(
    facts: ProjectDeletionShutdownFactsDTO,
) -> None:
    scenario = ShutdownScenario()
    scenario.writer.facts = facts
    with pytest.raises(RuntimeError, match="scope|binding"):
        await scenario.service.shutdown(scenario.store.context)
    assert scenario.effects.scopes == [] and scenario.writer.records == []
    assert scenario.store.events[-1] == "rollback"


@pytest.mark.asyncio
async def test_deleting_lifecycle_is_checked_as_integrity_not_a_caller_certificate() -> None:
    scenario = ShutdownScenario()
    scenario.writer.facts = replace(LOCKED, project_status=ProjectStatus.ACTIVE)
    with pytest.raises(ConflictError):
        await scenario.service.shutdown(scenario.store.context)
    assert scenario.effects.scopes == [] and scenario.writer.records == []


@pytest.mark.asyncio
async def test_missing_genuine_backing_stops_before_fence_and_effects() -> None:
    scenario = ShutdownScenario()
    scenario.backing.result = None
    with pytest.raises(AccessDeniedError):
        await scenario.service.shutdown(scenario.store.context)
    assert "fence" not in scenario.store.events and scenario.effects.scopes == []


@pytest.mark.asyncio
async def test_stale_original_fence_stops_before_effects() -> None:
    scenario = ShutdownScenario()
    scenario.store.fail_on_check = 1
    with pytest.raises(JobFenceLostError):
        await scenario.service.shutdown(scenario.store.context)
    assert scenario.effects.scopes == [] and scenario.writer.records == []


@pytest.mark.asyncio
async def test_expiry_during_effects_rolls_back_without_recording_a_checkpoint() -> None:
    scenario = ShutdownScenario()
    scenario.store.fail_on_check = 2
    with pytest.raises(JobFenceLostError):
        await scenario.service.shutdown(scenario.store.context)
    assert len(scenario.effects.scopes) == 1 and scenario.writer.records == []
    assert scenario.store.events[-1] == "rollback"


@pytest.mark.asyncio
async def test_already_committed_parent_checkpoint_skips_effects_revision_and_audit() -> None:
    scenario = ShutdownScenario()
    completed = FACTS.admitted_at + timedelta(seconds=5)
    scenario.writer.facts = replace(LOCKED, source_revision=2, shutdown_completed_at=completed)
    assert scenario.backing.result is not None
    scenario.backing.result = replace(
        scenario.backing.result,
        source_revision=2,
        shutdown_completed_at=completed,
    )
    await scenario.service.shutdown(scenario.store.context)
    assert scenario.effects.scopes == [] and scenario.writer.records == []
    assert scenario.store.events == ["begin", "lock-original", "backing", "fence", "commit"]


@pytest.mark.asyncio
async def test_completed_parent_does_not_bypass_current_fence() -> None:
    scenario = ShutdownScenario()
    completed = FACTS.admitted_at + timedelta(seconds=5)
    scenario.writer.facts = replace(LOCKED, source_revision=2, shutdown_completed_at=completed)
    assert scenario.backing.result is not None
    scenario.backing.result = replace(
        scenario.backing.result,
        source_revision=2,
        shutdown_completed_at=completed,
    )
    scenario.store.fail_on_check = 1
    with pytest.raises(JobFenceLostError):
        await scenario.service.shutdown(scenario.store.context)
    assert scenario.effects.scopes == [] and scenario.writer.records == []


@pytest.mark.asyncio
async def test_disagreeing_parent_observations_do_not_establish_completion() -> None:
    scenario = ShutdownScenario()
    scenario.writer.facts = replace(
        LOCKED,
        source_revision=2,
        shutdown_completed_at=FACTS.admitted_at + timedelta(seconds=5),
    )
    with pytest.raises(ConflictError):
        await scenario.service.shutdown(scenario.store.context)
    assert scenario.effects.scopes == [] and scenario.writer.records == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        asyncio.CancelledError(),
        DependencyUnavailableError(),
        ConnectionError("Effect failed."),
    ],
)
async def test_effect_failure_or_cancellation_propagates_for_rollback(error: BaseException) -> None:
    scenario = ShutdownScenario()
    scenario.effects.error = error
    with pytest.raises(type(error)) as caught:
        await scenario.service.shutdown(scenario.store.context)
    assert caught.value is error and scenario.writer.records == []
    assert scenario.store.events[-1] == "rollback"


@pytest.mark.asyncio
async def test_checkpoint_failure_propagates_with_no_second_effect_attempt() -> None:
    scenario = ShutdownScenario()
    error = DependencyUnavailableError("Checkpoint unavailable.")
    scenario.writer.record_error = error
    with pytest.raises(DependencyUnavailableError) as caught:
        await scenario.service.shutdown(scenario.store.context)
    assert caught.value is error and len(scenario.effects.scopes) == 1
    assert scenario.store.events[-1] == "rollback"


@pytest.mark.asyncio
async def test_uncertain_commit_never_redispatches_or_claims_local_completion() -> None:
    scenario = ShutdownScenario()
    error = DependencyUnavailableError("Commit acknowledgment missing.")
    scenario.transactions.commit_error = error
    with pytest.raises(DependencyUnavailableError) as caught:
        await scenario.service.shutdown(scenario.store.context)
    assert caught.value is error and len(scenario.effects.scopes) == 1
    assert len(scenario.writer.records) == 1 and "commit" not in scenario.store.events


@pytest.mark.asyncio
async def test_changed_rows_at_revision_limit_roll_back_without_checkpoint() -> None:
    scenario = ShutdownScenario()
    scenario.writer.facts = replace(LOCKED, access_revision=RevisionValidation.MAX_VALUE)
    with pytest.raises(ConflictError):
        await scenario.service.shutdown(scenario.store.context)
    assert len(scenario.effects.scopes) == 1 and scenario.writer.records == []
    assert scenario.store.events[-1] == "rollback"


@pytest.mark.asyncio
async def test_checked_unchanged_state_at_revision_limit_can_record_local_confirmation() -> None:
    scenario = ShutdownScenario()
    scenario.writer.facts = replace(LOCKED, access_revision=RevisionValidation.MAX_VALUE)
    scenario.effects.changed = False
    await scenario.service.shutdown(scenario.store.context)
    assert scenario.writer.records == [
        (scenario.store.context, scenario.writer.facts, False, RevisionValidation.MAX_VALUE)
    ]


@pytest.mark.asyncio
async def test_original_five_second_sql_budget_covers_effects_and_rolls_back() -> None:
    scenario = ShutdownScenario()
    scenario.effects.stall = True
    with pytest.raises(DependencyUnavailableError):
        await scenario.service.shutdown(scenario.store.context)
    assert len(scenario.effects.scopes) == 1 and scenario.writer.records == []
    assert scenario.store.events[-1] == "rollback"


@pytest.mark.asyncio
async def test_artifact_binding_cannot_select_project_shutdown() -> None:
    scenario = ShutdownScenario()
    with pytest.raises(JobStoppedError):
        await scenario.service.shutdown(original_effect().context)
    assert scenario.effects.scopes == [] and scenario.writer.records == []
    assert scenario.store.events == []


@pytest.mark.asyncio
async def test_unexpected_external_effect_does_not_reach_application_effects() -> None:
    scenario = ShutdownScenario()
    scenario.store.job = replace(scenario.store.job, pending_effect="unknown-unit")
    with pytest.raises(JobStoppedError):
        await scenario.service.shutdown(scenario.store.context)
    assert scenario.effects.scopes == [] and scenario.writer.records == []
