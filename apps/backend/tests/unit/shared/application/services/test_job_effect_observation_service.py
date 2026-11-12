from dataclasses import replace
from uuid import uuid4

import pytest
from tests.support.job_effect_recovery_handler import (
    MockEffectCleanupAuthority,
    MockEffectProductAuthority,
    MockEffectStore,
    MockEffectTransactions,
    original_effect,
)
from tests.unit.shared.application.services.test_project_deletion_job_authorization_service import (
    BINDING,
    FACTS,
)

from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.domain.value_objects.human_suspension_id import HumanSuspensionId
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.shared.application.dtos.human_suspension_job_binding_dto import (
    HumanSuspensionJobBindingDTO,
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
from inframeld_backend.shared.application.value_objects.job_payload import JobPayload


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


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["register", "admit-delete", "record-abort"])
@pytest.mark.parametrize("owner", ["project-deletion", "human-suspension"])
async def test_nonartifact_cleanup_never_acquires_artifact_dispatch_or_abort_proof(
    action: str, owner: str
) -> None:
    original = original_effect()
    if owner == "project-deletion":
        job_binding = BINDING
        payload = FACTS.payload
    else:
        job_binding = HumanSuspensionJobBindingDTO(
            obligation_id=HumanSuspensionId(uuid4()),
            job_id=original.context.job_id,
            operation_id=BINDING.operation_id,
            request_id=BINDING.request_id,
            installation_id=BINDING.installation_id,
            organization_id=BINDING.organization_id,
            principal_id=uuid4(),
            initiator_principal_id=BINDING.initiator_principal_id,
            identity=VerifiedHumanIdentityDTO(
                IdentityAuthority("test"), IdentitySubject("subject")
            ),
            key=BINDING.key,
            fingerprint=BINDING.fingerprint,
            before_access_revision=BINDING.before_access_revision,
            access_revision=BINDING.access_revision,
        )
        payload = JobPayload("human.suspension-cleanup", 1, job_binding.obligation_id.value.bytes)
    binding = replace(
        original, context=replace(original.context, binding=job_binding, payload=payload)
    )
    store = MockEffectStore(binding)
    # The artifact authorizer is initialized from its real artifact fixture.
    # It must never be consulted for the hostile deletion invocation.
    cleanup = MockEffectCleanupAuthority(MockEffectStore(original))
    operation = JobEffectObservationService(
        MockEffectTransactions(store.events),
        store,
        MockEffectProductAuthority(store.events),
        cleanup,
    )
    if action == "record-abort":
        assert store.observation is not None
        store.observation = replace(store.observation, admitted_at=store.job.observed_at)
    with pytest.raises(ConflictError):
        if action == "register":
            await operation.register(binding)
        elif action == "admit-delete":
            await operation.admit_delete(
                binding.effect_id, binding.scope, binding.artifact_attempt_id
            )
        else:
            await operation.record_delete_abort(
                binding.effect_id, binding.scope, binding.artifact_attempt_id
            )
    assert not {"fence", "product", "target", "admit", "register", "abort"}.intersection(
        store.events
    )
