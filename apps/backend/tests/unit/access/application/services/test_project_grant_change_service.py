import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import override
from uuid import UUID

import pytest
from tests.support.authentication_evidence import MockAuthenticationEvidence

from inframeld_backend.access.application.commands.assign_project_use_only_grant_command import (
    AssignProjectUseOnlyGrantCommand,
)
from inframeld_backend.access.application.commands.remove_project_action_grant_command import (
    RemoveProjectActionGrantCommand,
)
from inframeld_backend.access.application.commands.set_project_action_grant_command import (
    SetProjectActionGrantCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_action_grant_change_result_dto import (
    ProjectActionGrantChangeResultDTO,
)
from inframeld_backend.access.application.dtos.project_action_grant_management_facts_dto import (
    ProjectActionGrantManagementFactsDTO,
)
from inframeld_backend.access.application.dtos.project_grant_authorization_dto import (
    ProjectGrantAuthorizationDTO,
)
from inframeld_backend.access.application.dtos.project_grant_change_facts_dto import (
    ProjectGrantChangeFactsDTO,
)
from inframeld_backend.access.application.dtos.project_use_only_grant_authorization_request_dto import (
    ProjectUseOnlyGrantAuthorizationRequestDTO,
)
from inframeld_backend.access.application.enums.project_action_grant_change_kind import (
    ProjectActionGrantChangeKind,
)
from inframeld_backend.access.application.protocols.authorized_operation_scope import (
    AuthorizedOperationScope,
)
from inframeld_backend.access.application.protocols.project_action_grant_result_reader import (
    ProjectActionGrantResultReader,
)
from inframeld_backend.access.application.protocols.project_action_grant_result_writer import (
    ProjectActionGrantResultWriter,
)
from inframeld_backend.access.application.protocols.project_grant_authorizer import (
    ProjectGrantAuthorizer,
)
from inframeld_backend.access.application.protocols.project_grant_management_facts_reader import (
    ProjectGrantManagementFactsReader,
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
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.entities.project_action_grant import ProjectActionGrant
from inframeld_backend.access.domain.entities.project_membership import ProjectMembership
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.enums.project_grant_level import ProjectGrantLevel
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.errors.project_grant_errors import (
    ProjectGrantAlreadyExistsError,
)
from inframeld_backend.access.domain.policy_inputs.project_departure_candidate_policy_input import (
    ProjectDepartureCandidatePolicyInput,
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
from inframeld_backend.shared.application.dtos.idempotency_context_dto import (
    IdempotencyContextDTO,
)
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
    InvalidInputError,
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
from inframeld_backend.shared.application.value_objects.operation_lookup_authority import (
    OperationLookupAuthority,
)
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)
from inframeld_backend.shared.application.value_objects.request_fingerprint_key import (
    RequestFingerprintKey,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


class Phase(StrEnum):
    RESERVATION = "reservation"
    WRITE = "write"
    COMPLETION = "completion"
    COMMIT = "commit"


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
CONTEXT = IdempotencyContextDTO(
    method=HttpMethod.POST,
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
INSTALLATION = InstallationId(UUID(int=5))
ACTOR = Principal(ACTOR_ID, ORGANIZATION_ID, PrincipalKind.HUMAN, PrincipalStatus.ACTIVE)
RECIPIENT = Principal(RECIPIENT_ID, ORGANIZATION_ID, PrincipalKind.HUMAN, PrincipalStatus.ACTIVE)
OTHER = ProjectDepartureCandidatePolicyInput(
    Principal(
        PrincipalId(UUID(int=6)), ORGANIZATION_ID, PrincipalKind.HUMAN, PrincipalStatus.ACTIVE
    ),
    False,
    True,
    True,
    True,
    False,
    False,
)
MANAGEMENT = ProjectActionGrantManagementFactsDTO(
    INSTALLATION,
    ORGANIZATION_ID,
    PROJECT_ID,
    ACTION_ID,
    ProjectGrantChangeFactsDTO(
        ACTOR, False, None, RECIPIENT, ProjectStatus.ACTIVE, 7, True, True, True
    ),
    False,
    True,
    False,
    (OTHER,),
)
SET_COMMAND = SetProjectActionGrantCommand(PROJECT_ID, RECIPIENT_ID, ACTION_ID, False, 7)
REMOVE_COMMAND = RemoveProjectActionGrantCommand(PROJECT_ID, RECIPIENT_ID, ACTION_ID, 7)
ORIGINAL = ProjectActionGrantChangeResultDTO(
    INSTALLATION,
    ORGANIZATION_ID,
    PROJECT_ID,
    ACTOR_ID,
    RECIPIENT_ID,
    ACTION_ID,
    ProjectActionGrantChangeKind.SET,
    False,
    8,
    True,
    201,
    SAVED_RESULT,
)


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
            self.events.append(Phase.COMMIT)


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
        self.context: IdempotencyContextDTO | None = None
        self.access: AccessContextDTO | None = None
        self.authorization: object | None = None
        self.fingerprint: RequestFingerprint | None = None
        self.lookup_authority: OperationLookupAuthority | None = None
        self.expected_kind: OperationReplayKind | None = None

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
        self.lookup_authority = lookup_authority
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
    async def save_action_grant_change(
        self,
        membership: ProjectMembership,
        *,
        action_id: ActionId,
        actor_principal_id: PrincipalId,
        expected_project_access_revision: int,
        operation_id: OperationId,
    ) -> None:
        self.events.append("write_action")
        self.calls += 1
        assert membership is self.result
        assert actor_principal_id == ACTOR_ID
        self.last_revision = expected_project_access_revision
        self.last_operation = operation_id
        if self.error is not None:
            raise self.error

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
        self.events.append(Phase.WRITE)
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

    @override
    def for_set(self, command: SetProjectActionGrantCommand) -> RequestFingerprint:
        self.events.append("fingerprint")
        return super().for_set(command)

    @override
    def for_remove(self, command: RemoveProjectActionGrantCommand) -> RequestFingerprint:
        self.events.append("fingerprint")
        return super().for_remove(command)


class MockManagementFacts(ProjectGrantManagementFactsReader):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.result: ProjectActionGrantManagementFactsDTO | None = MANAGEMENT
        self.error: BaseException | None = None

    @override
    async def read_for_management(
        self,
        *,
        access: AccessContextDTO,
        project_id: ProjectId,
        recipient_principal_id: PrincipalId,
        action_id: ActionId,
    ) -> ProjectActionGrantManagementFactsDTO | None:
        self.events.append("management_facts")
        if self.error is not None:
            raise self.error
        return self.result


class MockGrantResults(ProjectActionGrantResultReader, ProjectActionGrantResultWriter):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.result = ORIGINAL
        self.error: BaseException | None = None
        self.saved: tuple[ProjectActionGrantChangeResultDTO, int, bool | None] | None = None

    @override
    async def original(
        self,
        *,
        facts: ProjectActionGrantManagementFactsDTO,
        command: SetProjectActionGrantCommand | RemoveProjectActionGrantCommand,
        context: IdempotencyContextDTO,
        operation: CompletedSynchronousOperationDTO,
    ) -> ProjectActionGrantChangeResultDTO:
        self.events.append("read_result")
        if self.error is not None:
            raise self.error
        return replace(self.result, operation=operation)

    @override
    async def save(
        self,
        result: ProjectActionGrantChangeResultDTO,
        *,
        before_revision: int,
        before_can_grant: bool | None,
    ) -> None:
        self.events.append("store_result")
        if self.error is not None:
            raise self.error
        self.saved = (result, before_revision, before_can_grant)


class GrantScenario:
    def __init__(self) -> None:
        self.events: list[str] = []
        self.transactions = MockTransactions(self.events)
        self.authorizer = MockProjectGrantAuthorizer(self.events)
        self.idempotency = MockOperationIdempotency(self.events)
        self.memberships = MockProjectMembershipRepository(self.events)
        self.fingerprints = MockFingerprints(self.events)
        self.management = MockManagementFacts(self.events)
        self.results = MockGrantResults(self.events)
        self.service = ProjectGrantChangeService(
            transaction_manager=self.transactions,
            project_grant_authorizer=self.authorizer,
            operation_idempotency=self.idempotency,
            membership_repository=self.memberships,
            project_grant_change_fingerprint_service=self.fingerprints,
            grant_management_facts_reader=self.management,
            grant_result_reader=self.results,
            grant_result_writer=self.results,
        )

    async def assign(
        self, command: AssignProjectUseOnlyGrantCommand = COMMAND
    ) -> CompletedSynchronousOperationDTO:
        return await self.service.assign_use_only(access=ACCESS, command=command, context=CONTEXT)

    async def set(
        self, command: SetProjectActionGrantCommand = SET_COMMAND
    ) -> ProjectActionGrantChangeResultDTO:
        return await self.service.set_action_grant(
            access=ACCESS,
            command=command,
            context=IdempotencyContextDTO(
                HttpMethod.PUT,
                f"/v1/projects/{command.project_id.value}/grants/{command.recipient_principal_id.value}/{command.action_id.value}",
                IdempotencyKey("manage-bob"),
            ),
        )

    async def remove(
        self, command: RemoveProjectActionGrantCommand = REMOVE_COMMAND
    ) -> ProjectActionGrantChangeResultDTO:
        return await self.service.remove_action_grant(
            access=ACCESS,
            command=command,
            context=IdempotencyContextDTO(
                HttpMethod.DELETE,
                f"/v1/projects/{command.project_id.value}/grants/{command.recipient_principal_id.value}/{command.action_id.value}",
                IdempotencyKey("manage-bob"),
            ),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("can_grant", [False, True])
async def test_new_full_assignment_saves_original_status_revision_and_receipt(
    can_grant: bool,
) -> None:
    scenario = GrantScenario()
    scenario.idempotency.result = NEW_RESERVATION
    result = await scenario.set(replace(SET_COMMAND, can_grant=can_grant))
    assert (result.can_grant, result.access_revision, result.changed, result.status_code) == (
        can_grant,
        8,
        True,
        201,
    )
    assert scenario.results.saved == (result, 7, None)
    assert scenario.events == [
        "fingerprint",
        "begin",
        "management_facts",
        "reserve",
        "load_membership",
        "write_action",
        "complete",
        "store_result",
        "commit",
    ]
    assert scenario.idempotency.lookup_authority == OperationLookupAuthority(
        OperationLookupAuthorityFamily.PROJECT_GRANT_READ, ACTION_ID
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("can_grant", [False, True])
async def test_existing_assignment_noop_or_level_change_has_original_200(can_grant: bool) -> None:
    scenario = GrantScenario()
    scenario.idempotency.result = NEW_RESERVATION
    scenario.memberships.result.assign_use_only_grant(
        action_id=ACTION_ID, assigned_by_principal_id=ACTOR_ID
    )
    result = await scenario.set(replace(SET_COMMAND, can_grant=can_grant))
    assert (result.status_code, result.changed, result.access_revision) == (
        200,
        can_grant,
        7 + int(can_grant),
    )
    assert scenario.results.saved == (result, 7, False)


@pytest.mark.asyncio
@pytest.mark.parametrize("blocked", [False, True])
async def test_fresh_removal_can_clear_inactive_or_recovery_blocked_recipient(
    blocked: bool,
) -> None:
    scenario = GrantScenario()
    scenario.idempotency.result = NEW_RESERVATION
    scenario.management.result = replace(
        MANAGEMENT,
        recipient_has_pending_recovery=blocked,
        recipient_has_coherent_identity=False,
        grant=replace(
            MANAGEMENT.grant, recipient=replace(RECIPIENT, status=PrincipalStatus.SUSPENDED)
        ),
    )
    scenario.memberships.result.assign_use_only_grant(
        action_id=ACTION_ID, assigned_by_principal_id=ACTOR_ID
    )
    result = await scenario.remove()
    assert (
        result.change_kind,
        result.can_grant,
        result.status_code,
        result.changed,
        result.access_revision,
    ) == ("remove", None, 200, True, 8)
    assert scenario.memberships.result.grants == ()
    assert scenario.results.saved == (result, 7, False)


@pytest.mark.asyncio
async def test_already_absent_removal_retains_a_no_change_receipt_without_loading_membership() -> (
    None
):
    scenario = GrantScenario()
    scenario.idempotency.result = NEW_RESERVATION
    scenario.management.result = replace(
        MANAGEMENT, grant=replace(MANAGEMENT.grant, recipient_is_project_member=False)
    )
    result = await scenario.remove()
    assert (result.changed, result.access_revision, result.status_code) == (False, 7, 200)
    assert scenario.memberships.loads == scenario.memberships.calls == 0
    assert scenario.results.saved == (result, 7, None)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "facts",
    [
        replace(MANAGEMENT, recipient_has_pending_recovery=True),
        replace(MANAGEMENT, recipient_has_coherent_identity=False),
        replace(MANAGEMENT, grant=replace(MANAGEMENT.grant, recipient_is_project_member=False)),
        replace(
            MANAGEMENT,
            grant=replace(
                MANAGEMENT.grant, recipient=replace(RECIPIENT, status=PrincipalStatus.SUSPENDED)
            ),
        ),
    ],
)
async def test_fresh_put_rejects_ineligible_recipient_after_original_request_lookup(
    facts: ProjectActionGrantManagementFactsDTO,
) -> None:
    scenario = GrantScenario()
    scenario.idempotency.result = NEW_RESERVATION
    scenario.management.result = facts
    with pytest.raises(ConflictError):
        await scenario.set()
    assert scenario.events == ["fingerprint", "begin", "management_facts", "reserve", "rollback"]
    assert scenario.memberships.loads == 0 and scenario.results.saved is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "can_grant,action,allowed",
    [
        (False, "inspect-budget", True),
        (False, "inspect-feedback", True),
        (True, "inspect-budget", False),
        (False, "create-access-groups", False),
    ],
)
async def test_application_put_is_limited_to_eligible_project_use_actions(
    can_grant: bool,
    action: str,
    allowed: bool,
) -> None:
    scenario = GrantScenario()
    scenario.idempotency.result = NEW_RESERVATION
    scenario.management.result = replace(
        MANAGEMENT,
        action_id=ActionId(action),
        recipient_application_is_project_bound=True,
        grant=replace(
            MANAGEMENT.grant, recipient=replace(RECIPIENT, kind=PrincipalKind.APPLICATION)
        ),
    )
    scenario.memberships.result = ProjectMembership(
        organization_id=ORGANIZATION_ID,
        project_id=PROJECT_ID,
        principal_id=RECIPIENT_ID,
        principal_kind=PrincipalKind.APPLICATION,
        grants=(),
    )
    command = replace(SET_COMMAND, action_id=ActionId(action), can_grant=can_grant)
    if allowed:
        result = await scenario.set(command)
        assert result.changed and result.status_code == 201 and not result.can_grant
    else:
        with pytest.raises(InvalidInputError):
            await scenario.set(command)
        assert scenario.memberships.loads == 0 and scenario.results.saved is None


@pytest.mark.asyncio
async def test_completed_put_replays_before_fresh_revision_recipient_or_handover_checks() -> None:
    scenario = GrantScenario()
    scenario.management.result = replace(
        MANAGEMENT,
        recipient_has_pending_recovery=True,
        recipient_has_coherent_identity=False,
        other_grantors=(),
        grant=replace(
            MANAGEMENT.grant,
            project_access_revision=99,
            recipient=None,
            recipient_is_project_member=False,
        ),
    )
    result = await scenario.set()
    assert result == ORIGINAL
    assert scenario.events == [
        "fingerprint",
        "begin",
        "management_facts",
        "reserve",
        "read_result",
        "commit",
    ]
    assert scenario.memberships.loads == 0 and scenario.results.saved is None


@pytest.mark.asyncio
async def test_removal_replay_does_not_delete_an_assignment_created_later() -> None:
    scenario = GrantScenario()
    scenario.results.result = replace(
        ORIGINAL, change_kind="remove", can_grant=None, status_code=200
    )
    scenario.memberships.result.set_action_grant(
        action_id=ACTION_ID,
        level=ProjectGrantLevel.USE_AND_GRANT,
        assigned_by_principal_id=ACTOR_ID,
    )
    later = scenario.memberships.result.grants
    scenario.management.result = replace(
        MANAGEMENT, other_grantors=(), grant=replace(MANAGEMENT.grant, project_access_revision=9)
    )
    result = await scenario.remove()
    assert result == scenario.results.result and result.access_revision == 8
    assert scenario.memberships.result.grants == later
    assert scenario.memberships.loads == scenario.memberships.calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "facts",
    [
        replace(MANAGEMENT, grant=replace(MANAGEMENT.grant, actor_can_grant_action=False)),
        replace(MANAGEMENT, grant=replace(MANAGEMENT.grant, has_pending_recovery=True)),
        replace(
            MANAGEMENT,
            grant=replace(MANAGEMENT.grant, actor=replace(ACTOR, status=PrincipalStatus.SUSPENDED)),
        ),
    ],
)
async def test_current_actor_denial_precedes_even_a_completed_receipt(
    facts: ProjectActionGrantManagementFactsDTO,
) -> None:
    scenario = GrantScenario()
    scenario.management.result = facts
    with pytest.raises(AccessDeniedError):
        await scenario.set()
    assert scenario.idempotency.calls == 0 and "read_result" not in scenario.events


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "unsupported", [False, True], ids=["ineligible-recipient", "unsupported-delegation"]
)
async def test_actor_denial_precedes_fresh_recipient_problem_classification(
    unsupported: bool,
) -> None:
    scenario = GrantScenario()
    scenario.idempotency.result = NEW_RESERVATION
    scenario.management.result = replace(
        MANAGEMENT,
        recipient_has_pending_recovery=True,
        recipient_application_is_project_bound=unsupported,
        grant=replace(
            MANAGEMENT.grant,
            actor_can_grant_action=False,
            recipient=replace(RECIPIENT, kind=PrincipalKind.APPLICATION)
            if unsupported
            else RECIPIENT,
        ),
    )
    with pytest.raises(AccessDeniedError):
        await scenario.set(replace(SET_COMMAND, can_grant=unsupported))
    assert scenario.idempotency.calls == 0 and scenario.memberships.loads == 0
    assert scenario.results.saved is None


@pytest.mark.asyncio
async def test_new_stale_revision_fails_without_a_transition_or_receipt() -> None:
    scenario = GrantScenario()
    scenario.idempotency.result = NEW_RESERVATION
    with pytest.raises(StaleRevisionError):
        await scenario.set(replace(SET_COMMAND, expected_access_revision=6))
    assert scenario.memberships.loads == 0 and scenario.results.saved is None
    assert scenario.events[-1] == "rollback"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "candidate",
    [
        None,
        replace(OTHER, has_pending_recovery=True),
        replace(OTHER, is_project_member=False),
        replace(OTHER, has_coherent_identity=False),
        replace(OTHER, principal=replace(OTHER.principal, status=PrincipalStatus.SUSPENDED)),
        replace(OTHER, principal=replace(OTHER.principal, id=RECIPIENT_ID)),
        replace(OTHER, can_grant=False, is_group_member=True, is_group_manager=True),
    ],
)
@pytest.mark.parametrize("removing", [False, True])
async def test_demotion_or_removal_cannot_strand_exact_project_authority(
    candidate: ProjectDepartureCandidatePolicyInput | None,
    removing: bool,
) -> None:
    scenario = GrantScenario()
    scenario.idempotency.result = NEW_RESERVATION
    scenario.memberships.result.set_action_grant(
        action_id=ACTION_ID,
        level=ProjectGrantLevel.USE_AND_GRANT,
        assigned_by_principal_id=ACTOR_ID,
    )
    scenario.management.result = replace(
        MANAGEMENT, other_grantors=(candidate,) if candidate else ()
    )
    with pytest.raises(ConflictError):
        if removing:
            await scenario.remove()
        else:
            await scenario.set()
    assert scenario.memberships.calls == 0 and scenario.results.saved is None
    assert scenario.memberships.result.grants[0].level is ProjectGrantLevel.USE_AND_GRANT


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_at", ["write", "complete", "receipt", "commit", "cancel"])
async def test_each_required_stage_failure_rolls_back_the_owning_transaction(
    failure_at: str,
) -> None:
    scenario = GrantScenario()
    scenario.idempotency.result = NEW_RESERVATION
    error = RuntimeError("controlled-stage-failure")
    if failure_at == "write":
        scenario.memberships.error = error
    elif failure_at == "complete":
        scenario.idempotency.completion_error = error
    elif failure_at == "receipt":
        scenario.results.error = error
    elif failure_at == "commit":
        scenario.transactions.error = error
    else:
        scenario.management.error = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError if failure_at == "cancel" else RuntimeError):
        await scenario.set()
    assert scenario.events[-1] == "rollback" and "commit" not in scenario.events


@pytest.mark.asyncio
async def test_receipt_cannot_substitute_another_recipient_or_original_level() -> None:
    scenario = GrantScenario()
    scenario.results.result = replace(ORIGINAL, recipient_principal_id=PrincipalId(UUID(int=99)))
    with pytest.raises(ConflictError):
        await scenario.set()
    assert scenario.events[-1] == "rollback"


@pytest.mark.asyncio
async def test_facts_scope_mismatch_is_not_permission_to_reserve_work() -> None:
    scenario = GrantScenario()
    scenario.management.result = replace(MANAGEMENT, project_id=ProjectId(UUID(int=99)))
    with pytest.raises(RuntimeError):
        await scenario.set()
    assert scenario.idempotency.calls == 0


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
    assert scenario.events == ["fingerprint", "begin", "authorize", "reserve", Phase.COMMIT]
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
        Phase.WRITE,
        "complete",
        Phase.COMMIT,
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", [Phase.RESERVATION, Phase.WRITE, Phase.COMPLETION, Phase.COMMIT])
async def test_failures_never_return_a_successful_result(
    phase: Phase,
) -> None:
    scenario = GrantScenario()
    scenario.idempotency.result = NEW_RESERVATION
    error = RuntimeError("injected failure")
    if phase == Phase.RESERVATION:
        scenario.idempotency.error = error
    elif phase == Phase.WRITE:
        scenario.memberships.error = error
    elif phase == Phase.COMPLETION:
        scenario.idempotency.completion_error = error
    else:
        scenario.transactions.error = error
    with pytest.raises(RuntimeError, match="injected failure"):
        await scenario.assign()
    assert Phase.COMMIT not in scenario.events
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
    assert Phase.COMMIT not in scenario.events
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
    assert Phase.COMMIT not in scenario.events
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


@pytest.mark.asyncio
async def test_original_grant_lookup_retains_delegation_authority() -> None:
    scenario = GrantScenario()
    await scenario.assign()
    assert scenario.idempotency.lookup_authority == OperationLookupAuthority(
        OperationLookupAuthorityFamily.PROJECT_GRANT_READ, ACTION_ID
    )
