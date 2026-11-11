"""Exercise independent Revoke authority, safe originals and current authorization ordering."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
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

from inframeld_backend.access.application.commands.revoke_application_key_command import (
    RevokeApplicationKeyCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.application_key_authentication_dto import (
    ApplicationKeyAuthenticationDTO,
)
from inframeld_backend.access.application.dtos.application_key_metadata_dto import (
    ApplicationKeyMetadataDTO,
)
from inframeld_backend.access.application.dtos.application_key_revocation_facts_dto import (
    ApplicationKeyRevocationFactsDTO,
)
from inframeld_backend.access.application.dtos.application_key_revocation_record_dto import (
    ApplicationKeyRevocationRecordDTO,
)
from inframeld_backend.access.application.dtos.human_credential_facts_dto import (
    HumanCredentialFactsDTO,
)
from inframeld_backend.access.application.dtos.project_action_facts_dto import ProjectActionFactsDTO
from inframeld_backend.access.application.protocols.application_key_revocation_facts_reader import (
    ApplicationKeyRevocationFactsReader,
)
from inframeld_backend.access.application.protocols.application_key_revocation_writer import (
    ApplicationKeyRevocationWriter,
)
from inframeld_backend.access.application.services.application_key_revocation_fingerprint_service import (
    ApplicationKeyRevocationFingerprintService,
)
from inframeld_backend.access.application.services.application_key_revocation_service import (
    ApplicationKeyRevocationService,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.application_key_adapter import ApplicationKeyAdapter
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.value_objects.application_key_id import ApplicationKeyId
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.enums.http_method import HttpMethod
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
ACCESS = AccessContextDTO(HUMAN.id, MockAuthenticationEvidence.browser())
NOW = datetime(2026, 11, 8, 15, 16, 17, 123456, tzinfo=UTC)
KEY = ApplicationKeyMetadataDTO(
    key_id=ApplicationKeyId(UUID(int=10)),
    application_principal_id=APPLICATION.id,
    project_id=PROJECT,
    allowed_adapters=(ApplicationKeyAdapter.HTTP, ApplicationKeyAdapter.MCP),
    created_at=NOW - timedelta(days=1),
    expires_at=NOW + timedelta(days=89),
    revoked_at=None,
)
COMMAND = RevokeApplicationKeyCommand(PROJECT, APPLICATION.id, KEY.key_id, 7)
CONTEXT = IdempotencyContextDTO(
    HttpMethod.POST,
    f"/v1/projects/{PROJECT.value}/application-accounts/{APPLICATION.id.value}/keys/{KEY.key_id.value}/revoke",
    IdempotencyKey("revoke-original"),
)
FACTS = ApplicationKeyRevocationFactsDTO(
    organization_id=ORG,
    project_id=PROJECT,
    installation_id=INSTALLATION,
    actor=ProjectActionFactsDTO(
        principal=HUMAN,
        has_pending_recovery=False,
        oauth_credential_facts=HumanCredentialFactsDTO(True, HumanCredentialVersion(1)),
        project_status=ProjectStatus.ACTIVE,
        is_project_member=True,
        has_exact_action_grant=True,
    ),
    application_principal=APPLICATION,
    metadata=KEY,
    access_revision=7,
    checked_at=NOW,
)
ORIGINAL = ApplicationKeyRevocationRecordDTO(
    operation_id=NEW_RESERVATION.operation_id,
    organization_id=ORG,
    installation_id=INSTALLATION,
    actor_principal_id=HUMAN.id,
    access_revision=8,
    metadata=replace(KEY, revoked_at=NOW),
)


class MockRevocationFacts(ApplicationKeyRevocationFactsReader):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.result: ApplicationKeyRevocationFactsDTO | None = FACTS
        self.original: ApplicationKeyRevocationRecordDTO | None = ORIGINAL

    @override
    async def lock_for_revoke(
        self, *, access: AccessContextDTO, command: RevokeApplicationKeyCommand
    ) -> ApplicationKeyRevocationFactsDTO | None:
        self.events.append("facts")
        return self.result

    @override
    async def read_original(
        self,
        *,
        organization_id: OrganizationId,
        project_id: ProjectId,
        actor_principal_id: PrincipalId,
        operation_id: OperationId,
    ) -> ApplicationKeyRevocationRecordDTO | None:
        self.events.append("original")
        assert (organization_id, project_id, actor_principal_id, operation_id) == (
            ORG,
            PROJECT,
            HUMAN.id,
            SAVED_RESULT.operation_id,
        )
        return self.original


class MockRevocationWriter(ApplicationKeyRevocationWriter):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.saved: list[ApplicationKeyRevocationRecordDTO] = []
        self.error: Exception | None = None

    @override
    async def save(
        self, *, original: ApplicationKeyRevocationRecordDTO, expected_project_revision: int
    ) -> None:
        self.events.append("write")
        assert expected_project_revision == 7
        if self.error is not None:
            raise self.error
        self.saved.append(original)


def scenario() -> tuple[
    ApplicationKeyRevocationService,
    MockRevocationFacts,
    MockRevocationWriter,
    MockOperationIdempotency,
    MockTransactions,
    list[str],
]:
    events: list[str] = []
    facts = MockRevocationFacts(events)
    writer = MockRevocationWriter(events)
    operations = MockOperationIdempotency(events)
    operations.result = NEW_RESERVATION
    transactions = MockTransactions(events)
    service = ApplicationKeyRevocationService(
        transaction_manager=transactions,
        revocation_facts_reader=facts,
        revocation_writer=writer,
        operation_idempotency=operations,
        revocation_fingerprint_service=ApplicationKeyRevocationFingerprintService(
            RequestFingerprintService(RequestFingerprintKey(b"f" * 32))
        ),
    )
    return service, facts, writer, operations, transactions, events


@pytest.mark.asyncio
async def test_revoke_only_human_can_revoke_last_key_without_issuance_delegation() -> None:
    service, _, writer, operations, _, events = scenario()
    result = await service.revoke(access=ACCESS, command=COMMAND, context=CONTEXT)

    assert result.original == ORIGINAL and result.operation.created
    assert writer.saved == [ORIGINAL]
    assert operations.authorization == FACTS
    assert operations.context == CONTEXT and operations.access == ACCESS
    assert operations.fingerprint is not None
    assert events == ["begin", "facts", "reserve", "write", "complete", "commit"]


@pytest.mark.asyncio
@pytest.mark.parametrize("expired", [False, True])
async def test_fresh_already_revoked_key_keeps_timestamp_and_revision(expired: bool) -> None:
    service, facts, writer, _, _, events = scenario()
    revoked = replace(
        KEY,
        revoked_at=NOW - timedelta(hours=2),
        expires_at=NOW - timedelta(hours=1) if expired else KEY.expires_at,
    )
    facts.result = replace(FACTS, metadata=revoked)
    result = await service.revoke(access=ACCESS, command=COMMAND, context=CONTEXT)

    assert result.original.metadata == revoked
    assert result.original.access_revision == 7 and result.operation.created
    assert writer.saved == [result.original]
    assert events == ["begin", "facts", "reserve", "write", "complete", "commit"]


@pytest.mark.asyncio
async def test_historical_replay_preserves_original_after_later_revision_and_metadata() -> None:
    service, facts, writer, operations, _, events = scenario()
    operations.result = SAVED_RESULT
    facts.result = replace(
        FACTS,
        access_revision=42,
        metadata=replace(KEY, revoked_at=NOW + timedelta(days=1)),
    )
    result = await service.revoke(access=ACCESS, command=COMMAND, context=CONTEXT)

    assert result.original == ORIGINAL and not result.operation.created
    assert not writer.saved
    assert events == ["begin", "facts", "reserve", "original", "commit"]


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
async def test_current_human_authority_precedes_original_disclosure(
    actor: ProjectActionFactsDTO, error: type[Exception]
) -> None:
    service, facts, writer, operations, _, events = scenario()
    facts.result = replace(FACTS, actor=actor)
    operations.result = SAVED_RESULT

    with pytest.raises(error):
        await service.revoke(access=ACCESS, command=COMMAND, context=CONTEXT)

    assert not writer.saved and operations.calls == 0
    assert events == ["begin", "facts", "rollback"]


@pytest.mark.asyncio
async def test_application_is_denied_before_history_without_human_fallback() -> None:
    service, facts, writer, operations, _, events = scenario()
    access = AccessContextDTO(APPLICATION.id, ApplicationKeyAuthenticationDTO(KEY.key_id))
    facts.result = replace(FACTS, actor=replace(FACTS.actor, principal=APPLICATION))

    with pytest.raises(AccessDeniedError):
        await service.revoke(access=access, command=COMMAND, context=CONTEXT)

    assert not writer.saved and operations.calls == 0
    assert events == ["begin", "facts", "rollback"]


@pytest.mark.asyncio
async def test_absent_target_key_is_hidden_without_reservation() -> None:
    service, facts, writer, operations, _, events = scenario()
    facts.result = replace(FACTS, metadata=None)

    with pytest.raises(ResourceNotFoundError):
        await service.revoke(access=ACCESS, command=COMMAND, context=CONTEXT)

    assert not writer.saved and operations.calls == 0
    assert events == ["begin", "facts", "rollback"]


@pytest.mark.asyncio
async def test_changed_target_binding_is_an_integrity_failure_before_effects() -> None:
    service, facts, writer, operations, _, events = scenario()
    facts.result = replace(FACTS, metadata=replace(KEY, key_id=ApplicationKeyId(UUID(int=11))))

    with pytest.raises(RuntimeError, match="scope"):
        await service.revoke(access=ACCESS, command=COMMAND, context=CONTEXT)

    assert not writer.saved and operations.calls == 0
    assert events == ["begin", "facts", "rollback"]


@pytest.mark.asyncio
async def test_fresh_stale_revision_cannot_revoke_the_key() -> None:
    service, facts, writer, _, _, events = scenario()
    facts.result = replace(FACTS, access_revision=8)

    with pytest.raises(StaleRevisionError):
        await service.revoke(access=ACCESS, command=COMMAND, context=CONTEXT)

    assert not writer.saved
    assert events == ["begin", "facts", "reserve", "rollback"]


@pytest.mark.asyncio
async def test_revision_exhaustion_cannot_partially_revoke() -> None:
    service, facts, writer, _, _, events = scenario()
    facts.result = replace(FACTS, access_revision=RevisionValidation.MAX_VALUE)

    with pytest.raises(ConflictError):
        await service.revoke(
            access=ACCESS,
            command=replace(COMMAND, expected_access_revision=RevisionValidation.MAX_VALUE),
            context=CONTEXT,
        )

    assert not writer.saved
    assert events == ["begin", "facts", "reserve", "rollback"]


@pytest.mark.asyncio
async def test_missing_original_is_unavailable_without_new_revocation() -> None:
    service, facts, writer, operations, _, events = scenario()
    operations.result = SAVED_RESULT
    facts.original = None

    with pytest.raises(DependencyUnavailableError):
        await service.revoke(access=ACCESS, command=COMMAND, context=CONTEXT)

    assert not writer.saved
    assert events == ["begin", "facts", "reserve", "original", "rollback"]


@pytest.mark.asyncio
async def test_original_cannot_be_retargeted_to_another_key() -> None:
    service, facts, writer, operations, _, _ = scenario()
    operations.result = SAVED_RESULT
    facts.original = replace(
        ORIGINAL, metadata=replace(KEY, revoked_at=NOW, key_id=ApplicationKeyId(UUID(int=11)))
    )

    with pytest.raises(ConflictError):
        await service.revoke(access=ACCESS, command=COMMAND, context=CONTEXT)

    assert not writer.saved


@pytest.mark.asyncio
async def test_failed_writer_never_records_completion_or_retries() -> None:
    service, _, writer, _, _, events = scenario()
    writer.error = RuntimeError("known write failure")

    with pytest.raises(RuntimeError, match="known write failure"):
        await service.revoke(access=ACCESS, command=COMMAND, context=CONTEXT)

    assert not writer.saved
    assert events == ["begin", "facts", "reserve", "write", "rollback"]


@pytest.mark.asyncio
async def test_unknown_commit_ack_propagates_without_automatic_reapplication() -> None:
    service, _, writer, _, transactions, events = scenario()
    error = RuntimeError("commit acknowledgment unknown")
    transactions.error = error

    with pytest.raises(RuntimeError) as raised:
        await service.revoke(access=ACCESS, command=COMMAND, context=CONTEXT)

    assert raised.value is error and len(writer.saved) == 1
    assert events.count("write") == events.count("complete") == 1


@pytest.mark.asyncio
async def test_method_and_exact_key_route_are_checked_before_local_io() -> None:
    service, _, writer, operations, _, events = scenario()

    with pytest.raises(RuntimeError, match="method or route"):
        await service.revoke(
            access=ACCESS, command=COMMAND, context=replace(CONTEXT, method=HttpMethod.DELETE)
        )

    assert not writer.saved and operations.calls == 0 and not events


@pytest.mark.parametrize("revision", [-1, True, 0.5, RevisionValidation.MAX_VALUE + 1])
def test_invalid_reviewed_revision_is_rejected_before_execution(revision: int) -> None:
    with pytest.raises((ValueError, TypeError)):
        replace(COMMAND, expected_access_revision=revision)
