from uuid import uuid4

import pytest
from tests.support.job_effect_recovery_handler import (
    MockEffectCleanupAuthority,
    MockEffectProductAuthority,
    MockEffectStore,
    MockEffectTransactions,
    original_effect,
)

from inframeld_backend.shared.application.errors.application_errors import (
    ConflictError,
    DependencyUnavailableError,
)
from inframeld_backend.shared.application.errors.job_errors import JobFenceLostError
from inframeld_backend.shared.application.services.job_effect_observation_service import (
    JobEffectObservationService,
)
from inframeld_backend.shared.application.value_objects.artifact_attempt_id import ArtifactAttemptId


def service(store: MockEffectStore) -> tuple[JobEffectObservationService, MockEffectTransactions]:
    transactions = MockEffectTransactions(store.events)
    return JobEffectObservationService(
        transactions,
        store,
        MockEffectProductAuthority(store.events),
        MockEffectCleanupAuthority(store),
    ), transactions


@pytest.mark.asyncio
async def test_unsealed_delete_admission_commits_once_under_original_cleanup_authority() -> None:
    binding = original_effect()
    store = MockEffectStore(binding)
    operation, _ = service(store)
    await operation.admit_delete(binding.effect_id, binding.scope, binding.artifact_attempt_id)
    assert store.events == ["begin", "effect", "fence", "cleanup", "target", "admit", "commit"]
    assert store.observation is not None and store.observation.admitted_at is not None
    with pytest.raises(ConflictError):
        await operation.admit_delete(binding.effect_id, binding.scope, binding.artifact_attempt_id)
    assert store.events.count("admit") == 1


@pytest.mark.asyncio
async def test_recording_requires_admission_and_cannot_clear_the_pending_unit() -> None:
    binding = original_effect()
    store = MockEffectStore(binding)
    operation, _ = service(store)
    with pytest.raises(ConflictError):
        await operation.record_delete_abort(
            binding.effect_id, binding.scope, binding.artifact_attempt_id
        )
    assert "abort" not in store.events
    await operation.admit_delete(binding.effect_id, binding.scope, binding.artifact_attempt_id)
    await operation.record_delete_abort(
        binding.effect_id, binding.scope, binding.artifact_attempt_id
    )
    assert store.observation is not None and store.observation.aborted_at is not None
    assert store.job.pending_effect == binding.unit
    assert store.events[-1] == "commit"


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["wrong-target", "stale-fence", "changed-row"])
async def test_live_admission_rejects_changed_binding_before_consuming(failure: str) -> None:
    binding = original_effect()
    store = MockEffectStore(binding)
    store.fence_error = failure == "stale-fence"
    store.target_error = failure == "changed-row"
    target = (
        ArtifactAttemptId(uuid4()) if failure == "wrong-target" else binding.artifact_attempt_id
    )
    operation, _ = service(store)
    with pytest.raises((ConflictError, JobFenceLostError)):
        await operation.admit_delete(binding.effect_id, binding.scope, target)
    assert "admit" not in store.events and "abort" not in store.events
    assert store.events[-1] == "rollback"


@pytest.mark.asyncio
async def test_ambiguous_commit_does_not_return_a_replayable_admission() -> None:
    binding = original_effect()
    store = MockEffectStore(binding)
    operation, transactions = service(store)
    transactions.commit_error = DependencyUnavailableError("Commit acknowledgment lost.")
    with pytest.raises(DependencyUnavailableError):
        await operation.admit_delete(binding.effect_id, binding.scope, binding.artifact_attempt_id)
    transactions.commit_error = None
    with pytest.raises(ConflictError):
        await operation.admit_delete(binding.effect_id, binding.scope, binding.artifact_attempt_id)
    assert store.events.count("admit") == 1 and "abort" not in store.events


@pytest.mark.asyncio
async def test_registration_rechecks_original_target_without_inventing_sealed_content() -> None:
    binding = original_effect()
    store = MockEffectStore(binding)
    operation, _ = service(store)
    await operation.register(binding)
    assert store.observation is not None and store.observation.binding == binding
    assert store.observation.binding.length is None and store.observation.binding.digest is None
    assert store.events == ["begin", "fence", "cleanup", "target", "register", "commit"]
