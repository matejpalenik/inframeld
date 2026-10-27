from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime
from typing import Literal, override
from uuid import UUID

import pytest
from tests.support.authentication_evidence import MockAuthenticationEvidence

from inframeld_backend.access.application.commands.assign_project_use_only_grant_command import (
    AssignProjectUseOnlyGrantCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_grant_authorization_dto import (
    ProjectGrantAuthorizationDTO,
)
from inframeld_backend.access.application.dtos.project_use_only_grant_authorization_request_dto import (
    ProjectUseOnlyGrantAuthorizationRequestDTO,
)
from inframeld_backend.access.application.protocols.authorized_operation_scope import (
    AuthorizedOperationScope,
)
from inframeld_backend.access.application.protocols.project_grant_authorizer import (
    ProjectGrantAuthorizer,
)
from inframeld_backend.access.application.protocols.project_membership_repository import (
    ProjectMembershipRepository,
)
from inframeld_backend.access.application.services.project_grant_change_fingerprint_service import (
    ProjectGrantChangeFingerprintService,
)
from inframeld_backend.access.application.services.project_grant_change_service import (
    ProjectGrantChangeService,
)
from inframeld_backend.access.domain.entities.project_action_grant import ProjectActionGrant
from inframeld_backend.access.domain.entities.project_membership import ProjectMembership
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.project_grant_level import ProjectGrantLevel
from inframeld_backend.access.domain.errors.project_grant_errors import (
    ProjectGrantAlreadyExistsError,
)
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.dtos.accepted_async_operation_dto import (
    AcceptedAsyncOperationDTO,
)
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.dtos.new_operation_reservation_dto import (
    NewOperationReservationDTO,
)
from inframeld_backend.shared.application.dtos.operation_admission_context_dto import (
    OperationAdmissionContextDTO,
)
from inframeld_backend.shared.application.dtos.recovery_required_operation_dto import (
    RecoveryRequiredOperationDTO,
)
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ConflictError,
    ResourceNotFoundError,
    StaleRevisionError,
)
from inframeld_backend.shared.application.protocols.operation_idempotency import (
    OperationIdempotency,
)
from inframeld_backend.shared.application.protocols.transaction_manager import TransactionManager
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)
from inframeld_backend.shared.application.value_objects.request_fingerprint_key import (
    RequestFingerprintKey,
)

ACTOR_ID = PrincipalId(UUID(int=1))
RECIPIENT_ID = PrincipalId(UUID(int=2))
ORGANIZATION_ID = OrganizationId(UUID(int=3))
PROJECT_ID = ProjectId(UUID(int=4))
ACTION_ID = ActionId("create-access-groups")
ACCESS = AccessContextDTO(
    actor_principal_id=ACTOR_ID, authentication_evidence=MockAuthenticationEvidence.browser()
)
AUTHORIZATION = ProjectGrantAuthorizationDTO(
    organization_id=ORGANIZATION_ID, project_id=PROJECT_ID, project_access_revision=7
)
COMMAND = AssignProjectUseOnlyGrantCommand(PROJECT_ID, RECIPIENT_ID, ACTION_ID, 7)
CONTEXT = OperationAdmissionContextDTO(
    method="POST",
    requested_route="/v1/projects/{project_id}/grants",
    key=IdempotencyKey("assign-bob-1"),
)
SAVED_RESULT = CompletedSynchronousOperationDTO(
    operation_id=OperationId("saved-grant"),
    created=False,
    replay_kind=OperationReplayKind.SAFE_RESULT,
    expires_at=datetime(2030, 1, 1, tzinfo=UTC),
)
NEW_RESERVATION = NewOperationReservationDTO(SAVED_RESULT.operation_id)


class MockTransactions(TransactionManager):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.error: Exception | None = None

    @override
    @asynccontextmanager
    async def begin(self) -> AsyncGenerator[None]:
        self.events.append("begin")
        try:
            yield
            if self.error is not None:
                raise self.error
        except BaseException:
            self.events.append("rollback")
            raise
        else:
            self.events.append("commit")


class MockProjectGrantAuthorizer(ProjectGrantAuthorizer):
    """Support changed authority on a later attempt without caching approval."""

    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.error: Exception | None = None
        self.calls = 0
        self.result = AUTHORIZATION
        self.last_request: tuple[AccessContextDTO, ProjectId, PrincipalId, ActionId] | None = None

    @override
    async def require_authorization(
        self, *, access: AccessContextDTO, request: ProjectUseOnlyGrantAuthorizationRequestDTO
    ) -> ProjectGrantAuthorizationDTO:
        self.events.append("authorize")
        self.calls += 1
        self.last_request = (
            access,
            request.project_id,
            request.recipient_principal_id,
            request.action_id,
        )
        if self.error is not None:
            raise self.error
        return self.result


class MockOperationIdempotency(OperationIdempotency):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.result: (
            NewOperationReservationDTO
            | CompletedSynchronousOperationDTO
            | AcceptedAsyncOperationDTO
            | RecoveryRequiredOperationDTO
        ) = SAVED_RESULT
        self.completed_result: CompletedSynchronousOperationDTO | AcceptedAsyncOperationDTO = (
            replace(SAVED_RESULT, created=True)
        )
        self.error: Exception | None = None
        self.completion_error: Exception | None = None
        self.calls = 0
        self.context: OperationAdmissionContextDTO | None = None
        self.access: AccessContextDTO | None = None
        self.authorization: object | None = None
        self.fingerprint: RequestFingerprint | None = None
        self.expected_kind: OperationReplayKind | None = None

    @override
    async def find_or_reserve[ProjectScope: ProjectId | None](
        self,
        *,
        context: OperationAdmissionContextDTO,
        access: AccessContextDTO,
        authorization: AuthorizedOperationScope[ProjectScope],
        fingerprint: RequestFingerprint,
        expected_replay_kind: OperationReplayKind,
    ) -> (
        NewOperationReservationDTO
        | CompletedSynchronousOperationDTO
        | AcceptedAsyncOperationDTO
        | RecoveryRequiredOperationDTO
    ):
        self.events.append("reserve")
        self.calls += 1
        self.context = context
        self.access = access
        self.authorization = authorization
        self.fingerprint = fingerprint
        self.expected_kind = expected_replay_kind
        assert expected_replay_kind is OperationReplayKind.SAFE_RESULT
        if self.error is not None:
            raise self.error
        return self.result

    @override
    async def record_completed_result(
        self, operation: NewOperationReservationDTO, *, replay_kind: OperationReplayKind
    ) -> CompletedSynchronousOperationDTO | AcceptedAsyncOperationDTO:
        self.events.append("complete")
        assert operation == NEW_RESERVATION
        assert replay_kind is OperationReplayKind.SAFE_RESULT
        if self.completion_error is not None:
            raise self.completion_error
        return self.completed_result


class MockProjectMembershipRepository(ProjectMembershipRepository):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.error: Exception | None = None
        self.load_error: Exception | None = None
        self.calls = 0
        self.loads = 0
        self.last_operation: OperationId | None = None
        self.last_project_id: ProjectId | None = None
        self.last_revision: int | None = None
        self.result = ProjectMembership(
            organization_id=ORGANIZATION_ID,
            project_id=PROJECT_ID,
            principal_id=RECIPIENT_ID,
            principal_kind=PrincipalKind.HUMAN,
            grants=(),
        )

    @override
    async def get(
        self, *, organization_id: OrganizationId, project_id: ProjectId, principal_id: PrincipalId
    ) -> ProjectMembership:
        self.events.append("load_membership")
        self.loads += 1
        self.last_project_id = project_id
        assert (organization_id, project_id, principal_id) == (
            ORGANIZATION_ID,
            PROJECT_ID,
            RECIPIENT_ID,
        )
        if self.load_error is not None:
            raise self.load_error
        return self.result

    @override
    async def save(
        self,
        membership: ProjectMembership,
        *,
        expected_project_access_revision: int,
        operation_id: OperationId,
    ) -> None:
        self.events.append("write")
        self.calls += 1
        assert membership is self.result
        grant = membership.grants[0]
        assert (
            grant.project_id,
            grant.recipient_principal_id,
            grant.action_id,
            grant.assigned_by_principal_id,
            grant.level,
        ) == (PROJECT_ID, RECIPIENT_ID, ACTION_ID, ACTOR_ID, ProjectGrantLevel.USE_ONLY)
        self.last_revision = expected_project_access_revision
        assert expected_project_access_revision == 7
        self.last_operation = operation_id
        if self.error is not None:
            raise self.error


class MockFingerprints(ProjectGrantChangeFingerprintService):
    def __init__(self, events: list[str]) -> None:
        super().__init__(RequestFingerprintService(RequestFingerprintKey(b"K" * 32)))
        self.events = events

    @override
    def for_assign_use_only(self, command: AssignProjectUseOnlyGrantCommand) -> RequestFingerprint:
        self.events.append("fingerprint")
        return super().for_assign_use_only(command)


class GrantScenario:
    def __init__(self) -> None:
        self.events: list[str] = []
        self.transactions = MockTransactions(self.events)
        self.authorizer = MockProjectGrantAuthorizer(self.events)
        self.idempotency = MockOperationIdempotency(self.events)
        self.memberships = MockProjectMembershipRepository(self.events)
        self.fingerprints = MockFingerprints(self.events)
        self.service = ProjectGrantChangeService(
            transactions=self.transactions,
            authorizer=self.authorizer,
            idempotency=self.idempotency,
            memberships=self.memberships,
            fingerprints=self.fingerprints,
        )

    async def assign(
        self, command: AssignProjectUseOnlyGrantCommand = COMMAND
    ) -> CompletedSynchronousOperationDTO:
        return await self.service.assign_use_only(access=ACCESS, command=command, context=CONTEXT)


@pytest.mark.asyncio
@pytest.mark.parametrize("error_type", [AccessDeniedError, ResourceNotFoundError])
async def test_denied_authorization_does_not_reserve_work(
    error_type: type[AccessDeniedError | ResourceNotFoundError],
) -> None:
    """Authorization failure must stop the workflow before any reservation."""
    scenario = GrantScenario()
    scenario.authorizer.error = error_type()
    with pytest.raises(error_type):
        await scenario.assign()
    assert scenario.idempotency.calls == 0
    assert scenario.memberships.calls == 0
    assert scenario.memberships.loads == 0
    assert scenario.events == ["fingerprint", "begin", "authorize", "rollback"]


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", [NEW_RESERVATION, SAVED_RESULT], ids=["new", "replay"])
async def test_mismatched_authorized_project_stops_before_reservation_or_replay(
    operation: NewOperationReservationDTO | CompletedSynchronousOperationDTO,
) -> None:
    """A broken authorizer must not redirect either a new grant or a saved replay."""
    scenario = GrantScenario()
    scenario.authorizer.result = replace(AUTHORIZATION, project_id=ProjectId(UUID(int=5)))
    scenario.idempotency.result = operation

    with pytest.raises(RuntimeError, match="Authorization returned a different project"):
        await scenario.assign()

    assert scenario.idempotency.calls == 0
    assert scenario.memberships.calls == 0
    assert scenario.memberships.loads == 0
    assert scenario.events == ["fingerprint", "begin", "authorize", "rollback"]


@pytest.mark.asyncio
async def test_replay_rechecks_authorization_before_returning_saved_result() -> None:
    """A prior success cannot bypass changed authority on the next request."""
    scenario = GrantScenario()
    old_command = replace(COMMAND, expected_access_revision=0)
    first = await scenario.assign(old_command)
    assert first == SAVED_RESULT
    assert scenario.authorizer.last_request == (ACCESS, PROJECT_ID, RECIPIENT_ID, ACTION_ID)
    expected_fingerprint = ProjectGrantChangeFingerprintService(
        RequestFingerprintService(RequestFingerprintKey(b"K" * 32))
    ).for_assign_use_only(old_command)
    assert scenario.idempotency.context is CONTEXT
    assert scenario.idempotency.access is ACCESS
    assert scenario.idempotency.authorization is AUTHORIZATION
    assert scenario.idempotency.fingerprint == expected_fingerprint
    assert scenario.idempotency.expected_kind is OperationReplayKind.SAFE_RESULT
    assert scenario.events == ["fingerprint", "begin", "authorize", "reserve", "commit"]
    assert scenario.memberships.calls == 0
    assert scenario.memberships.loads == 0
    scenario.authorizer.error = AccessDeniedError()
    with pytest.raises(AccessDeniedError):
        await scenario.assign(old_command)
    assert scenario.authorizer.calls == 2
    assert scenario.idempotency.calls == 1


@pytest.mark.asyncio
async def test_new_work_rejects_a_stale_revision_before_writing_grant() -> None:
    """New assignments must match the revision established by authorization."""
    scenario = GrantScenario()
    scenario.idempotency.result = NEW_RESERVATION
    with pytest.raises(StaleRevisionError):
        await scenario.assign(replace(COMMAND, expected_access_revision=0))
    assert scenario.idempotency.calls == 1
    assert scenario.memberships.calls == 0
    assert scenario.memberships.loads == 0
    assert scenario.events[-1] == "rollback"


@pytest.mark.asyncio
async def test_new_assignment_completes_before_transaction_commit() -> None:
    scenario = GrantScenario()
    scenario.authorizer.result = replace(AUTHORIZATION, project_id=ProjectId(PROJECT_ID.value))
    scenario.idempotency.result = NEW_RESERVATION
    result = await scenario.assign()
    assert result == replace(SAVED_RESULT, created=True)
    assert scenario.memberships.last_operation == NEW_RESERVATION.operation_id
    assert scenario.memberships.last_project_id is scenario.authorizer.result.project_id
    assert scenario.events == [
        "fingerprint",
        "begin",
        "authorize",
        "reserve",
        "load_membership",
        "write",
        "complete",
        "commit",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["reservation", "write", "completion", "commit"])
async def test_failures_never_return_a_successful_result(
    phase: Literal["reservation", "write", "completion", "commit"],
) -> None:
    scenario = GrantScenario()
    scenario.idempotency.result = NEW_RESERVATION
    error = RuntimeError("injected failure")
    if phase == "reservation":
        scenario.idempotency.error = error
    elif phase == "write":
        scenario.memberships.error = error
    elif phase == "completion":
        scenario.idempotency.completion_error = error
    else:
        scenario.transactions.error = error
    with pytest.raises(RuntimeError, match="injected failure"):
        await scenario.assign()
    assert "commit" not in scenario.events
    assert scenario.events[-1] == "rollback"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "outcome",
    [
        RecoveryRequiredOperationDTO(SAVED_RESULT.operation_id),
        AcceptedAsyncOperationDTO(SAVED_RESULT.operation_id, False, None),
        replace(SAVED_RESULT, replay_kind=OperationReplayKind.ISSUED_SECRET),
    ],
)
async def test_non_grant_outcomes_are_rejected_inside_the_transaction(
    outcome: RecoveryRequiredOperationDTO
    | AcceptedAsyncOperationDTO
    | CompletedSynchronousOperationDTO,
) -> None:
    """Recovery and incompatible outcomes cannot become a completed grant response."""
    scenario = GrantScenario()
    scenario.idempotency.result = outcome
    with pytest.raises(ConflictError):
        await scenario.assign()
    assert scenario.memberships.calls == 0
    assert scenario.memberships.loads == 0
    assert scenario.events[-1] == "rollback"


@pytest.mark.asyncio
async def test_unexpected_async_completion_cannot_commit_a_grant() -> None:
    scenario = GrantScenario()
    scenario.idempotency.result = NEW_RESERVATION
    scenario.idempotency.completed_result = AcceptedAsyncOperationDTO(
        SAVED_RESULT.operation_id, True, None
    )
    with pytest.raises(ConflictError):
        await scenario.assign()
    assert scenario.memberships.calls == 1
    assert "commit" not in scenario.events
    assert scenario.events[-1] == "rollback"


@pytest.mark.asyncio
@pytest.mark.parametrize("scope", ["organization", "project", "recipient"])
async def test_loaded_membership_must_match_the_authorized_assignment(scope: str) -> None:
    """A broken repository must not redirect an authorized grant to another member."""
    scenario = GrantScenario()
    scenario.idempotency.result = NEW_RESERVATION
    scenario.memberships.result = ProjectMembership(
        organization_id=OrganizationId(UUID(int=9)) if scope == "organization" else ORGANIZATION_ID,
        project_id=ProjectId(UUID(int=9)) if scope == "project" else PROJECT_ID,
        principal_id=PrincipalId(UUID(int=9)) if scope == "recipient" else RECIPIENT_ID,
        principal_kind=PrincipalKind.HUMAN,
        grants=(),
    )
    with pytest.raises(RuntimeError, match="loaded membership"):
        await scenario.assign()
    assert scenario.memberships.calls == 0
    assert scenario.memberships.result.grants == ()
    assert "complete" not in scenario.events
    assert scenario.events[-1] == "rollback"


@pytest.mark.asyncio
@pytest.mark.parametrize("level", list(ProjectGrantLevel))
async def test_existing_domain_assignment_becomes_the_existing_conflict(
    level: ProjectGrantLevel,
) -> None:
    scenario = GrantScenario()
    scenario.idempotency.result = NEW_RESERVATION
    original = ProjectActionGrant(PROJECT_ID, RECIPIENT_ID, ACTION_ID, level, None)
    scenario.memberships.result = ProjectMembership(
        organization_id=ORGANIZATION_ID,
        project_id=PROJECT_ID,
        principal_id=RECIPIENT_ID,
        principal_kind=PrincipalKind.HUMAN,
        grants=(original,),
    )
    with pytest.raises(ConflictError, match="already exists"):
        await scenario.assign()
    assert scenario.memberships.loads == 1
    assert scenario.memberships.calls == 0
    assert scenario.memberships.result.grants[0] is original
    assert scenario.events[-1] == "rollback"


@pytest.mark.asyncio
async def test_duplicate_conflict_message_is_independent_of_domain_wording(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Internal domain diagnostics must not change the application conflict message."""
    scenario = GrantScenario()
    scenario.idempotency.result = NEW_RESERVATION
    domain_error = ProjectGrantAlreadyExistsError("An internal assignment invariant failed.")

    def mock_assign_use_only_grant(
        membership: ProjectMembership,
        *,
        action_id: ActionId,
        assigned_by_principal_id: PrincipalId,
    ) -> None:
        assert membership is scenario.memberships.result
        assert action_id == ACTION_ID
        assert assigned_by_principal_id == ACTOR_ID
        raise domain_error

    monkeypatch.setattr(ProjectMembership, "assign_use_only_grant", mock_assign_use_only_grant)

    with pytest.raises(ConflictError) as caught:
        await scenario.assign()

    assert caught.value.message == "This project action grant already exists."
    assert caught.value.__cause__ is domain_error
    assert scenario.memberships.loads == 1
    assert scenario.memberships.calls == 0
    assert scenario.memberships.result.grants == ()
    assert "complete" not in scenario.events
    assert "commit" not in scenario.events
    assert scenario.events[-1] == "rollback"


@pytest.mark.asyncio
async def test_membership_loading_failure_rolls_back_without_completion() -> None:
    scenario = GrantScenario()
    scenario.idempotency.result = NEW_RESERVATION
    scenario.memberships.load_error = ResourceNotFoundError()
    with pytest.raises(ResourceNotFoundError):
        await scenario.assign()
    assert scenario.memberships.calls == 0
    assert "complete" not in scenario.events
    assert scenario.events[-1] == "rollback"
