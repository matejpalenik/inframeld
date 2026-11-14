from dataclasses import replace
from typing import Literal, override
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

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.application_key_authentication_dto import (
    ApplicationKeyAuthenticationDTO,
)
from inframeld_backend.access.application.dtos.human_credential_facts_dto import (
    HumanCredentialFactsDTO,
)
from inframeld_backend.access.application.dtos.project_action_facts_dto import ProjectActionFactsDTO
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.value_objects.application_key_id import ApplicationKeyId
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.indexing.application.commands.create_processing_profile_command import (
    CreateProcessingProfileCommand,
)
from inframeld_backend.indexing.application.dtos.processing_profile_creation_dto import (
    ProcessingProfileCreationDTO,
)
from inframeld_backend.indexing.application.dtos.processing_profile_creation_facts_dto import (
    ProcessingProfileCreationFactsDTO,
)
from inframeld_backend.indexing.application.dtos.processing_profile_dto import ProcessingProfileDTO
from inframeld_backend.indexing.application.protocols.processing_profile_creation_repository import (
    ProcessingProfileCreationRepository,
)
from inframeld_backend.indexing.application.services.processing_profile_creation_service import (
    ProcessingProfileCreationService,
)
from inframeld_backend.indexing.domain.enums.processing_profile_action import (
    ProcessingProfileAction,
)
from inframeld_backend.indexing.domain.value_objects.docling_processing_definition import (
    DoclingProcessingDefinition,
)
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.enums.operation_lookup_authority_family import (
    OperationLookupAuthorityFamily,
)
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ConflictError,
    DependencyUnavailableError,
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

COMMAND = CreateProcessingProfileCommand(
    project_id=PROJECT_ID,
    name=ResourceName("handbook"),
    display_name=SubmittedDisplayName("Support handbook"),
    definition=DoclingProcessingDefinition(
        docling_slim_version="2.148.0",
        docling_core_version="2.106.0",
        asset_manifest_sha256="7ea9f3c967a7bc66d2501e466334e7aef46a639e01a11376888321e0f0a51d0e",
        max_content_tokens=640,
        merge_peers=True,
        repeat_table_header=False,
        ocr_enabled=False,
    ),
)
CONTEXT = IdempotencyContextDTO(
    HttpMethod.POST,
    f"/v1/projects/{PROJECT_ID.value}/processing-profiles",
    IdempotencyKey("processing-profile-create"),
)
FACTS = ProcessingProfileCreationFactsDTO(
    organization_id=ORGANIZATION_ID,
    project_id=PROJECT_ID,
    access_revision=7,
    action=ProjectActionFactsDTO(
        Principal(
            ACCESS.actor_principal_id, ORGANIZATION_ID, PrincipalKind.HUMAN, PrincipalStatus.ACTIVE
        ),
        False,
        HumanCredentialFactsDTO(True, HumanCredentialVersion(1)),
        ProjectStatus.ACTIVE,
        True,
        True,
    ),
)


class MockCreationRepository(ProcessingProfileCreationRepository):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.facts = FACTS
        self.saved: ProcessingProfileCreationDTO | None = None
        self.access = ACCESS

    @override
    async def lock_for_creation(
        self, *, access: AccessContextDTO, project_id: ProjectId
    ) -> ProcessingProfileCreationFactsDTO:
        assert self.events == ["begin"]
        self.events.append("authority")
        assert access == self.access
        assert project_id == COMMAND.project_id
        return self.facts

    @override
    async def original(
        self,
        *,
        access: AccessContextDTO,
        facts: ProcessingProfileCreationFactsDTO,
        operation: CompletedSynchronousOperationDTO,
    ) -> ProcessingProfileCreationDTO:
        self.events.append("original")
        assert access == ACCESS and facts == self.facts and operation == SAVED_RESULT
        assert self.saved is not None
        return self.saved

    @override
    async def save(
        self,
        *,
        access: AccessContextDTO,
        facts: ProcessingProfileCreationFactsDTO,
        operation_id: OperationId,
        profile: ProcessingProfileDTO,
        initial_actions: tuple[ProcessingProfileAction, ...],
        can_grant: Literal[True],
    ) -> None:
        self.events.append("save")
        assert (
            access == ACCESS and facts == self.facts and operation_id == SAVED_RESULT.operation_id
        )
        assert self.saved is None
        self.saved = ProcessingProfileCreationDTO(
            profile=profile,
            operation=SAVED_RESULT,
            project_access_revision=facts.access_revision + 1,
            initial_actions=initial_actions,
            can_grant=can_grant,
        )


@pytest.mark.asyncio
async def test_ordinary_creation_owns_the_transaction_and_returns_after_commit() -> None:
    events: list[str] = []
    idempotency = MockOperationIdempotency(events)
    idempotency.result = NEW_RESERVATION
    service = ProcessingProfileCreationService(
        MockCreationRepository(events),
        idempotency,
        RequestFingerprintService(RequestFingerprintKey(b"P" * 32)),
        transactions=MockTransactions(events),
    )

    result = await service.create(access=ACCESS, command=COMMAND, context=CONTEXT)

    assert result is not None and result.operation.created
    assert events == ["begin", "authority", "reserve", "save", "complete", "commit"]


@pytest.mark.asyncio
async def test_ordinary_creation_returns_unavailable_when_commit_times_out() -> None:
    events: list[str] = []
    idempotency = MockOperationIdempotency(events)
    idempotency.result = NEW_RESERVATION
    transactions = MockTransactions(events)
    transactions.error = TimeoutError()
    service = ProcessingProfileCreationService(
        MockCreationRepository(events),
        idempotency,
        RequestFingerprintService(RequestFingerprintKey(b"P" * 32)),
        transactions=transactions,
    )

    with pytest.raises(DependencyUnavailableError):
        await service.create(access=ACCESS, command=COMMAND, context=CONTEXT)

    assert events == ["begin", "authority", "reserve", "save", "complete", "rollback"]


@pytest.mark.asyncio
async def test_creation_and_replay_preserve_the_exact_profile_and_creator_assignments() -> None:
    events: list[str] = []
    repository = MockCreationRepository(events)
    idempotency = MockOperationIdempotency(events)
    transactions = MockTransactions(events)
    service = ProcessingProfileCreationService(
        repository,
        idempotency,
        RequestFingerprintService(RequestFingerprintKey(b"P" * 32)),
        transactions=transactions,
    )
    idempotency.result = NEW_RESERVATION

    async with transactions.begin():
        result = await service.create_in_transaction(
            access=ACCESS, command=COMMAND, context=CONTEXT
        )

    assert result is not None
    assert result.profile.id.value != UUID(int=0)
    assert result.profile.project_id == PROJECT_ID
    assert result.profile.name == COMMAND.name
    assert result.profile.display_name == COMMAND.display_name
    assert result.profile.definition == COMMAND.definition
    assert tuple(action.value for action in result.initial_actions) == (
        "view-processing-profile",
        "use-processing-profile",
    )
    assert result.can_grant is True and result.project_access_revision == 8
    assert result.operation.created and result.operation.operation_id == SAVED_RESULT.operation_id
    assert events == ["begin", "authority", "reserve", "save", "complete", "commit"]
    assert idempotency.lookup_authority is not None
    assert idempotency.lookup_authority.family is OperationLookupAuthorityFamily.PROJECT_ACTION_USE
    assert idempotency.lookup_authority.action_id.value == "create-processing-profiles"
    fingerprint = idempotency.fingerprint

    events.clear()
    idempotency.result = SAVED_RESULT
    repository.facts = replace(FACTS, access_revision=13)
    async with transactions.begin():
        replay = await service.create_in_transaction(
            access=ACCESS, command=COMMAND, context=CONTEXT
        )

    assert replay == replace(result, operation=SAVED_RESULT)
    assert idempotency.fingerprint == fingerprint
    assert events == ["begin", "authority", "reserve", "original", "commit"]

    events.clear()
    changed = replace(COMMAND, definition=replace(COMMAND.definition, repeat_table_header=True))
    with pytest.raises(ConflictError, match="original"):
        async with transactions.begin():
            await service.create_in_transaction(access=ACCESS, command=changed, context=CONTEXT)
    assert idempotency.fingerprint != fingerprint
    assert events == ["begin", "authority", "reserve", "original", "rollback"]


@pytest.mark.asyncio
@pytest.mark.parametrize("application_actor", [False, True])
async def test_ineligible_actor_cannot_reserve_or_recover(application_actor: bool) -> None:
    events: list[str] = []
    repository = MockCreationRepository(events)
    idempotency = MockOperationIdempotency(events)
    transactions = MockTransactions(events)
    service = ProcessingProfileCreationService(
        repository,
        idempotency,
        RequestFingerprintService(RequestFingerprintKey(b"P" * 32)),
        transactions=transactions,
    )
    if application_actor:
        repository.access = replace(
            ACCESS,
            authentication_evidence=ApplicationKeyAuthenticationDTO(ApplicationKeyId(UUID(int=9))),
        )
        repository.facts = replace(
            FACTS,
            action=replace(
                FACTS.action,
                principal=replace(FACTS.action.principal, kind=PrincipalKind.APPLICATION),
                oauth_credential_facts=None,
            ),
        )
    else:
        repository.facts = replace(
            FACTS, action=replace(FACTS.action, has_exact_action_grant=False)
        )

    with pytest.raises(AccessDeniedError):
        async with transactions.begin():
            await service.create_in_transaction(
                access=repository.access, command=COMMAND, context=CONTEXT
            )

    assert events == ["begin", "authority", "rollback"]


@pytest.mark.asyncio
async def test_completion_failure_propagates_to_the_caller_transaction() -> None:
    events: list[str] = []
    idempotency = MockOperationIdempotency(events)
    idempotency.result = NEW_RESERVATION
    idempotency.completion_error = RuntimeError("Original completion is unavailable.")
    transactions = MockTransactions(events)
    service = ProcessingProfileCreationService(
        MockCreationRepository(events),
        idempotency,
        RequestFingerprintService(RequestFingerprintKey(b"P" * 32)),
        transactions=transactions,
    )

    with pytest.raises(RuntimeError, match="Original completion is unavailable"):
        async with transactions.begin():
            await service.create_in_transaction(access=ACCESS, command=COMMAND, context=CONTEXT)

    assert events == ["begin", "authority", "reserve", "save", "complete", "rollback"]
