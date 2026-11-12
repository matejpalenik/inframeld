from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import override
from uuid import UUID, uuid4

import pytest
from tests.support.job_effect_recovery_handler import original_effect

from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.domain.value_objects.human_suspension_id import HumanSuspensionId
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.shared.application.dtos.human_suspension_job_binding_dto import (
    HumanSuspensionJobBindingDTO,
)
from inframeld_backend.shared.application.dtos.human_suspension_job_facts_dto import (
    HumanSuspensionJobFactsDTO,
)
from inframeld_backend.shared.application.dtos.job_attempt_context_dto import JobAttemptContextDTO
from inframeld_backend.shared.application.errors.application_errors import AccessDeniedError
from inframeld_backend.shared.application.protocols.human_suspension_job_facts_reader import (
    HumanSuspensionJobFactsReader,
)
from inframeld_backend.shared.application.services.human_suspension_job_authorization_service import (
    HumanSuspensionJobAuthorizationService,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.job_fence import JobFence
from inframeld_backend.shared.application.value_objects.job_payload import JobPayload
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)
from inframeld_backend.shared.application.value_objects.request_id import RequestId


class FactsReader(HumanSuspensionJobFactsReader):
    def __init__(self, facts: HumanSuspensionJobFactsDTO | None) -> None:
        self.facts = facts
        self.calls: list[tuple[JobAttemptContextDTO, UUID]] = []

    @override
    async def read_live_attempt(
        self, context: JobAttemptContextDTO, *, worker_id: UUID
    ) -> HumanSuspensionJobFactsDTO | None:
        self.calls.append((context, worker_id))
        return self.facts


def _live() -> tuple[JobAttemptContextDTO, HumanSuspensionJobFactsDTO]:
    effect = original_effect()
    binding = HumanSuspensionJobBindingDTO(
        obligation_id=HumanSuspensionId(uuid4()),
        job_id=effect.context.job_id,
        operation_id=OperationId("original-suspension"),
        request_id=RequestId(uuid4()),
        installation_id=effect.scope.installation_id,
        organization_id=effect.scope.organization_id.value,
        principal_id=uuid4(),
        initiator_principal_id=uuid4(),
        identity=VerifiedHumanIdentityDTO(IdentityAuthority("test"), IdentitySubject("subject")),
        key=IdempotencyKey("suspension"),
        fingerprint=RequestFingerprint(b"f" * 32),
        before_access_revision=4,
        access_revision=5,
    )
    payload = JobPayload("human.suspension-cleanup", 1, binding.obligation_id.value.bytes)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    deadline = now + timedelta(minutes=2)
    context = replace(
        effect.context, binding=binding, payload=payload, attempt=1, work_deadline=deadline
    )
    return context, HumanSuspensionJobFactsDTO(
        binding=binding,
        payload=payload,
        attempt=context.attempt,
        fence=context.fence,
        worker_id=uuid4(),
        work_deadline=deadline,
        lease_expires_at=now + timedelta(seconds=30),
        observed_at=now,
        source_revision=1,
    )


@pytest.mark.asyncio
async def test_exact_live_suspension_authority_passes_the_original_observation() -> None:
    context, facts = _live()
    reader = FactsReader(facts)
    assert (
        await HumanSuspensionJobAuthorizationService(reader).require_current(
            context, worker_id=facts.worker_id
        )
        is facts
    )
    assert reader.calls == [(context, facts.worker_id)]


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["binding", "fence", "lease", "worker", "version"])
async def test_missing_or_crossed_suspension_facts_do_not_authorize(change: str) -> None:
    context, facts = _live()
    if change == "binding":
        observed = None
    elif change == "fence":
        observed = replace(facts, fence=JobFence(uuid4()))
    elif change == "lease":
        observed = replace(facts, lease_expires_at=facts.observed_at)
    elif change == "worker":
        observed = replace(facts, worker_id=uuid4())
    else:
        assert change == "version"
        observed = replace(facts, source_revision=0)
    reader = FactsReader(observed)
    with pytest.raises(AccessDeniedError):
        await HumanSuspensionJobAuthorizationService(reader).require_current(
            context, worker_id=facts.worker_id
        )
    assert reader.calls == [(context, facts.worker_id)]


@pytest.mark.asyncio
async def test_artifact_context_never_reaches_suspension_facts_reader() -> None:
    _, facts = _live()
    reader = FactsReader(facts)
    with pytest.raises(AccessDeniedError):
        await HumanSuspensionJobAuthorizationService(reader).require_current(
            original_effect().context, worker_id=facts.worker_id
        )
    assert reader.calls == []
