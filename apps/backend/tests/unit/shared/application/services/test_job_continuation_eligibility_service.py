from dataclasses import replace
from datetime import timedelta

import pytest
from tests.support.job_effect_recovery_handler import (
    MockEffectCleanupAuthority,
    MockEffectProductAuthority,
    MockEffectStore,
    original_effect,
)

from inframeld_backend.shared.application.enums.job_continuation_disposition import (
    JobContinuationDisposition,
)
from inframeld_backend.shared.application.enums.job_effect_observation_kind import (
    JobEffectObservationKind,
)
from inframeld_backend.shared.application.services.job_continuation_eligibility_service import (
    JobContinuationEligibilityService,
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
