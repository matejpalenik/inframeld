from dataclasses import replace
from typing import override
from uuid import uuid4

import pytest
from tests.support.job_effect_recovery_handler import (
    MockEffectCleanupAuthority,
    MockEffectStore,
    MockEffectTransactions,
    original_effect,
)

from inframeld_backend.shared.application.dtos.artifact_cleanup_job_binding_dto import (
    ArtifactCleanupJobBindingDTO,
)
from inframeld_backend.shared.application.dtos.artifact_cleanup_target_dto import (
    ArtifactCleanupTargetDTO,
)
from inframeld_backend.shared.application.dtos.job_effect_binding_dto import JobEffectBindingDTO
from inframeld_backend.shared.application.enums.artifact_cleanup_kind import ArtifactCleanupKind
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ConflictError,
    DependencyUnavailableError,
)
from inframeld_backend.shared.application.errors.job_errors import (
    JobFenceLostError,
    JobStoppedError,
)
from inframeld_backend.shared.application.protocols.artifact_cleanup_target_reader import (
    ArtifactCleanupTargetReader,
)
from inframeld_backend.shared.application.services.artifact_cleanup_preparation_service import (
    ArtifactCleanupPreparationService,
)
from inframeld_backend.shared.application.value_objects.artifact_attempt_id import ArtifactAttemptId
from inframeld_backend.shared.application.value_objects.job_payload import JobPayload


class MockPreparationStore(MockEffectStore):
    @override
    async def register_effect(self, binding: JobEffectBindingDTO) -> None:
        await super().register_effect(binding)
        self.job = replace(self.job, pending_effect=binding.unit)


class MockCleanupTargetReader(ArtifactCleanupTargetReader):
    def __init__(self, store: MockEffectStore) -> None:
        self.store = store
        source = store.binding
        self.target: ArtifactCleanupTargetDTO | None = ArtifactCleanupTargetDTO(
            source.artifact_id,
            source.artifact_attempt_id,
            source.scope,
            source.length,
            source.digest,
        )

    @override
    async def read(
        self, binding: ArtifactCleanupJobBindingDTO, attempt_id: ArtifactAttemptId
    ) -> ArtifactCleanupTargetDTO | None:
        self.store.events.append("projection")
        assert (
            binding == self.store.job.binding
            and attempt_id == self.store.binding.artifact_attempt_id
        )
        return self.target


def prepared_operation() -> tuple[
    ArtifactCleanupPreparationService,
    MockPreparationStore,
    MockEffectCleanupAuthority,
    MockCleanupTargetReader,
    MockEffectTransactions,
]:
    original = original_effect()
    binding = original.context.binding
    assert isinstance(binding, ArtifactCleanupJobBindingDTO)
    context = replace(
        original.context,
        payload=JobPayload("artifact.cleanup", 1, binding.obligation_id.value.bytes),
    )
    store = MockPreparationStore(replace(original, context=context))
    store.job = replace(store.job, checkpoint=b"", pending_effect=None)
    authority = MockEffectCleanupAuthority(store)
    authority.facts = replace(authority.facts, retention_allows_cleanup=True)
    targets = MockCleanupTargetReader(store)
    transactions = MockEffectTransactions(store.events)
    return (
        ArtifactCleanupPreparationService(transactions, store, authority, targets),
        store,
        authority,
        targets,
        transactions,
    )


def ack_for(store: MockEffectStore) -> bytes:
    binding = store.job.binding
    assert isinstance(binding, ArtifactCleanupJobBindingDTO)
    return (
        b"artifact.cleanup.delete-ack.v1\0"
        + binding.obligation_id.value.bytes
        + store.binding.artifact_id.value.bytes
        + store.binding.artifact_attempt_id.value.bytes
    )


@pytest.mark.asyncio
async def test_preparation_commits_original_intent_from_locked_progress_before_dispatch() -> None:
    operation, store, _, _, _ = prepared_operation()
    result = await operation.prepare(store.binding.context)
    assert result is not None and result.effect_id != store.binding.effect_id
    assert result.context.checkpoint == b""
    assert result.context != store.binding.context
    assert (
        result.action,
        result.artifact_id,
        result.artifact_attempt_id,
        result.scope,
        result.length,
        result.digest,
    ) == (
        "delete",
        store.binding.artifact_id,
        store.binding.artifact_attempt_id,
        store.binding.scope,
        None,
        None,
    )
    assert store.observation is not None and store.observation.binding == result
    assert store.job.pending_effect == result.unit
    assert store.events == ["begin", "fence", "cleanup", "projection", "register", "commit"]
    with pytest.raises(ConflictError):
        await operation.prepare(store.binding.context)


@pytest.mark.asyncio
async def test_exact_committed_ack_skips_registration_using_locked_state() -> None:
    operation, store, _, _, _ = prepared_operation()
    store.job = replace(store.job, checkpoint=ack_for(store))
    assert await operation.prepare(store.binding.context) is None
    assert store.job.pending_effect is None and "register" not in store.events
    assert store.events[-1] == "commit"


@pytest.mark.asyncio
async def test_caller_ack_cannot_suppress_registration_when_locked_progress_is_empty() -> None:
    operation, store, _, _, _ = prepared_operation()
    caller = replace(store.binding.context, checkpoint=ack_for(store))
    result = await operation.prepare(caller)
    assert result is not None and result.context.checkpoint == b""
    assert store.events[-2:] == ["register", "commit"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changed",
    [
        "malformed",
        "foreign-ack",
        "pending",
        "missing-target",
        "published",
        "write-pending",
        "retention",
        "two-targets",
        "wrong-kind",
        "wrong-payload",
        "stale-fence",
        "lost-authority",
    ],
)
async def test_uncertain_or_changed_original_state_never_looks_like_saved_ack(changed: str) -> None:
    operation, store, authority, targets, _ = prepared_operation()
    context = store.binding.context
    if changed == "malformed":
        store.job = replace(store.job, checkpoint=b"artifact.cleanup.delete-ack.v1\0broken")
    elif changed == "foreign-ack":
        store.job = replace(store.job, checkpoint=ack_for(store)[:-16] + uuid4().bytes)
    elif changed == "pending":
        store.job = replace(store.job, checkpoint=ack_for(store), pending_effect="unresolved")
    elif changed == "missing-target":
        targets.target = None
    elif changed == "published":
        authority.facts = replace(authority.facts, published=True)
    elif changed == "write-pending":
        authority.facts = replace(authority.facts, pending_write=True)
    elif changed == "retention":
        authority.facts = replace(authority.facts, retention_allows_cleanup=False)
    elif changed == "two-targets":
        authority.facts = replace(
            authority.facts, targets=authority.facts.targets + (ArtifactAttemptId(uuid4()),)
        )
    elif changed == "wrong-kind":
        assert isinstance(context.binding, ArtifactCleanupJobBindingDTO)
        context = replace(
            context, binding=replace(context.binding, kind=ArtifactCleanupKind.ERASURE)
        )
    elif changed == "wrong-payload":
        context = replace(context, payload=JobPayload("artifact.cleanup", 1, b"another obligation"))
    elif changed == "stale-fence":
        store.fence_error = True
    else:
        authority.denied = True
    with pytest.raises((ConflictError, AccessDeniedError, JobFenceLostError, JobStoppedError)):
        await operation.prepare(context)
    assert "register" not in store.events and store.events[-1] == "rollback"


@pytest.mark.asyncio
async def test_lost_preparation_commit_ack_cannot_grant_dispatch_or_another_invocation() -> None:
    operation, store, _, _, transactions = prepared_operation()
    transactions.commit_error = DependencyUnavailableError("Commit acknowledgment lost.")
    with pytest.raises(DependencyUnavailableError):
        await operation.prepare(store.binding.context)
    transactions.commit_error = None
    with pytest.raises(ConflictError):
        await operation.prepare(store.binding.context)
    assert store.events.count("register") == 1
