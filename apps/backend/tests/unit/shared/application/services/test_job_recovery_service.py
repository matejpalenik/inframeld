import asyncio
from dataclasses import replace
from datetime import timedelta
from typing import override
from uuid import UUID, uuid4

import pytest
from tests.support.job_effect_recovery_handler import (
    MockEffectCleanupAuthority,
    MockEffectProductAuthority,
    MockEffectStore,
    MockEffectTransactions,
    original_effect,
)

from inframeld_backend.access.application.dtos.admitted_work_authority_dto import (
    AdmittedWorkAuthorityDTO,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.shared.application.dtos.artifact_cleanup_job_binding_dto import (
    ArtifactCleanupJobBindingDTO,
)
from inframeld_backend.shared.application.dtos.job_snapshot_dto import JobSnapshotDTO
from inframeld_backend.shared.application.dtos.product_job_binding_dto import ProductJobBindingDTO
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
from inframeld_backend.shared.application.services.job_execution_service import JobExecutionService
from inframeld_backend.shared.application.services.job_recovery_service import JobRecoveryService
from inframeld_backend.shared.application.value_objects.artifact_cleanup_obligation_id import (
    ArtifactCleanupObligationId,
)
from inframeld_backend.shared.application.value_objects.job_fence import JobFence
from inframeld_backend.shared.application.value_objects.job_payload import JobPayload
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.application.value_objects.request_id import RequestId
from inframeld_backend.shared.domain.enums.job_status import JobStatus


@pytest.mark.asyncio
async def test_recovery_consumes_original_proof_before_retiring_without_refunding_attempts() -> (
    None
):
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
    assessment = JobContinuationEligibilityService(
        store,
        MockEffectProductAuthority(store.events),
        MockEffectCleanupAuthority(store),
        supported_payloads=(("artifact.cleanup", 1),),
    )
    result = await JobRecoveryService(store, assessment).recover_in_transaction(store.job)
    assert result.disposition is JobContinuationDisposition.ELIGIBLE
    assert store.events[-2:] == ["consume", "retire"]
    assert store.job.status is JobStatus.QUEUED
    assert store.job.attempt == 1 and store.job.checkpoint == b"checkpoint"
    assert store.job.work_deadline == store.binding.context.work_deadline


@pytest.mark.asyncio
async def test_unknown_effect_is_retired_as_recovery_required_without_consuming() -> None:
    store = MockEffectStore(original_effect())
    store.job = replace(store.job, lease_expires_at=store.job.observed_at - timedelta(seconds=1))
    assessment = JobContinuationEligibilityService(
        store,
        MockEffectProductAuthority(store.events),
        MockEffectCleanupAuthority(store),
        supported_payloads=(("artifact.cleanup", 1),),
    )
    await JobRecoveryService(store, assessment).recover_in_transaction(store.job)
    assert "consume" not in store.events
    assert store.job.status is JobStatus.RECOVERY_REQUIRED


class MockClaimStore(MockEffectStore):
    """Change the selected row after the unlocked observation, before queue ownership."""

    def __init__(self) -> None:
        super().__init__(original_effect())
        self.job = replace(self.job, lease_expires_at=self.job.observed_at - timedelta(seconds=1))
        self.locked_job = self.job

    @override
    async def peek_candidate(self) -> JobSnapshotDTO | None:
        self.events.append("peek")
        return self.job

    @override
    async def next_candidate(self) -> JobSnapshotDTO | None:
        self.events.append("queue")
        return self.locked_job


def execution(store: MockClaimStore, product: MockEffectProductAuthority) -> JobExecutionService:
    eligibility = JobContinuationEligibilityService(
        store,
        product,
        MockEffectCleanupAuthority(store),
        supported_payloads=(("artifact.cleanup", 1), ("inspect.feedback", 1)),
    )
    return JobExecutionService(
        MockEffectTransactions(store.events),
        store,
        worker_id=uuid4(),
        product=product,
        recovery=JobRecoveryService(store, eligibility),
        supported_payloads=(("artifact.cleanup", 1), ("inspect.feedback", 1)),
    )


@pytest.mark.asyncio
async def test_claim_consumes_exact_abort_and_retires_in_the_original_transaction() -> None:
    store = MockClaimStore()
    assert store.observation is not None
    now = store.job.observed_at
    store.locked_job = replace(store.job, observed_at=now + timedelta(milliseconds=1))
    store.observation = replace(
        store.observation,
        admitted_at=now - timedelta(seconds=3),
        kind=JobEffectObservationKind.NOT_DISPATCHED,
        aborted_at=now - timedelta(seconds=2),
    )
    original_deadline = store.job.work_deadline
    assert await execution(store, MockEffectProductAuthority(store.events)).claim_next() is None
    assert store.job.status is JobStatus.QUEUED and store.job.pending_effect is None
    assert store.job.attempt == 1 and store.job.work_deadline == original_deadline
    assert store.events[:3] == ["begin", "peek", "queue"]
    assert store.events[-3:] == ["consume", "retire", "commit"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    ["binding", "checkpoint", "payload", "fence", "attempt", "cancellation", "pending", "deadline"],
)
async def test_changed_locked_candidate_is_not_recovered_or_dispatched(change: str) -> None:
    store = MockClaimStore()
    job = store.job
    if change == "binding":
        assert isinstance(job.binding, ArtifactCleanupJobBindingDTO)
        store.locked_job = replace(
            job, binding=replace(job.binding, obligation_id=ArtifactCleanupObligationId(uuid4()))
        )
    elif change == "checkpoint":
        store.locked_job = replace(job, checkpoint=b"later progress")
    elif change == "payload":
        store.locked_job = replace(job, payload=JobPayload("artifact.cleanup", 1, b"changed"))
    elif change == "fence":
        store.locked_job = replace(job, fence=JobFence(uuid4()))
    elif change == "attempt":
        store.locked_job = replace(job, attempt=2)
    elif change == "cancellation":
        store.locked_job = replace(job, cancel_requested=True)
    elif change == "pending":
        store.locked_job = replace(job, pending_effect="later-unit")
    else:
        assert job.work_deadline is not None
        store.locked_job = replace(job, work_deadline=job.work_deadline + timedelta(seconds=1))
    assert await execution(store, MockEffectProductAuthority(store.events)).claim_next() is None
    assert store.events == ["begin", "peek", "queue", "commit"]
    assert store.job == job


def queued_product(store: MockClaimStore) -> None:
    scope = store.binding.scope
    authority = AdmittedWorkAuthorityDTO(
        PrincipalId(UUID(int=20)),
        PrincipalKind.APPLICATION,
        scope.installation_id,
        scope.organization_id,
        scope.project_id,
        ActionId("inspect-feedback"),
        None,
    )
    binding = ProductJobBindingDTO(
        OperationId("original-operation"), RequestId(UUID(int=21)), authority
    )
    store.job = replace(
        store.job,
        binding=binding,
        payload=JobPayload("inspect.feedback", 1, b"original"),
        status=JobStatus.QUEUED,
        fence=None,
        lease_expires_at=None,
        pending_effect=None,
    )
    store.locked_job = store.job


@pytest.mark.asyncio
async def test_revoked_product_authority_is_checked_before_queue_and_never_dispatched() -> None:
    store = MockClaimStore()
    queued_product(store)
    product = MockEffectProductAuthority(store.events)
    product.denied = True
    assert await execution(store, product).claim_next() is None
    assert store.events == ["begin", "peek", "product", "queue", "retire", "commit"]
    assert store.job.status is JobStatus.FAILED and store.job.reason == "authority_changed"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure", [DependencyUnavailableError("Authority unavailable."), asyncio.CancelledError()]
)
async def test_unavailable_or_cancelled_access_does_not_take_queue_ownership(
    failure: BaseException,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = MockClaimStore()
    queued_product(store)
    product = MockEffectProductAuthority(store.events)

    async def unavailable(authority: AdmittedWorkAuthorityDTO) -> None:
        store.events.append("product")
        raise failure

    monkeypatch.setattr(product, "require_current", unavailable)
    with pytest.raises(type(failure)) as caught:
        await execution(store, product).claim_next()
    assert caught.value is failure
    assert store.events == ["begin", "peek", "product", "rollback"]
