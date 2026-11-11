"""Exercise admission orchestration with controlled ports, without claiming SQL or worker proof."""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime
from typing import override
from uuid import UUID

import pytest
from tests.support.authentication_evidence import MockAuthenticationEvidence

from inframeld_backend.access.application.commands.delete_project_command import (
    DeleteProjectCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.human_credential_facts_dto import (
    HumanCredentialFactsDTO,
)
from inframeld_backend.access.application.dtos.project_action_authorization_dto import (
    ProjectActionAuthorizationDTO,
)
from inframeld_backend.access.application.dtos.project_action_facts_dto import ProjectActionFactsDTO
from inframeld_backend.access.application.dtos.project_deletion_facts_dto import (
    ProjectDeletionFactsDTO,
)
from inframeld_backend.access.application.dtos.project_deletion_result_dto import (
    ProjectDeletionResultDTO,
)
from inframeld_backend.access.application.errors.human_oauth_credential_rejected_error import (
    HumanOAuthCredentialRejectedError,
)
from inframeld_backend.access.application.protocols.authorized_operation_scope import (
    AuthorizedOperationScope,
)
from inframeld_backend.access.application.protocols.project_deletion_admission_writer import (
    ProjectDeletionAdmissionWriter,
)
from inframeld_backend.access.application.protocols.project_deletion_facts_reader import (
    ProjectDeletionFactsReader,
)
from inframeld_backend.access.application.protocols.project_deletion_result_reader import (
    ProjectDeletionResultReader,
)
from inframeld_backend.access.application.services.project_deletion_fingerprint_service import (
    ProjectDeletionFingerprintService,
)
from inframeld_backend.access.application.services.project_deletion_service import (
    ProjectDeletionService,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_deletion_obligation_id import (
    ProjectDeletionObligationId,
)
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.dtos.accepted_async_operation_dto import (
    AcceptedAsyncOperationDTO,
)
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.dtos.new_operation_reservation_dto import (
    NewOperationReservationDTO,
)
from inframeld_backend.shared.application.dtos.recovery_required_operation_dto import (
    RecoveryRequiredOperationDTO,
)
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.enums.operation_lookup_authority_family import (
    OperationLookupAuthorityFamily,
)
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ConflictError,
    DependencyUnavailableError,
    IdempotencyKeyReusedError,
    ResourceNotFoundError,
    StaleRevisionError,
)
from inframeld_backend.shared.application.errors.job_errors import JobQueueFullError
from inframeld_backend.shared.application.protocols.operation_idempotency import (
    OperationIdempotency,
)
from inframeld_backend.shared.application.protocols.transaction_manager import TransactionManager
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.job_id import JobId
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.application.value_objects.operation_lookup_authority import (
    OperationLookupAuthority,
)
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)
from inframeld_backend.shared.application.value_objects.request_fingerprint_key import (
    RequestFingerprintKey,
)
from inframeld_backend.shared.application.value_objects.request_id import RequestId
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId

INSTALLATION = InstallationId(UUID(int=1))
ORGANIZATION = OrganizationId(UUID(int=2))
PROJECT = ProjectId(UUID(int=3))
ACTOR = PrincipalId(UUID(int=4))
ACCESS = AccessContextDTO(
    ACTOR,
    MockAuthenticationEvidence.browser(
        installation_id=INSTALLATION, version=HumanCredentialVersion(1)
    ),
)
COMMAND = DeleteProjectCommand(PROJECT, 7)
CONTEXT = IdempotencyContextDTO(
    HttpMethod.DELETE, f"/v1/projects/{PROJECT.value}", IdempotencyKey("delete-original")
)
REQUEST = RequestId(UUID(int=5))
OPERATION = OperationId("project-delete-original")
NEW = NewOperationReservationDTO(OPERATION)
ACCEPTED = AcceptedAsyncOperationDTO(OPERATION, True, None)
REPLAY = replace(ACCEPTED, created=False)
FACTS = ProjectDeletionFactsDTO(
    INSTALLATION,
    ORGANIZATION,
    PROJECT,
    7,
    ProjectActionFactsDTO(
        principal=Principal(ACTOR, ORGANIZATION, PrincipalKind.HUMAN, PrincipalStatus.ACTIVE),
        has_pending_recovery=False,
        oauth_credential_facts=HumanCredentialFactsDTO(True, HumanCredentialVersion(1)),
        project_status=ProjectStatus.ACTIVE,
        is_project_member=True,
        has_exact_action_grant=True,
    ),
)
ORIGINAL = ProjectDeletionResultDTO(
    INSTALLATION,
    ORGANIZATION,
    PROJECT,
    ACTOR,
    ProjectDeletionObligationId(UUID(int=6)),
    JobId(UUID(int=7)),
    7,
    8,
    REPLAY,
)
type Outcome = (
    NewOperationReservationDTO
    | AcceptedAsyncOperationDTO
    | CompletedSynchronousOperationDTO
    | RecoveryRequiredOperationDTO
)


class MockTransactions(TransactionManager):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.commit_error: Exception | None = None

    @override
    @asynccontextmanager
    async def begin(self) -> AsyncGenerator[None]:
        self.events.append("begin")
        try:
            yield
        except BaseException:
            self.events.append("rollback")
            raise
        self.events.append("commit")
        if self.commit_error is not None:
            raise self.commit_error


class MockFacts(ProjectDeletionFactsReader):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.result: ProjectDeletionFactsDTO | None = FACTS
        self.stall = False

    @override
    async def lock_for_deletion(
        self, *, access: AccessContextDTO, project_id: ProjectId
    ) -> ProjectDeletionFactsDTO | None:
        self.events.append("facts")
        assert access.actor_principal_id == ACTOR and project_id == PROJECT
        if self.stall:
            await asyncio.Event().wait()
        return self.result


class MockIdempotency(OperationIdempotency):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.result: Outcome = NEW
        self.completion: AcceptedAsyncOperationDTO | CompletedSynchronousOperationDTO = ACCEPTED
        self.error: Exception | None = None
        self.completion_error: Exception | None = None
        self.fingerprint: RequestFingerprint | None = None

    @override
    async def reserve_or_recover[ProjectScope: ProjectId | None](
        self,
        *,
        context: IdempotencyContextDTO,
        access: AccessContextDTO,
        authorization: AuthorizedOperationScope[ProjectScope],
        fingerprint: RequestFingerprint,
        expected_replay_kind: OperationReplayKind,
        lookup_authority: OperationLookupAuthority | None = None,
    ) -> Outcome:
        self.events.append("reserve")
        assert context == CONTEXT and access == ACCESS
        assert authorization.organization_id == ORGANIZATION and authorization.project_id == PROJECT
        assert expected_replay_kind is OperationReplayKind.ASYNC_JOB
        assert lookup_authority == OperationLookupAuthority(
            OperationLookupAuthorityFamily.PROJECT_ACTION_USE,
            # The original lookup rule is ordinary current Delete authority, not erasure authority.
            ActionId("delete-project"),
        )
        self.fingerprint = fingerprint
        if self.error is not None:
            raise self.error
        return self.result

    @override
    async def record_completed_result(
        self, operation: NewOperationReservationDTO, *, replay_kind: OperationReplayKind
    ) -> AcceptedAsyncOperationDTO | CompletedSynchronousOperationDTO:
        self.events.append("complete")
        assert operation == NEW and replay_kind is OperationReplayKind.ASYNC_JOB
        if self.completion_error is not None:
            raise self.completion_error
        return self.completion


class MockAdmission(ProjectDeletionAdmissionWriter):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.error: BaseException | None = None
        self.obligation_id: ProjectDeletionObligationId | None = None
        self.job_id: JobId | None = None
        self.fingerprint: RequestFingerprint | None = None
        self.calls = 0

    @override
    async def admit(
        self,
        *,
        installation_id: InstallationId,
        scope: ProjectActionAuthorizationDTO,
        access: AccessContextDTO,
        command: DeleteProjectCommand,
        context: IdempotencyContextDTO,
        request_id: RequestId,
        reservation: NewOperationReservationDTO,
        fingerprint: RequestFingerprint,
        obligation_id: ProjectDeletionObligationId,
        job_id: JobId,
    ) -> None:
        self.events.append("admit")
        self.calls += 1
        assert (installation_id, scope.organization_id, scope.project_id) == (
            INSTALLATION,
            ORGANIZATION,
            PROJECT,
        )
        assert (access, command, context, request_id, reservation) == (
            ACCESS,
            COMMAND,
            CONTEXT,
            REQUEST,
            NEW,
        )
        self.obligation_id, self.job_id, self.fingerprint = obligation_id, job_id, fingerprint
        if self.error is not None:
            raise self.error


class MockOriginal(ProjectDeletionResultReader):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.result = ORIGINAL

    @override
    async def original(
        self,
        *,
        installation_id: InstallationId,
        organization_id: OrganizationId,
        project_id: ProjectId,
        actor_principal_id: PrincipalId,
        operation: AcceptedAsyncOperationDTO,
    ) -> ProjectDeletionResultDTO:
        self.events.append("original")
        assert (installation_id, organization_id, project_id, actor_principal_id, operation) == (
            INSTALLATION,
            ORGANIZATION,
            PROJECT,
            ACTOR,
            REPLAY,
        )
        return self.result


class DeletionScenario:
    def __init__(self) -> None:
        self.events: list[str] = []
        self.transactions = MockTransactions(self.events)
        self.facts = MockFacts(self.events)
        self.idempotency = MockIdempotency(self.events)
        self.admission = MockAdmission(self.events)
        self.original = MockOriginal(self.events)
        self.service = ProjectDeletionService(
            transaction_manager=self.transactions,
            project_deletion_facts_reader=self.facts,
            project_deletion_admission_writer=self.admission,
            project_deletion_result_reader=self.original,
            operation_idempotency=self.idempotency,
            project_deletion_fingerprint_service=ProjectDeletionFingerprintService(
                RequestFingerprintService(RequestFingerprintKey(b"K" * 32))
            ),
        )

    async def delete(
        self,
        *,
        command: DeleteProjectCommand = COMMAND,
        context: IdempotencyContextDTO = CONTEXT,
        access: AccessContextDTO = ACCESS,
    ) -> ProjectDeletionResultDTO:
        return await self.service.delete(
            access=access,
            command=command,
            context=context,
            request_id=REQUEST,
        )


@pytest.mark.asyncio
async def test_fresh_admission_keeps_exact_original_and_waits_for_commit() -> None:
    scenario = DeletionScenario()
    result = await scenario.delete()
    assert scenario.events == ["begin", "facts", "reserve", "admit", "complete", "commit"]
    assert (
        result.installation_id,
        result.organization_id,
        result.project_id,
        result.actor_principal_id,
    ) == (
        INSTALLATION,
        ORGANIZATION,
        PROJECT,
        ACTOR,
    )
    assert result.operation == ACCEPTED
    assert (result.before_access_revision, result.access_revision) == (7, 8)
    assert result.obligation_id == scenario.admission.obligation_id
    assert result.job_id == scenario.admission.job_id
    assert scenario.idempotency.fingerprint == scenario.admission.fingerprint


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "facts",
    [
        replace(FACTS, action=replace(FACTS.action, has_exact_action_grant=False)),
        replace(FACTS, action=replace(FACTS.action, has_pending_recovery=True)),
        replace(
            FACTS,
            action=replace(
                FACTS.action,
                principal=replace(FACTS.action.principal, status=PrincipalStatus.SUSPENDED),
            ),
        ),
    ],
)
async def test_current_denial_precedes_original_history(facts: ProjectDeletionFactsDTO) -> None:
    scenario = DeletionScenario()
    scenario.facts.result = facts
    scenario.idempotency.result = REPLAY
    with pytest.raises(AccessDeniedError):
        await scenario.delete()
    assert scenario.events == ["begin", "facts", "rollback"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "facts",
    [
        None,
        replace(FACTS, action=replace(FACTS.action, is_project_member=False)),
    ],
)
async def test_missing_or_hidden_project_never_reads_history(
    facts: ProjectDeletionFactsDTO | None,
) -> None:
    scenario = DeletionScenario()
    scenario.facts.result = facts
    scenario.idempotency.result = REPLAY
    with pytest.raises(ResourceNotFoundError):
        await scenario.delete()
    assert "reserve" not in scenario.events


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "facts",
    [
        replace(FACTS, project_id=ProjectId(UUID(int=99))),
        replace(FACTS, organization_id=OrganizationId(UUID(int=99))),
        replace(
            FACTS,
            action=replace(
                FACTS.action,
                principal=replace(FACTS.action.principal, id=PrincipalId(UUID(int=99))),
            ),
        ),
    ],
)
async def test_foreign_returned_scope_fails_before_reservation(
    facts: ProjectDeletionFactsDTO,
) -> None:
    scenario = DeletionScenario()
    scenario.facts.result = facts
    with pytest.raises(RuntimeError, match="scope"):
        await scenario.delete()
    assert "reserve" not in scenario.events


@pytest.mark.asyncio
async def test_accepted_original_precedes_fresh_revision_or_second_admission() -> None:
    scenario = DeletionScenario()
    scenario.idempotency.result = REPLAY
    scenario.facts.result = replace(
        FACTS,
        access_revision=90,
        action=replace(FACTS.action, project_status=ProjectStatus.DELETING),
    )
    assert await scenario.delete() == ORIGINAL
    assert scenario.events == ["begin", "facts", "reserve", "original", "commit"]
    assert scenario.admission.calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "original",
    [
        replace(ORIGINAL, installation_id=InstallationId(UUID(int=99))),
        replace(ORIGINAL, organization_id=OrganizationId(UUID(int=99))),
        replace(ORIGINAL, project_id=ProjectId(UUID(int=99))),
        replace(ORIGINAL, actor_principal_id=PrincipalId(UUID(int=99))),
        replace(ORIGINAL, before_access_revision=6),
        replace(ORIGINAL, access_revision=9),
        replace(ORIGINAL, operation=replace(REPLAY, operation_id=OperationId("other"))),
    ],
)
async def test_incoherent_original_is_not_returned(original: ProjectDeletionResultDTO) -> None:
    scenario = DeletionScenario()
    scenario.idempotency.result = REPLAY
    scenario.original.result = original
    with pytest.raises(ConflictError):
        await scenario.delete()
    assert scenario.admission.calls == 0 and scenario.events[-1] == "rollback"


@pytest.mark.asyncio
async def test_stale_review_does_not_admit_or_complete() -> None:
    scenario = DeletionScenario()
    with pytest.raises(StaleRevisionError):
        await scenario.delete(command=replace(COMMAND, expected_access_revision=6))
    assert "admit" not in scenario.events and "complete" not in scenario.events


@pytest.mark.asyncio
async def test_new_key_cannot_start_another_deletion_in_blocked_scope() -> None:
    scenario = DeletionScenario()
    scenario.facts.result = replace(
        FACTS, action=replace(FACTS.action, project_status=ProjectStatus.DELETING)
    )
    with pytest.raises(ConflictError):
        await scenario.delete()
    assert "admit" not in scenario.events and scenario.events[-1] == "rollback"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error", [IdempotencyKeyReusedError(), ConflictError("Uncertain original.")]
)
async def test_reservation_failures_propagate_without_admission(error: Exception) -> None:
    scenario = DeletionScenario()
    scenario.idempotency.error = error
    with pytest.raises(type(error)) as caught:
        await scenario.delete()
    assert caught.value is error and scenario.admission.calls == 0
    assert scenario.events[-1] == "rollback"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error", [JobQueueFullError(), ConnectionError("Write failed."), asyncio.CancelledError()]
)
async def test_admission_failure_propagates_for_caller_rollback(error: BaseException) -> None:
    scenario = DeletionScenario()
    scenario.admission.error = error
    with pytest.raises(type(error)) as caught:
        await scenario.delete()
    assert caught.value is error
    assert "complete" not in scenario.events and scenario.events[-1] == "rollback"


@pytest.mark.asyncio
async def test_completion_failure_rolls_back_admission_without_redispatch() -> None:
    scenario = DeletionScenario()
    error = ConnectionError("Completion unavailable.")
    scenario.idempotency.completion_error = error
    with pytest.raises(ConnectionError) as caught:
        await scenario.delete()
    assert caught.value is error and scenario.admission.calls == 1
    assert scenario.events[-1] == "rollback"


@pytest.mark.asyncio
async def test_uncertain_commit_is_not_a_response_or_an_automatic_new_attempt() -> None:
    scenario = DeletionScenario()
    error = ConnectionError("Commit acknowledgment missing.")
    scenario.transactions.commit_error = error
    with pytest.raises(ConnectionError) as caught:
        await scenario.delete()
    assert caught.value is error and scenario.admission.calls == 1
    assert scenario.events == ["begin", "facts", "reserve", "admit", "complete", "commit"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "completion",
    [
        replace(ACCEPTED, operation_id=OperationId("other")),
        replace(ACCEPTED, created=False),
        replace(ACCEPTED, expires_at=datetime(2030, 1, 1, tzinfo=UTC)),
    ],
)
async def test_new_unfinished_parent_cannot_change_identity_or_acquire_expiry(
    completion: AcceptedAsyncOperationDTO,
) -> None:
    scenario = DeletionScenario()
    scenario.idempotency.completion = completion
    with pytest.raises(ConflictError):
        await scenario.delete()
    assert scenario.events[-1] == "rollback"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "context",
    [
        replace(CONTEXT, method=HttpMethod.POST),
        replace(CONTEXT, requested_route="/v1/projects/other"),
    ],
)
async def test_changed_method_or_route_fails_before_transaction(
    context: IdempotencyContextDTO,
) -> None:
    scenario = DeletionScenario()
    with pytest.raises(RuntimeError, match="method or route"):
        await scenario.delete(context=context)
    assert scenario.events == []


@pytest.mark.asyncio
async def test_original_database_deadline_bounds_a_stalled_facts_read() -> None:
    scenario = DeletionScenario()
    scenario.facts.stall = True
    with pytest.raises(DependencyUnavailableError):
        await scenario.delete()
    assert scenario.events == ["begin", "facts", "rollback"]


@pytest.mark.asyncio
async def test_application_caller_is_denied_before_history_without_key_fact_fallback() -> None:
    scenario = DeletionScenario()
    application_access = AccessContextDTO(ACTOR, MockAuthenticationEvidence.application_key())
    scenario.facts.result = replace(
        FACTS,
        action=replace(
            FACTS.action, principal=replace(FACTS.action.principal, kind=PrincipalKind.APPLICATION)
        ),
    )
    scenario.idempotency.result = REPLAY
    with pytest.raises(AccessDeniedError):
        await scenario.delete(access=application_access)
    assert scenario.events == ["begin", "facts", "rollback"]


@pytest.mark.asyncio
async def test_changed_human_credential_generation_rejects_before_history() -> None:
    scenario = DeletionScenario()
    oauth_access = AccessContextDTO(
        ACTOR, replace(MockAuthenticationEvidence.human_oauth(), installation_id=INSTALLATION)
    )
    scenario.facts.result = replace(
        FACTS,
        action=replace(
            FACTS.action,
            oauth_credential_facts=HumanCredentialFactsDTO(True, HumanCredentialVersion(2)),
        ),
    )
    scenario.idempotency.result = REPLAY
    with pytest.raises(HumanOAuthCredentialRejectedError):
        await scenario.delete(access=oauth_access)
    assert scenario.events == ["begin", "facts", "rollback"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "operation",
    [
        RecoveryRequiredOperationDTO(OPERATION),
        CompletedSynchronousOperationDTO(
            OPERATION, False, OperationReplayKind.SAFE_RESULT, datetime(2030, 1, 1, tzinfo=UTC)
        ),
    ],
)
async def test_uncertain_or_synchronous_original_is_never_redispatched(operation: Outcome) -> None:
    scenario = DeletionScenario()
    scenario.idempotency.result = operation
    with pytest.raises(ConflictError):
        await scenario.delete()
    assert scenario.events == ["begin", "facts", "reserve", "rollback"]


@pytest.mark.asyncio
async def test_exhausted_access_revision_cannot_admit_a_deletion() -> None:
    scenario = DeletionScenario()
    scenario.facts.result = replace(FACTS, access_revision=RevisionValidation.MAX_VALUE)
    with pytest.raises(ConflictError):
        await scenario.delete(
            command=replace(COMMAND, expected_access_revision=RevisionValidation.MAX_VALUE)
        )
    assert "admit" not in scenario.events and scenario.events[-1] == "rollback"
