import asyncio
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import override
from uuid import UUID, uuid4

import pytest

from inframeld_backend.access.application.dtos.human_oauth_cleanup_outcome_dto import (
    HumanOAuthCleanupOutcomeDTO,
)
from inframeld_backend.access.application.dtos.human_session_cleanup_outcome_dto import (
    HumanSessionCleanupOutcomeDTO,
)
from inframeld_backend.access.application.dtos.human_suspension_cleanup_dispatch_dto import (
    HumanSuspensionCleanupDispatchDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.enums.oauth_cleanup_category import OAuthCleanupCategory
from inframeld_backend.access.application.enums.oauth_cleanup_disposition import (
    OAuthCleanupDisposition,
)
from inframeld_backend.access.application.protocols.human_oauth_credential_revoker import (
    HumanOAuthCredentialRevoker,
)
from inframeld_backend.access.application.protocols.human_session_revoker import HumanSessionRevoker
from inframeld_backend.access.application.protocols.human_suspension_cleanup_checkpoint_writer import (
    HumanSuspensionCleanupCheckpointWriter,
)
from inframeld_backend.access.application.protocols.human_suspension_cleanup_claim_writer import (
    HumanSuspensionCleanupClaimWriter,
)
from inframeld_backend.access.application.services.human_suspension_cleanup_execution_service import (
    HumanSuspensionCleanupExecutionService,
)
from inframeld_backend.access.domain.enums.identity_recovery_cleanup_state import (
    IdentityRecoveryCleanupState as State,
)
from inframeld_backend.access.domain.value_objects.human_suspension_id import HumanSuspensionId
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.shared.application.dtos.human_suspension_job_binding_dto import (
    HumanSuspensionJobBindingDTO,
)
from inframeld_backend.shared.application.dtos.job_attempt_context_dto import JobAttemptContextDTO
from inframeld_backend.shared.application.enums.human_suspension_cleanup_step import (
    HumanSuspensionCleanupStep as Step,
)
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.application.protocols.transaction_manager import TransactionManager
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.job_fence import JobFence
from inframeld_backend.shared.application.value_objects.job_id import JobId
from inframeld_backend.shared.application.value_objects.job_payload import JobPayload
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)
from inframeld_backend.shared.application.value_objects.request_id import RequestId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


class Scenario(
    TransactionManager,
    HumanSuspensionCleanupClaimWriter,
    HumanSuspensionCleanupCheckpointWriter,
    HumanSessionRevoker,
    HumanOAuthCredentialRevoker,
):
    def __init__(self) -> None:
        self.binding = HumanSuspensionJobBindingDTO(
            HumanSuspensionId(uuid4()),
            JobId(uuid4()),
            OperationId("suspend"),
            RequestId(uuid4()),
            InstallationId(uuid4()),
            uuid4(),
            uuid4(),
            uuid4(),
            VerifiedHumanIdentityDTO(
                IdentityAuthority("kratos:test"), IdentitySubject(str(uuid4()))
            ),
            IdempotencyKey("original"),
            RequestFingerprint(b"a" * 32),
            0,
            1,
        )
        self.context = JobAttemptContextDTO(
            self.binding.job_id,
            self.binding,
            JobPayload("human.suspension-cleanup", 1, self.binding.obligation_id.value.bytes),
            1,
            JobFence(uuid4()),
            datetime.now(UTC) + timedelta(seconds=20),
            b"",
        )
        self.worker = uuid4()
        self.events: list[str] = []
        self.confirmed: set[Step] = set()
        self.in_transaction = False
        self.marked: Step | None = None
        self.committed: Step | None = None
        self.unknown = False
        self.cancel_provider = False
        self.uncertain_grants = False

    @override
    @asynccontextmanager
    async def begin(self) -> AsyncGenerator[None]:
        assert not self.in_transaction
        self.in_transaction = True
        try:
            yield
            if self.marked is not None:
                self.committed, self.marked = self.marked, None
                if self.unknown:
                    raise DependencyUnavailableError()
        finally:
            self.in_transaction = False

    @override
    async def claim_next(
        self, *, worker_id: UUID, lease_seconds: float, work_seconds: float
    ) -> JobAttemptContextDTO | None:
        assert self.in_transaction and worker_id == self.worker
        assert (lease_seconds, work_seconds) == (60, 7200)
        self.events.append("claim")
        return self.context

    @override
    async def prepare_dispatch(
        self, context: JobAttemptContextDTO, *, worker_id: UUID, step: Step
    ) -> HumanSuspensionCleanupDispatchDTO | None:
        assert self.in_transaction and context == self.context and worker_id == self.worker
        if step in self.confirmed:
            return None
        self.events.append("mark:" + step.value)
        self.marked = step
        return HumanSuspensionCleanupDispatchDTO(self.binding.identity, 3)

    @override
    async def confirm(self, context: JobAttemptContextDTO, *, worker_id: UUID, step: Step) -> None:
        assert self.in_transaction and context == self.context and worker_id == self.worker
        assert self.committed is step
        self.events.append("confirm:" + step.value)
        self.confirmed.add(step)

    @override
    async def stop_unconfirmed(
        self, context: JobAttemptContextDTO, *, worker_id: UUID, step: Step, outcome: State
    ) -> None:
        assert self.in_transaction and context == self.context and worker_id == self.worker
        assert self.committed is step and outcome is State.UNCERTAIN
        self.events.append("stop:" + step.value)

    def _sent(self, step: Step, timeout_seconds: float) -> None:
        assert not self.in_transaction and self.committed is step
        assert 0 < timeout_seconds <= 3
        self.events.append("send:" + step.value)
        if self.cancel_provider:
            raise asyncio.CancelledError

    @override
    async def revoke_sessions(
        self, identity: VerifiedHumanIdentityDTO, *, timeout_seconds: float
    ) -> HumanSessionCleanupOutcomeDTO:
        assert identity == self.binding.identity
        self._sent(Step.KRATOS_SESSIONS, timeout_seconds)
        return HumanSessionCleanupOutcomeDTO(State.CONFIRMED, 204)

    @override
    async def revoke_cli_grants(
        self, subject: IdentitySubject, *, timeout_seconds: float
    ) -> HumanOAuthCleanupOutcomeDTO:
        assert subject == self.binding.identity.subject
        self._sent(Step.HYDRA_CLI_GRANTS, timeout_seconds)
        if self.uncertain_grants:
            return HumanOAuthCleanupOutcomeDTO(
                State.UNCERTAIN,
                OAuthCleanupDisposition.RETRYABLE,
                OAuthCleanupCategory.PROVIDER_TIMEOUT,
            )
        return HumanOAuthCleanupOutcomeDTO(
            State.CONFIRMED,
            OAuthCleanupDisposition.NOT_NEEDED,
            OAuthCleanupCategory.ACKNOWLEDGED,
            204,
        )

    @override
    async def revoke_remembered_logins(
        self, subject: IdentitySubject, *, timeout_seconds: float
    ) -> HumanOAuthCleanupOutcomeDTO:
        assert subject == self.binding.identity.subject
        self._sent(Step.HYDRA_REMEMBERED_LOGINS, timeout_seconds)
        return HumanOAuthCleanupOutcomeDTO(
            State.CONFIRMED,
            OAuthCleanupDisposition.NOT_NEEDED,
            OAuthCleanupCategory.ACKNOWLEDGED,
            204,
        )

    def service(
        self, *, stop_requested: Callable[[], bool] = lambda: False
    ) -> HumanSuspensionCleanupExecutionService:
        return HumanSuspensionCleanupExecutionService(
            self, self, self, self, self, worker_id=self.worker, stop_requested=stop_requested
        )


@pytest.mark.asyncio
async def test_executes_fixed_steps_after_each_marker_commit_without_open_sql() -> None:
    scenario = Scenario()
    assert await scenario.service().execute_once()
    assert scenario.events == ["claim"] + [
        f"{action}:{step.value}" for step in Step for action in ("mark", "send", "confirm")
    ]


@pytest.mark.asyncio
async def test_skips_saved_confirmation_and_stops_on_provider_uncertainty() -> None:
    scenario = Scenario()
    scenario.confirmed.add(Step.KRATOS_SESSIONS)
    scenario.uncertain_grants = True
    assert await scenario.service().execute_once()
    assert scenario.events == [
        "claim",
        "mark:hydra_cli_grants",
        "send:hydra_cli_grants",
        "stop:hydra_cli_grants",
    ]


@pytest.mark.asyncio
async def test_unknown_marker_commit_and_cancellation_leave_no_new_dispatch() -> None:
    unknown = Scenario()
    unknown.unknown = True
    with pytest.raises(DependencyUnavailableError):
        await unknown.service().execute_once()
    assert unknown.events == ["claim", "mark:kratos_sessions"]

    canceled = Scenario()
    canceled.cancel_provider = True
    with pytest.raises(asyncio.CancelledError):
        await canceled.service().execute_once()
    assert canceled.events == ["claim", "mark:kratos_sessions", "send:kratos_sessions"]


@pytest.mark.asyncio
async def test_stop_after_marker_commit_admits_no_provider_call() -> None:
    scenario = Scenario()
    service = scenario.service(stop_requested=lambda: scenario.committed is not None)
    assert await service.execute_once()
    assert scenario.events == ["claim", "mark:kratos_sessions"]
