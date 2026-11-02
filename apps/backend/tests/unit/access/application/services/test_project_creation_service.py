import asyncio
from dataclasses import dataclass, replace
from typing import override
from uuid import UUID

import pytest
from tests.support.mock_project_metadata import (
    ACCESS,
    NEW_RESERVATION,
    SAVED_RESULT,
    MockOperationIdempotency,
    MockTransactions,
)

from inframeld_backend.access.application.commands.create_project_command import (
    CreateProjectCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.created_project_dto import CreatedProjectDTO
from inframeld_backend.access.application.dtos.project_creation_authorization_dto import (
    ProjectCreationAuthorizationDTO,
)
from inframeld_backend.access.application.protocols.project_creation_authorizer import (
    ProjectCreationAuthorizer,
)
from inframeld_backend.access.application.protocols.project_creation_result_reader import (
    ProjectCreationResultReader,
)
from inframeld_backend.access.application.protocols.project_creation_writer import (
    ProjectCreationWriter,
)
from inframeld_backend.access.application.services.project_creation_fingerprint_service import (
    ProjectCreationFingerprintService,
)
from inframeld_backend.access.application.services.project_creation_service import (
    ProjectCreationService,
)
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.dtos.operation_admission_context_dto import (
    OperationAdmissionContextDTO,
)
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ConflictError,
    StaleRevisionError,
)
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.application.value_objects.request_fingerprint_key import (
    RequestFingerprintKey,
)
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName
from inframeld_backend.shared.domain.value_objects.submitted_display_name import (
    SubmittedDisplayName,
)

INITIAL_ACTIONS = tuple(
    ActionId(value)
    for value in (
        "manage-project-members",
        "create-access-groups",
        "create-application-accounts",
        "create-pipelines",
        "create-deployments",
        "manage-upload-defaults",
        "delete-project",
        "inspect-budget",
        "manage-budget",
        "manage-trace-policy",
        "delete-trace-history",
        "inspect-feedback",
        "create-collections",
        "create-sources",
        "create-model-connections",
        "create-processing-profiles",
        "create-embedding-profiles",
        "edit-project-metadata",
    )
)
COMMAND = CreateProjectCommand(
    OrganizationId(UUID(int=2)), 7, ResourceName("production"), SubmittedDisplayName("Production")
)
CONTEXT = OperationAdmissionContextDTO("POST", "/v1/projects", IdempotencyKey("create-original"))
ORIGINAL = CreatedProjectDTO(
    SAVED_RESULT.operation_id,
    COMMAND.organization_id,
    ProjectId(UUID(int=3)),
    ACCESS.actor_principal_id,
    COMMAND.name,
    COMMAND.display_name.value,
    1,
    0,
    INITIAL_ACTIONS,
)


class MockCreationAuthorizer(ProjectCreationAuthorizer):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.scope = ProjectCreationAuthorizationDTO(COMMAND.organization_id, 7)
        self.error: Exception | None = None

    @override
    async def require_creation(
        self, *, access: AccessContextDTO, organization_id: OrganizationId
    ) -> ProjectCreationAuthorizationDTO:
        self.events.append("authorize")
        if self.error:
            raise self.error
        return self.scope


class MockCreationWriter(ProjectCreationWriter):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.projects: list[CreatedProjectDTO] = []
        self.error: BaseException | None = None
        self.pause: asyncio.Event | None = None
        self.entered = asyncio.Event()

    @override
    async def create(
        self, *, project: CreatedProjectDTO, expected_organization_revision: int
    ) -> None:
        self.events.append("write")
        assert expected_organization_revision == 7
        self.projects.append(project)
        self.entered.set()
        if self.pause:
            await self.pause.wait()
        if self.error:
            raise self.error


class MockCreationResults(ProjectCreationResultReader):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.result: CreatedProjectDTO | None = ORIGINAL

    @override
    async def original(
        self, *, organization_id: OrganizationId, actor_id: PrincipalId, operation_id: OperationId
    ) -> CreatedProjectDTO:
        self.events.append("original")
        assert organization_id == COMMAND.organization_id and actor_id == ACCESS.actor_principal_id
        assert operation_id == SAVED_RESULT.operation_id
        if self.result is None:
            raise ConflictError()
        return self.result


@dataclass
class CreationScenarioDTO:
    service: ProjectCreationService
    events: list[str]
    authorizer: MockCreationAuthorizer
    writer: MockCreationWriter
    results: MockCreationResults
    idempotency: MockOperationIdempotency
    transactions: MockTransactions


@pytest.fixture
def scenario() -> CreationScenarioDTO:
    events: list[str] = []
    authorizer, writer, results = (
        MockCreationAuthorizer(events),
        MockCreationWriter(events),
        MockCreationResults(events),
    )
    idempotency, transactions = MockOperationIdempotency(events), MockTransactions(events)
    return CreationScenarioDTO(
        ProjectCreationService(
            transactions=transactions,
            authorizer=authorizer,
            writer=writer,
            results=results,
            idempotency=idempotency,
            fingerprints=ProjectCreationFingerprintService(
                RequestFingerprintService(RequestFingerprintKey(b"k" * 32))
            ),
        ),
        events,
        authorizer,
        writer,
        results,
        idempotency,
        transactions,
    )


@pytest.mark.asyncio
async def test_new_project_uses_original_org_scope_and_commits_one_fixed_creator_seed(
    scenario: CreationScenarioDTO,
) -> None:
    scenario.idempotency.result = NEW_RESERVATION
    result = await scenario.service.create(access=ACCESS, command=COMMAND, context=CONTEXT)
    assert scenario.events == ["begin", "authorize", "reserve", "write", "complete", "commit"]
    assert result.operation.created
    assert result.project.operation_id == NEW_RESERVATION.operation_id
    assert result.project.organization_id == COMMAND.organization_id
    assert result.project.creator_principal_id == ACCESS.actor_principal_id
    assert result.project.name == COMMAND.name and result.project.display_name == "Production"
    assert result.project.access_revision == 1 and result.project.metadata_revision == 0
    assert result.project.initial_actions == INITIAL_ACTIONS
    assert len(scenario.writer.projects) == 1
    assert scenario.idempotency.authorization == scenario.authorizer.scope
    assert scenario.authorizer.scope.project_id is None
    assert scenario.authorizer.scope.access_revision == 7
    assert scenario.idempotency.lookup_authority is not None
    assert scenario.idempotency.lookup_authority.action_id == ActionId("create-projects")
    assert scenario.idempotency.lookup_authority.family.value == "organization_action_use"


@pytest.mark.asyncio
async def test_replay_uses_original_snapshot_and_expiry_before_fresh_revision_check(
    scenario: CreationScenarioDTO,
) -> None:
    scenario.authorizer.scope = replace(scenario.authorizer.scope, access_revision=99)
    result = await scenario.service.create(access=ACCESS, command=COMMAND, context=CONTEXT)
    assert result.project == ORIGINAL and result.operation == SAVED_RESULT
    assert scenario.events == ["begin", "authorize", "reserve", "original", "commit"]
    assert scenario.writer.projects == []


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["denied", "wrong-scope"])
async def test_authorization_must_succeed_and_match_before_reservation(
    scenario: CreationScenarioDTO, failure: str
) -> None:
    if failure == "denied":
        scenario.authorizer.error = AccessDeniedError()
    else:
        scenario.authorizer.scope = replace(
            scenario.authorizer.scope, organization_id=OrganizationId(UUID(int=9))
        )
    with pytest.raises(AccessDeniedError if failure == "denied" else RuntimeError):
        await scenario.service.create(access=ACCESS, command=COMMAND, context=CONTEXT)
    assert scenario.events == ["begin", "authorize", "rollback"]
    assert scenario.idempotency.calls == 0 and scenario.writer.projects == []


@pytest.mark.asyncio
async def test_new_request_with_stale_org_revision_rolls_back_without_creating(
    scenario: CreationScenarioDTO,
) -> None:
    scenario.idempotency.result = NEW_RESERVATION
    with pytest.raises(StaleRevisionError):
        await scenario.service.create(
            access=ACCESS, command=replace(COMMAND, expected_access_revision=6), context=CONTEXT
        )
    assert scenario.events == ["begin", "authorize", "reserve", "rollback"]
    assert scenario.writer.projects == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changed",
    [
        "missing",
        "organization",
        "actor",
        "operation",
        "access-revision",
        "metadata-revision",
        "grant-snapshot",
    ],
)
async def test_missing_or_incoherent_original_result_never_reconstructs_state(
    scenario: CreationScenarioDTO, changed: str
) -> None:
    if changed == "missing":
        scenario.results.result = None
    elif changed == "organization":
        scenario.results.result = replace(ORIGINAL, organization_id=OrganizationId(UUID(int=9)))
    elif changed == "actor":
        scenario.results.result = replace(ORIGINAL, creator_principal_id=PrincipalId(UUID(int=9)))
    elif changed == "operation":
        scenario.results.result = replace(ORIGINAL, operation_id=OperationId("different-original"))
    elif changed == "access-revision":
        scenario.results.result = replace(ORIGINAL, access_revision=2)
    elif changed == "metadata-revision":
        scenario.results.result = replace(ORIGINAL, metadata_revision=1)
    else:
        scenario.results.result = replace(ORIGINAL, initial_actions=INITIAL_ACTIONS[:-1])
    with pytest.raises(ConflictError):
        await scenario.service.create(access=ACCESS, command=COMMAND, context=CONTEXT)
    assert scenario.events[-1] == "rollback" and scenario.writer.projects == []


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary", ["write", "completion", "commit"])
async def test_required_writes_and_uncertain_commit_never_return_success_or_retry(
    scenario: CreationScenarioDTO, boundary: str
) -> None:
    scenario.idempotency.result = NEW_RESERVATION
    failure = RuntimeError("Controlled atomic creation failure")
    if boundary == "write":
        scenario.writer.error = failure
    elif boundary == "completion":
        scenario.idempotency.completion_error = failure
    else:
        scenario.transactions.error = failure
    with pytest.raises(RuntimeError) as error:
        await scenario.service.create(access=ACCESS, command=COMMAND, context=CONTEXT)
    assert error.value is failure
    assert len(scenario.writer.projects) == 1 and scenario.events[-1] == "rollback"
    if boundary == "write":
        assert "complete" not in scenario.events


@pytest.mark.asyncio
async def test_cancellation_keeps_transaction_rollback_and_does_not_complete(
    scenario: CreationScenarioDTO,
) -> None:
    scenario.idempotency.result = NEW_RESERVATION
    scenario.writer.pause = asyncio.Event()
    task = asyncio.create_task(
        scenario.service.create(access=ACCESS, command=COMMAND, context=CONTEXT)
    )
    try:
        await asyncio.wait_for(scenario.writer.entered.wait(), 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert scenario.events[-1] == "rollback" and "complete" not in scenario.events
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
