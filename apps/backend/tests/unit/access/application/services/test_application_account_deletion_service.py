"""Prove current Delete authority and atomic original orchestration with unit doubles."""

import asyncio
from dataclasses import replace
from datetime import UTC, datetime
from typing import override
from uuid import UUID

import pytest
from tests.support.authentication_evidence import MockAuthenticationEvidence
from tests.support.mock_project_metadata import (
    NEW_RESERVATION,
    SAVED_RESULT,
    MockOperationIdempotency,
    MockTransactions,
)

from inframeld_backend.access.application.commands.delete_application_account_command import (
    DeleteApplicationAccountCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.application_account_deletion_facts_dto import (
    ApplicationAccountDeletionFactsDTO,
)
from inframeld_backend.access.application.dtos.application_account_deletion_record_dto import (
    ApplicationAccountDeletionRecordDTO,
)
from inframeld_backend.access.application.dtos.application_key_authentication_dto import (
    ApplicationKeyAuthenticationDTO,
)
from inframeld_backend.access.application.dtos.human_credential_facts_dto import (
    HumanCredentialFactsDTO,
)
from inframeld_backend.access.application.dtos.project_action_authorization_dto import (
    ProjectActionAuthorizationDTO,
)
from inframeld_backend.access.application.dtos.project_action_facts_dto import ProjectActionFactsDTO
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.protocols.application_account_deletion_facts_reader import (
    ApplicationAccountDeletionFactsReader,
)
from inframeld_backend.access.application.protocols.application_account_deletion_writer import (
    ApplicationAccountDeletionWriter,
)
from inframeld_backend.access.application.services.application_account_deletion_fingerprint_service import (
    ApplicationAccountDeletionFingerprintService,
)
from inframeld_backend.access.application.services.application_account_deletion_service import (
    ApplicationAccountDeletionService,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.value_objects.application_key_id import ApplicationKeyId
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ConflictError,
    DependencyUnavailableError,
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
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId

ORG = OrganizationId(UUID(int=2))
PROJECT = ProjectId(UUID(int=3))
INSTALLATION = InstallationId(UUID(int=4))
HUMAN = Principal(PrincipalId(UUID(int=1)), ORG, PrincipalKind.HUMAN, PrincipalStatus.ACTIVE)
APPLICATION = Principal(
    PrincipalId(UUID(int=8)), ORG, PrincipalKind.APPLICATION, PrincipalStatus.ACTIVE
)
BROWSER = MockAuthenticationEvidence.browser(
    VerifiedHumanIdentityDTO(IdentityAuthority("kratos:test"), IdentitySubject("alice")),
    installation_id=INSTALLATION,
    version=HumanCredentialVersion(1),
)
ACCESS = AccessContextDTO(HUMAN.id, BROWSER)
NOW = datetime(2026, 11, 10, 19, 0, tzinfo=UTC)
COMMAND = DeleteApplicationAccountCommand(PROJECT, APPLICATION.id, 7)
CONTEXT = IdempotencyContextDTO(
    HttpMethod.DELETE,
    f"/v1/projects/{PROJECT.value}/application-accounts/{APPLICATION.id.value}",
    IdempotencyKey("retire-original"),
)
FACTS = ApplicationAccountDeletionFactsDTO(
    organization_id=ORG,
    project_id=PROJECT,
    installation_id=INSTALLATION,
    actor=ProjectActionFactsDTO(
        principal=HUMAN,
        has_pending_recovery=False,
        oauth_credential_facts=HumanCredentialFactsDTO(True, BROWSER.version),
        project_status=ProjectStatus.ACTIVE,
        is_project_member=True,
        has_exact_action_grant=True,
    ),
    application_principal=APPLICATION,
    access_revision=7,
    checked_at=NOW,
)
ORIGINAL = ApplicationAccountDeletionRecordDTO(
    operation_id=NEW_RESERVATION.operation_id,
    installation_id=INSTALLATION,
    organization_id=ORG,
    project_id=PROJECT,
    actor_principal_id=HUMAN.id,
    application_principal_id=APPLICATION.id,
    access_revision=8,
)


class MockDeletionFacts(ApplicationAccountDeletionFactsReader):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.result: ApplicationAccountDeletionFactsDTO | None = FACTS
        self.original: ApplicationAccountDeletionRecordDTO | None = ORIGINAL
        self.stall = False

    @override
    async def lock_for_deletion(
        self, *, access: AccessContextDTO, command: DeleteApplicationAccountCommand
    ) -> ApplicationAccountDeletionFactsDTO | None:
        self.events.append("facts")
        if self.stall:
            await asyncio.Event().wait()
        return self.result

    @override
    async def read_original(
        self,
        *,
        organization_id: OrganizationId,
        project_id: ProjectId,
        actor_principal_id: PrincipalId,
        operation_id: OperationId,
    ) -> ApplicationAccountDeletionRecordDTO | None:
        self.events.append("original")
        assert (organization_id, project_id, actor_principal_id, operation_id) == (
            ORG,
            PROJECT,
            HUMAN.id,
            SAVED_RESULT.operation_id,
        )
        return self.original


class MockDeletionWriter(ApplicationAccountDeletionWriter):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.saved: list[ApplicationAccountDeletionRecordDTO] = []
        self.error: BaseException | None = None

    @override
    async def save(
        self,
        *,
        original: ApplicationAccountDeletionRecordDTO,
        expected_project_revision: int,
        checked_at: datetime,
    ) -> None:
        self.events.append("write")
        assert expected_project_revision == 7
        assert checked_at == NOW
        if self.error is not None:
            raise self.error
        self.saved.append(original)


def scenario() -> tuple[
    ApplicationAccountDeletionService,
    MockDeletionFacts,
    MockDeletionWriter,
    MockOperationIdempotency,
    MockTransactions,
    list[str],
]:
    events: list[str] = []
    facts = MockDeletionFacts(events)
    writer = MockDeletionWriter(events)
    operations = MockOperationIdempotency(events)
    operations.result = NEW_RESERVATION
    transactions = MockTransactions(events)
    service = ApplicationAccountDeletionService(
        transaction_manager=transactions,
        deletion_facts_reader=facts,
        deletion_writer=writer,
        operation_idempotency=operations,
        deletion_fingerprint_service=ApplicationAccountDeletionFingerprintService(
            RequestFingerprintService(RequestFingerprintKey(b"f" * 32))
        ),
    )
    return service, facts, writer, operations, transactions, events


@pytest.mark.asyncio
async def test_valid_retirement_completes_original_and_returns_after_commit() -> None:
    service, _, writer, operations, _, events = scenario()
    result = await service.delete(access=ACCESS, command=COMMAND, context=CONTEXT)
    assert result.original == ORIGINAL and result.operation.created
    assert writer.saved == [ORIGINAL]
    assert operations.authorization == ProjectActionAuthorizationDTO(ORG, PROJECT)
    assert operations.access == ACCESS and operations.context == CONTEXT
    assert operations.expected_kind is OperationReplayKind.SAFE_RESULT
    assert operations.lookup_authority is None and operations.fingerprint is not None
    assert events == ["begin", "facts", "reserve", "write", "complete", "commit"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "actor,error",
    [
        (replace(FACTS.actor, has_exact_action_grant=False), AccessDeniedError),
        (replace(FACTS.actor, has_pending_recovery=True), AccessDeniedError),
        (replace(FACTS.actor, is_project_member=False), ResourceNotFoundError),
        (replace(FACTS.actor, project_status=ProjectStatus.DELETING), ResourceNotFoundError),
        (
            replace(FACTS.actor, principal=replace(HUMAN, status=PrincipalStatus.SUSPENDED)),
            ResourceNotFoundError,
        ),
    ],
)
async def test_current_authority_denies_retired_target_replay_before_history(
    actor: ProjectActionFactsDTO, error: type[Exception]
) -> None:
    service, facts, writer, operations, _, events = scenario()
    facts.result = replace(
        FACTS,
        actor=actor,
        application_principal=replace(APPLICATION, status=PrincipalStatus.RETIRED),
    )
    operations.result = SAVED_RESULT
    with pytest.raises(error):
        await service.delete(access=ACCESS, command=COMMAND, context=CONTEXT)
    assert not writer.saved and operations.calls == 0
    assert events == ["begin", "facts", "rollback"]


@pytest.mark.asyncio
async def test_application_credential_cannot_retire_even_with_exact_grant() -> None:
    service, facts, writer, operations, _, events = scenario()
    facts.result = replace(
        FACTS, actor=replace(FACTS.actor, principal=APPLICATION, oauth_credential_facts=None)
    )
    access = AccessContextDTO(
        APPLICATION.id, ApplicationKeyAuthenticationDTO(ApplicationKeyId(UUID(int=10)))
    )
    with pytest.raises(AccessDeniedError):
        await service.delete(access=access, command=COMMAND, context=CONTEXT)
    assert operations.calls == 0 and not writer.saved
    assert events == ["begin", "facts", "rollback"]


@pytest.mark.asyncio
async def test_exact_original_precedes_fresh_revision_and_retired_lifecycle() -> None:
    service, facts, writer, operations, _, events = scenario()
    operations.result = SAVED_RESULT
    facts.result = replace(
        FACTS,
        access_revision=42,
        application_principal=replace(APPLICATION, status=PrincipalStatus.RETIRED),
    )
    result = await service.delete(access=ACCESS, command=COMMAND, context=CONTEXT)
    assert result.original == ORIGINAL and result.operation == SAVED_RESULT
    assert not writer.saved
    assert events == ["begin", "facts", "reserve", "original", "commit"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "original",
    [
        replace(ORIGINAL, operation_id=OperationId("different")),
        replace(ORIGINAL, installation_id=InstallationId(UUID(int=20))),
        replace(ORIGINAL, organization_id=OrganizationId(UUID(int=20))),
        replace(ORIGINAL, project_id=ProjectId(UUID(int=20))),
        replace(ORIGINAL, actor_principal_id=PrincipalId(UUID(int=20))),
        replace(ORIGINAL, application_principal_id=PrincipalId(UUID(int=20))),
        replace(ORIGINAL, access_revision=7),
        replace(ORIGINAL, access_revision=9),
    ],
)
async def test_incoherent_original_never_returns_a_receipt(
    original: ApplicationAccountDeletionRecordDTO,
) -> None:
    service, facts, writer, operations, _, events = scenario()
    facts.original = original
    operations.result = SAVED_RESULT
    with pytest.raises(ConflictError):
        await service.delete(access=ACCESS, command=COMMAND, context=CONTEXT)
    assert not writer.saved and events[-1] == "rollback"


@pytest.mark.asyncio
async def test_missing_original_is_unavailable_without_redispatch() -> None:
    service, facts, writer, operations, _, events = scenario()
    facts.original = None
    operations.result = SAVED_RESULT
    with pytest.raises(DependencyUnavailableError):
        await service.delete(access=ACCESS, command=COMMAND, context=CONTEXT)
    assert not writer.saved and operations.calls == 1 and events[-1] == "rollback"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "facts",
    [
        replace(FACTS, project_id=ProjectId(UUID(int=20))),
        replace(FACTS, organization_id=OrganizationId(UUID(int=20))),
        replace(
            FACTS,
            actor=replace(FACTS.actor, principal=replace(HUMAN, id=PrincipalId(UUID(int=20)))),
        ),
        replace(FACTS, application_principal=replace(APPLICATION, id=PrincipalId(UUID(int=20)))),
        replace(
            FACTS,
            application_principal=replace(
                APPLICATION, organization_id=OrganizationId(UUID(int=20))
            ),
        ),
        replace(FACTS, application_principal=replace(APPLICATION, kind=PrincipalKind.HUMAN)),
    ],
)
async def test_incoherent_current_scope_never_reserves(
    facts: ApplicationAccountDeletionFactsDTO,
) -> None:
    service, reader, writer, operations, _, events = scenario()
    reader.result = facts
    with pytest.raises(RuntimeError, match="facts changed the actor or target scope"):
        await service.delete(access=ACCESS, command=COMMAND, context=CONTEXT)
    assert not writer.saved and operations.calls == 0 and events[-1] == "rollback"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "revision,status,error",
    [
        (8, PrincipalStatus.ACTIVE, StaleRevisionError),
        (7, PrincipalStatus.RETIRED, ConflictError),
        (RevisionValidation.MAX_VALUE, PrincipalStatus.ACTIVE, ConflictError),
    ],
)
async def test_fresh_revision_and_lifecycle_guard_after_reservation(
    revision: int,
    status: PrincipalStatus,
    error: type[Exception],
) -> None:
    service, facts, writer, operations, _, events = scenario()
    facts.result = replace(
        FACTS, access_revision=revision, application_principal=replace(APPLICATION, status=status)
    )
    command = (
        replace(COMMAND, expected_access_revision=revision)
        if revision == RevisionValidation.MAX_VALUE
        else COMMAND
    )
    with pytest.raises(error):
        await service.delete(access=ACCESS, command=command, context=CONTEXT)
    assert not writer.saved and operations.calls == 1
    assert events == ["begin", "facts", "reserve", "rollback"]


@pytest.mark.asyncio
async def test_suspended_target_can_be_permanently_retired() -> None:
    service, facts, writer, _, _, events = scenario()
    facts.result = replace(
        FACTS, application_principal=replace(APPLICATION, status=PrincipalStatus.SUSPENDED)
    )
    result = await service.delete(access=ACCESS, command=COMMAND, context=CONTEXT)
    assert result.original == ORIGINAL and writer.saved == [ORIGINAL] and events[-1] == "commit"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "context",
    [
        replace(CONTEXT, method=HttpMethod.POST),
        replace(CONTEXT, requested_route=CONTEXT.requested_route + "/different"),
    ],
)
async def test_exact_method_and_route_precede_transaction(context: IdempotencyContextDTO) -> None:
    service, _, writer, operations, _, events = scenario()
    with pytest.raises(RuntimeError, match="changed its original method or route"):
        await service.delete(access=ACCESS, command=COMMAND, context=context)
    assert events == [] and operations.calls == 0 and not writer.saved


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["reserve", "write", "complete", "commit"])
async def test_failure_propagates_without_redispatch(stage: str) -> None:
    service, _, writer, operations, transactions, events = scenario()
    error = OSError("uncertain commit" if stage == "commit" else "dependency failed")
    if stage == "reserve":
        operations.error = error
    elif stage == "write":
        writer.error = error
    elif stage == "complete":
        operations.completion_error = error
    else:
        transactions.error = error
    with pytest.raises(OSError) as caught:
        await service.delete(access=ACCESS, command=COMMAND, context=CONTEXT)
    assert caught.value is error and operations.calls == 1 and events[-1] == "rollback"
    assert events.count("write") <= 1 and events.count("complete") <= 1


@pytest.mark.asyncio
async def test_cancellation_propagates_through_transaction() -> None:
    service, _, writer, operations, _, events = scenario()
    writer.error = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        await service.delete(access=ACCESS, command=COMMAND, context=CONTEXT)
    assert operations.calls == 1 and events == ["begin", "facts", "reserve", "write", "rollback"]


@pytest.mark.asyncio
async def test_existing_five_second_transaction_bound_covers_lock_wait() -> None:
    service, facts, writer, operations, _, events = scenario()
    facts.stall = True
    async with asyncio.timeout(7):
        with pytest.raises(DependencyUnavailableError):
            await service.delete(access=ACCESS, command=COMMAND, context=CONTEXT)
    assert not writer.saved and operations.calls == 0
    assert events == ["begin", "facts", "rollback"]


@pytest.mark.asyncio
async def test_missing_target_never_reserves() -> None:
    service, facts, writer, operations, _, events = scenario()
    facts.result = None
    with pytest.raises(ResourceNotFoundError):
        await service.delete(access=ACCESS, command=COMMAND, context=CONTEXT)
    assert not writer.saved and operations.calls == 0
    assert events == ["begin", "facts", "rollback"]


@pytest.mark.asyncio
@pytest.mark.parametrize("created", [False, True])
async def test_completion_shape_and_identity_are_checked(created: bool) -> None:
    service, _, writer, operations, _, events = scenario()
    if created:
        operations.completed_result = replace(
            SAVED_RESULT, created=True, operation_id=OperationId("wrong")
        )
        error: type[Exception] = RuntimeError
    else:
        operations.result = replace(SAVED_RESULT, created=True)
        error = ConflictError
    with pytest.raises(error, match="completion changed|coherent completed result"):
        await service.delete(access=ACCESS, command=COMMAND, context=CONTEXT)
    assert bool(writer.saved) is created and events[-1] == "rollback"
