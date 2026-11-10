from dataclasses import replace
from datetime import timedelta

import pytest
from tests.support.job_effect_recovery_handler import (
    MockEffectCleanupAuthority,
    MockEffectProductAuthority,
    MockEffectStore,
    original_effect,
)
from tests.unit.shared.application.services.test_project_deletion_job_authorization_service import (
    BINDING,
    FACTS,
    MockFacts,
)

from inframeld_backend.shared.application.enums.job_continuation_disposition import (
    JobContinuationDisposition,
)
from inframeld_backend.shared.application.enums.job_effect_observation_kind import (
    JobEffectObservationKind,
)
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.application.services.job_continuation_eligibility_service import (
    JobContinuationEligibilityService,
)
from inframeld_backend.shared.application.services.project_deletion_job_authorization_service import (
    ProjectDeletionJobAuthorizationService,
)


def prepared_store() -> MockEffectStore:
    store = MockEffectStore(original_effect())
    now = store.job.observed_at
    store.job = replace(store.job, lease_expires_at=now - timedelta(seconds=1))
    assert store.observation is not None
    store.observation = replace(
        store.observation,
        admitted_at=now - timedelta(seconds=3),
        kind=JobEffectObservationKind.NOT_DISPATCHED,
        aborted_at=now - timedelta(seconds=2),
    )
    return store


def eligibility(store: MockEffectStore) -> JobContinuationEligibilityService:
    return JobContinuationEligibilityService(
        store,
        MockEffectProductAuthority(store.events),
        MockEffectCleanupAuthority(store),
        supported_payloads=(("artifact.cleanup", 1),),
    )


@pytest.mark.asyncio
async def test_committed_historical_abort_needs_no_live_old_fence() -> None:
    store = prepared_store()
    store.fence_error = True
    result = await eligibility(store).assess_in_transaction(store.job)
    assert result.disposition is JobContinuationDisposition.ELIGIBLE
    assert result.observation == store.observation
    assert "fence" not in store.events and "product" not in store.events


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["missing", "no-proof", "wrong-payload", "consumed"])
async def test_unknown_or_mismatched_effect_never_becomes_safe(change: str) -> None:
    store = prepared_store()
    assert store.observation is not None
    if change == "missing":
        store.observation = None
    elif change == "no-proof":
        store.observation = replace(store.observation, kind=None, aborted_at=None)
    elif change == "wrong-payload":
        store.observation = replace(store.observation, binding=replace(store.binding, unit="other"))
    else:
        store.observation = replace(store.observation, consumed_at=store.job.observed_at)
    result = await eligibility(store).assess_in_transaction(store.job)
    assert result.disposition is JobContinuationDisposition.NOT_ESTABLISHED
    assert "consume" not in store.events and "retire" not in store.events


@pytest.mark.asyncio
async def test_safe_budget_exhaustion_differs_from_unknown_effect_exhaustion() -> None:
    store = prepared_store()
    now = store.binding.context.work_deadline + timedelta(seconds=1)
    store.job = replace(store.job, observed_at=now)
    assert store.observation is not None
    store.observation = replace(store.observation, observed_at=now)
    result = await eligibility(store).assess_in_transaction(store.job)
    assert result.disposition is JobContinuationDisposition.INELIGIBLE
    assert result.reason == "work_deadline_exhausted"
    store.observation = None
    result = await eligibility(store).assess_in_transaction(store.job)
    assert result.disposition is JobContinuationDisposition.NOT_ESTABLISHED


@pytest.mark.asyncio
async def test_unconfigured_deletion_obligation_validation_is_unavailable_not_product_fallback() -> (
    None
):
    from tests.unit.shared.application.services.test_project_deletion_job_authorization_service import (
        BINDING,
        FACTS,
    )

    store = prepared_store()
    store.job = replace(store.job, binding=BINDING, payload=FACTS.payload, pending_effect=None)
    with pytest.raises(DependencyUnavailableError):
        await eligibility(store).assess_in_transaction(store.job)
    assert "product" not in store.events and "cleanup" not in store.events


@pytest.mark.asyncio
@pytest.mark.parametrize("completed", [False, True])
async def test_deletion_continuation_uses_original_backing_and_local_completion(
    completed: bool,
) -> None:

    store = prepared_store()
    store.job = replace(store.job, binding=BINDING, payload=FACTS.payload, pending_effect=None)
    reader = MockFacts()
    reader.result = replace(
        FACTS,
        job_id=store.job.job_id,
        observed_at=store.job.observed_at,
        shutdown_completed_at=FACTS.admitted_at + timedelta(seconds=5) if completed else None,
        source_revision=2 if completed else 1,
    )
    operation = JobContinuationEligibilityService(
        store,
        MockEffectProductAuthority(store.events),
        MockEffectCleanupAuthority(store),
        supported_payloads=(("project.application-shutdown", 1),),
        project_deletion_job_authorizer=ProjectDeletionJobAuthorizationService(reader),
    )
    result = await operation.assess_in_transaction(store.job)
    assert result.disposition is (
        JobContinuationDisposition.INELIGIBLE if completed else JobContinuationDisposition.ELIGIBLE
    )
    assert result.reason == (
        "project_shutdown_already_complete" if completed else "retained_safe_work"
    )
    assert reader.calls == [BINDING.obligation_id]
    assert not {"product", "cleanup", "proof", "consume", "retire"}.intersection(store.events)


@pytest.mark.asyncio
async def test_deletion_unknown_effect_never_consumes_artifact_abort_proof() -> None:

    store = prepared_store()
    store.job = replace(store.job, binding=BINDING, payload=FACTS.payload)
    reader = MockFacts()
    reader.result = replace(FACTS, job_id=store.job.job_id, observed_at=store.job.observed_at)
    operation = JobContinuationEligibilityService(
        store,
        MockEffectProductAuthority(store.events),
        MockEffectCleanupAuthority(store),
        supported_payloads=(("project.application-shutdown", 1),),
        project_deletion_job_authorizer=ProjectDeletionJobAuthorizationService(reader),
    )
    result = await operation.assess_in_transaction(store.job)
    assert result.disposition is JobContinuationDisposition.NOT_ESTABLISHED
    assert result.reason == "unknown_external_effect"
    assert "proof" not in store.events and "consume" not in store.events
