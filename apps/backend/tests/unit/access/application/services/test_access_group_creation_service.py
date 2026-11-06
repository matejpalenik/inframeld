"""Check original creation identity and current authority before retained-history access."""

from dataclasses import dataclass, replace
from typing import override
from uuid import UUID

import pytest
from tests.support.mock_project_metadata import (
    ACCESS,
    NEW_RESERVATION,
    ORGANIZATION_ID,
    PROJECT_ID,
    SAVED_RESULT,
    MockOperationIdempotency,
    MockTransactions,
)

from inframeld_backend.access.application.commands.create_access_group_command import (
    CreateAccessGroupCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.access_group_creation_facts_dto import (
    AccessGroupCreationFactsDTO,
)
from inframeld_backend.access.application.dtos.created_access_group_dto import (
    CreatedAccessGroupDTO,
)
from inframeld_backend.access.application.dtos.project_action_facts_dto import ProjectActionFactsDTO
from inframeld_backend.access.application.protocols.access_group_creation_facts_reader import (
    AccessGroupCreationFactsReader,
)
from inframeld_backend.access.application.protocols.access_group_creation_result_reader import (
    AccessGroupCreationResultReader,
)
from inframeld_backend.access.application.protocols.access_group_creation_writer import (
    AccessGroupCreationWriter,
)
from inframeld_backend.access.application.services.access_group_creation_fingerprint_service import (
    AccessGroupCreationFingerprintService,
)
from inframeld_backend.access.application.services.access_group_creation_service import (
    AccessGroupCreationService,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ConflictError,
    ResourceNotFoundError,
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
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName
from inframeld_backend.shared.domain.value_objects.submitted_display_name import (
    SubmittedDisplayName,
)

COMMAND = CreateAccessGroupCommand(
    PROJECT_ID, 7, ResourceName("support-knowledge"), SubmittedDisplayName("SupportKnowledge")
)
CONTEXT = IdempotencyContextDTO(
    HttpMethod.POST,
    f"/v1/projects/{PROJECT_ID.value}/access-groups",
    IdempotencyKey("create-original"),
)
ORIGINAL = CreatedAccessGroupDTO(
    operation_id=SAVED_RESULT.operation_id,
    organization_id=ORGANIZATION_ID,
    project_id=PROJECT_ID,
    group_id=AccessGroupId(UUID(int=8)),
    creator_principal_id=ACCESS.actor_principal_id,
    name=COMMAND.name,
    display_name=COMMAND.display_name.value,
    access_revision=8,
)
FACTS = AccessGroupCreationFactsDTO(
    organization_id=ORGANIZATION_ID,
    project_id=PROJECT_ID,
    access_revision=7,
    action=ProjectActionFactsDTO(
        principal=Principal(
            ACCESS.actor_principal_id, ORGANIZATION_ID, PrincipalKind.HUMAN, PrincipalStatus.ACTIVE
        ),
        has_pending_recovery=False,
        oauth_credential_facts=None,
        project_status=ProjectStatus.ACTIVE,
        is_project_member=True,
        has_exact_action_grant=True,
    ),
)


class MockCreationFacts(AccessGroupCreationFactsReader):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.result: AccessGroupCreationFactsDTO | None = FACTS

    @override
    async def lock_for_creation(
        self, *, access: AccessContextDTO, project_id: ProjectId
    ) -> AccessGroupCreationFactsDTO | None:
        self.events.append("authorize")
        return self.result


class MockCreationWriter(AccessGroupCreationWriter):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.groups: list[CreatedAccessGroupDTO] = []
        self.error: Exception | None = None

    @override
    async def create(self, *, group: CreatedAccessGroupDTO, expected_project_revision: int) -> None:
        self.events.append("write")
        assert expected_project_revision == 7
        self.groups.append(group)
        if self.error is not None:
            raise self.error


class MockCreationResults(AccessGroupCreationResultReader):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.result = ORIGINAL

    @override
    async def original(
        self,
        *,
        organization_id: OrganizationId,
        project_id: ProjectId,
        actor_id: PrincipalId,
        operation_id: OperationId,
    ) -> CreatedAccessGroupDTO:
        self.events.append("original")
        assert (organization_id, project_id, actor_id, operation_id) == (
            ORGANIZATION_ID,
            PROJECT_ID,
            ACCESS.actor_principal_id,
            SAVED_RESULT.operation_id,
        )
        return self.result


@dataclass
class CreationScenarioDTO:
    service: AccessGroupCreationService
    events: list[str]
    facts: MockCreationFacts
    writer: MockCreationWriter
    results: MockCreationResults
    idempotency: MockOperationIdempotency
    transactions: MockTransactions


@pytest.fixture
def scenario() -> CreationScenarioDTO:
    events: list[str] = []
    facts, writer, results = (
        MockCreationFacts(events),
        MockCreationWriter(events),
        MockCreationResults(events),
    )
    idempotency, transactions = MockOperationIdempotency(events), MockTransactions(events)
    service = AccessGroupCreationService(
        transaction_manager=transactions,
        creation_facts_reader=facts,
        creation_writer=writer,
        creation_result_reader=results,
        operation_idempotency=idempotency,
        creation_fingerprint_service=AccessGroupCreationFingerprintService(
            RequestFingerprintService(RequestFingerprintKey(b"K" * 32))
        ),
    )
    return CreationScenarioDTO(service, events, facts, writer, results, idempotency, transactions)


@pytest.mark.asyncio
async def test_create_commits_one_distinct_group_and_creator_membership_without_document_grants(
    scenario: CreationScenarioDTO,
) -> None:
    scenario.idempotency.result = NEW_RESERVATION
    result = await scenario.service.create(access=ACCESS, command=COMMAND, context=CONTEXT)
    group = result.group
    assert group.group_id.value != ACCESS.actor_principal_id.value
    assert (group.organization_id, group.project_id, group.creator_principal_id) == (
        ORGANIZATION_ID,
        PROJECT_ID,
        ACCESS.actor_principal_id,
    )
    assert (
        group.name,
        group.display_name,
        group.access_revision,
    ) == (COMMAND.name, "SupportKnowledge", 8)
    assert scenario.writer.groups == [group]
    assert result.operation.created
    assert scenario.events == ["begin", "authorize", "reserve", "write", "complete", "commit"]
    assert scenario.idempotency.lookup_authority is not None
    assert scenario.idempotency.lookup_authority.action_id == ActionId("create-access-groups")


@pytest.mark.asyncio
async def test_replay_returns_original_group_without_restoring_membership(
    scenario: CreationScenarioDTO,
) -> None:
    scenario.facts.result = replace(FACTS, access_revision=32)
    result = await scenario.service.create(access=ACCESS, command=COMMAND, context=CONTEXT)
    assert result.group == ORIGINAL and result.operation == SAVED_RESULT
    assert not scenario.writer.groups
    assert scenario.events == ["begin", "authorize", "reserve", "original", "commit"]


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["grant", "recovery", "membership", "suspended"])
async def test_lost_authority_cannot_search_history_or_create(
    scenario: CreationScenarioDTO, change: str
) -> None:
    action = FACTS.action
    if change == "grant":
        action = replace(action, has_exact_action_grant=False)
    elif change == "recovery":
        action = replace(action, has_pending_recovery=True)
    elif change == "membership":
        action = replace(action, is_project_member=False)
    else:
        action = replace(
            action, principal=replace(action.principal, status=PrincipalStatus.SUSPENDED)
        )
    scenario.facts.result = replace(FACTS, action=action)
    with pytest.raises((AccessDeniedError, ResourceNotFoundError)):
        await scenario.service.create(access=ACCESS, command=COMMAND, context=CONTEXT)
    assert scenario.idempotency.calls == 0 and not scenario.writer.groups
    assert scenario.events == ["begin", "authorize", "rollback"]


@pytest.mark.asyncio
async def test_stale_fresh_review_cannot_write(scenario: CreationScenarioDTO) -> None:
    scenario.idempotency.result = NEW_RESERVATION
    with pytest.raises(StaleRevisionError):
        await scenario.service.create(
            access=ACCESS, command=replace(COMMAND, expected_access_revision=6), context=CONTEXT
        )
    assert not scenario.writer.groups
    assert scenario.events[-1] == "rollback"


@pytest.mark.asyncio
async def test_exhausted_fresh_revision_cannot_create(scenario: CreationScenarioDTO) -> None:
    scenario.facts.result = replace(FACTS, access_revision=RevisionValidation.MAX_VALUE)
    scenario.idempotency.result = NEW_RESERVATION
    with pytest.raises(ConflictError):
        await scenario.service.create(
            access=ACCESS,
            command=replace(COMMAND, expected_access_revision=RevisionValidation.MAX_VALUE),
            context=CONTEXT,
        )
    assert not scenario.writer.groups


@pytest.mark.asyncio
async def test_audit_or_commit_failure_does_not_return_success(
    scenario: CreationScenarioDTO,
) -> None:
    scenario.idempotency.result = NEW_RESERVATION
    scenario.writer.error = RuntimeError("Controlled required audit failure")
    with pytest.raises(RuntimeError):
        await scenario.service.create(access=ACCESS, command=COMMAND, context=CONTEXT)
    assert "complete" not in scenario.events and scenario.events[-1] == "rollback"


@pytest.mark.parametrize("revision", [-1, True, 1.0, RevisionValidation.MAX_VALUE + 1])
def test_creation_command_rejects_inexact_or_unsupported_revision(revision: int) -> None:
    with pytest.raises((TypeError, ValueError)):
        replace(COMMAND, expected_access_revision=revision)
