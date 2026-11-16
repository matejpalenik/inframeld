import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import override
from uuid import uuid4

import pytest

from inframeld_backend.access.application.dtos.admitted_work_authority_dto import (
    AdmittedWorkAuthorityDTO,
)
from inframeld_backend.access.application.dtos.encrypted_provider_credential_dto import (
    EncryptedProviderCredentialDTO,
)
from inframeld_backend.access.application.dtos.model_connection_access_dto import (
    ModelConnectionAccessDTO,
)
from inframeld_backend.access.application.dtos.provider_credential_binding_dto import (
    ProviderCredentialBindingDTO,
)
from inframeld_backend.access.application.protocols.admitted_work_authorizer import (
    AdmittedWorkAuthorizer,
)
from inframeld_backend.access.application.protocols.model_dispatch_credential_reader import (
    ModelDispatchCredentialReader,
)
from inframeld_backend.access.application.services.model_dispatch_credential_service import (
    ModelDispatchCredentialService,
)
from inframeld_backend.access.domain.enums.model_connection_authentication import (
    ModelConnectionAuthentication,
)
from inframeld_backend.access.domain.enums.model_connection_provider import ModelConnectionProvider
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.policies.model_connection_destination_policy import (
    ModelConnectionDestinationPolicy,
)
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.dtos.job_attempt_context_dto import JobAttemptContextDTO
from inframeld_backend.shared.application.dtos.job_snapshot_dto import JobSnapshotDTO
from inframeld_backend.shared.application.dtos.product_job_binding_dto import ProductJobBindingDTO
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ConflictError,
    DependencyUnavailableError,
    StaleRevisionError,
)
from inframeld_backend.shared.application.errors.job_errors import (
    JobFenceLostError,
    JobStoppedError,
)
from inframeld_backend.shared.application.protocols.job_ownership import JobOwnership
from inframeld_backend.shared.application.value_objects.job_fence import JobFence
from inframeld_backend.shared.application.value_objects.job_id import JobId
from inframeld_backend.shared.application.value_objects.job_payload import JobPayload
from inframeld_backend.shared.application.value_objects.model_connection_id import ModelConnectionId
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.application.value_objects.request_id import RequestId
from inframeld_backend.shared.domain.enums.job_status import JobStatus
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId

_URL = "https://models.example.test/v1"
_OLLAMA_URL = "http://127.0.0.1:11434"
_ACCESS = ModelConnectionAccessDTO(
    ModelConnectionProvider.OPENAI_COMPATIBLE, _URL, None, ModelConnectionAuthentication.API_KEY
)
_DESTINATIONS = ModelConnectionDestinationPolicy(
    https_base_urls=frozenset({_URL}), local_ollama_base_urls=frozenset({_OLLAMA_URL})
)
_AUTHORITY = AdmittedWorkAuthorityDTO(
    principal_id=PrincipalId(uuid4()),
    principal_kind=PrincipalKind.APPLICATION,
    installation_id=InstallationId(uuid4()),
    organization_id=OrganizationId(uuid4()),
    project_id=ProjectId(uuid4()),
    action_id=ActionId("inspect-budget"),
    human_binding=None,
)
_CONNECTION = ModelConnectionId(uuid4())
_BINDING = ProviderCredentialBindingDTO(
    _AUTHORITY.organization_id, _AUTHORITY.project_id, _CONNECTION, uuid4(), 2
)
_ENVELOPE = EncryptedProviderCredentialDTO(1, "xchacha20-poly1305", "a" * 64, b"x" * 54)
_NOW = datetime.now(UTC)
_ATTEMPT = JobAttemptContextDTO(
    job_id=JobId(uuid4()),
    binding=ProductJobBindingDTO(OperationId("model-consumer"), RequestId(uuid4()), _AUTHORITY),
    payload=JobPayload("fixture.model_consumer", 1, b""),
    attempt=1,
    fence=JobFence(uuid4()),
    work_deadline=_NOW + timedelta(hours=1),
    checkpoint=b"",
)


class MockDispatchFacts(ModelDispatchCredentialReader):
    def __init__(self) -> None:
        self.events: list[str] = []
        self.authority_denied = False
        self.fence_lost = False
        self.fence_waiting: asyncio.Event | None = None
        self.canceled = False
        self.access: tuple[ModelConnectionAccessDTO, int] | None = (_ACCESS, 3)
        self.sealed: tuple[ProviderCredentialBindingDTO, EncryptedProviderCredentialDTO] | None = (
            _BINDING,
            _ENVELOPE,
        )

    @override
    async def read_access(
        self, authority: AdmittedWorkAuthorityDTO, connection_id: ModelConnectionId
    ) -> tuple[ModelConnectionAccessDTO, int] | None:
        assert authority == _AUTHORITY and connection_id == _CONNECTION
        self.events.append("exact_use")
        return self.access

    @override
    async def read_sealed(
        self,
        authority: AdmittedWorkAuthorityDTO,
        connection_id: ModelConnectionId,
        access_revision: int,
    ) -> tuple[ProviderCredentialBindingDTO, EncryptedProviderCredentialDTO] | None:
        assert (authority, connection_id, access_revision) == (_AUTHORITY, _CONNECTION, 3)
        self.events.append("sealed")
        return self.sealed


class MockAuthority(AdmittedWorkAuthorizer):
    def __init__(self, facts: MockDispatchFacts) -> None:
        self.facts = facts

    @override
    async def require_current(self, authority: AdmittedWorkAuthorityDTO) -> None:
        assert authority == _AUTHORITY
        self.facts.events.append("authority")
        if self.facts.authority_denied:
            raise AccessDeniedError()


class MockJobOwnership(JobOwnership):
    def __init__(self, facts: MockDispatchFacts) -> None:
        self.facts = facts

    @override
    async def require_current(self, context: JobAttemptContextDTO) -> JobSnapshotDTO:
        assert context == _ATTEMPT
        self.facts.events.append("fence")
        if self.facts.fence_lost:
            raise JobFenceLostError()
        if self.facts.fence_waiting is not None:
            self.facts.fence_waiting.set()
            await asyncio.Event().wait()
        return JobSnapshotDTO(
            job_id=context.job_id,
            binding=context.binding,
            payload=context.payload,
            status=JobStatus.RUNNING,
            admitted_at=_NOW,
            queued_deadline=_NOW + timedelta(hours=24),
            due_at=_NOW,
            observed_at=_NOW,
            attempt=context.attempt,
            work_deadline=context.work_deadline,
            fence=context.fence,
            lease_expires_at=_NOW + timedelta(seconds=30),
            cancel_requested=self.facts.canceled,
            pending_effect=None,
            reason=None,
            checkpoint=context.checkpoint,
        )

    @override
    async def require_issued_attempt(self, context: JobAttemptContextDTO) -> None:
        pytest.fail("Issued history cannot authorize credential reads.")


def _service(facts: MockDispatchFacts) -> ModelDispatchCredentialService:
    return ModelDispatchCredentialService(
        MockAuthority(facts), MockJobOwnership(facts), facts, _DESTINATIONS
    )


@pytest.mark.asyncio
async def test_reads_current_sealed_slot_only_after_authority_fence_and_use() -> None:
    facts = MockDispatchFacts()

    result = await _service(facts).read(
        attempt=_ATTEMPT, connection_id=_CONNECTION, admitted_access_revision=3
    )

    assert result.access == _ACCESS and result.access_revision == 3
    assert result.binding == _BINDING and result.envelope == _ENVELOPE
    assert "envelope" not in repr(result)
    assert facts.events == ["authority", "fence", "exact_use", "sealed"]


@pytest.mark.asyncio
async def test_a_stalled_fence_fails_before_looking_up_the_connection() -> None:
    facts = MockDispatchFacts()
    facts.fence_waiting = asyncio.Event()

    with pytest.raises(DependencyUnavailableError, match="job ownership exceeded"):
        await asyncio.wait_for(
            _service(facts).read(
                attempt=_ATTEMPT, connection_id=_CONNECTION, admitted_access_revision=3
            ),
            timeout=7,
        )

    assert facts.events == ["authority", "fence"]


@pytest.mark.asyncio
async def test_caller_cancellation_propagates_during_a_stalled_fence() -> None:
    facts = MockDispatchFacts()
    started = asyncio.Event()
    facts.fence_waiting = started

    async with asyncio.TaskGroup() as group:
        reading = group.create_task(
            _service(facts).read(
                attempt=_ATTEMPT, connection_id=_CONNECTION, admitted_access_revision=3
            )
        )
        await asyncio.wait_for(started.wait(), timeout=2)
        reading.cancel()
        with pytest.raises(asyncio.CancelledError):
            await reading

    assert facts.events == ["authority", "fence"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "condition", ["authority", "fence", "cancel", "use", "revision", "url", "no-key"]
)
async def test_denial_does_not_disclose_the_sealed_slot(condition: str) -> None:
    facts = MockDispatchFacts()
    expected: type[Exception]
    if condition == "authority":
        facts.authority_denied, expected = True, AccessDeniedError
    elif condition == "fence":
        facts.fence_lost, expected = True, JobFenceLostError
    elif condition == "cancel":
        facts.canceled, expected = True, JobStoppedError
    elif condition == "use":
        facts.access, expected = None, AccessDeniedError
    elif condition == "revision":
        facts.access, expected = (_ACCESS, 4), StaleRevisionError
    elif condition == "url":
        facts.access = (replace(_ACCESS, base_url="https://other.example.test/v1"), 3)
        expected = AccessDeniedError
    else:
        facts.access = (
            ModelConnectionAccessDTO(
                ModelConnectionProvider.OLLAMA,
                _OLLAMA_URL,
                None,
                ModelConnectionAuthentication.NONE,
            ),
            3,
        )
        expected = ConflictError

    with pytest.raises(expected):
        await _service(facts).read(
            attempt=_ATTEMPT, connection_id=_CONNECTION, admitted_access_revision=3
        )

    assert "sealed" not in facts.events


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", [True, False])
async def test_unusable_slot_never_returns_a_snapshot(missing: bool) -> None:
    facts = MockDispatchFacts()
    facts.sealed = (
        None
        if missing
        else (replace(_BINDING, connection_id=ModelConnectionId(uuid4())), _ENVELOPE)
    )
    with pytest.raises(ConflictError if missing else DependencyUnavailableError):
        await _service(facts).read(
            attempt=_ATTEMPT, connection_id=_CONNECTION, admitted_access_revision=3
        )
