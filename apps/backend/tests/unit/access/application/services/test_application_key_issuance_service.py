"""Keep current issuance authority ahead of safe original recovery and fresh secrets."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import override
from unittest.mock import patch
from uuid import UUID

import pytest
from tests.support.authentication_evidence import MockAuthenticationEvidence
from tests.support.mock_project_metadata import MockTransactions

from inframeld_backend.access.application.commands.issue_application_key_command import (
    IssueApplicationKeyCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.application_key_authentication_dto import (
    ApplicationKeyAuthenticationDTO,
)
from inframeld_backend.access.application.dtos.application_key_creation_dto import (
    ApplicationKeyCreationDTO,
)
from inframeld_backend.access.application.dtos.application_key_issuance_facts_dto import (
    ApplicationKeyIssuanceFactsDTO,
)
from inframeld_backend.access.application.dtos.application_key_issuance_record_dto import (
    ApplicationKeyIssuanceRecordDTO,
)
from inframeld_backend.access.application.dtos.application_key_metadata_dto import (
    ApplicationKeyMetadataDTO,
)
from inframeld_backend.access.application.dtos.application_key_verification_profile_dto import (
    ApplicationKeyVerificationProfileDTO,
)
from inframeld_backend.access.application.dtos.project_action_facts_dto import ProjectActionFactsDTO
from inframeld_backend.access.application.protocols.application_key_issuance_facts_reader import (
    ApplicationKeyIssuanceFactsReader,
)
from inframeld_backend.access.application.protocols.application_key_issuance_writer import (
    ApplicationKeyIssuanceWriter,
)
from inframeld_backend.access.application.protocols.authorized_operation_scope import (
    AuthorizedOperationScope,
)
from inframeld_backend.access.application.services.application_key_issuance_fingerprint_service import (
    ApplicationKeyIssuanceFingerprintService,
)
from inframeld_backend.access.application.services.application_key_issuance_service import (
    ApplicationKeyIssuanceService,
)
from inframeld_backend.access.application.value_objects.application_key_credential import (
    ApplicationKeyCredential,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.application_key_adapter import ApplicationKeyAdapter
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.value_objects.application_key_audience import (
    ApplicationKeyAudience,
)
from inframeld_backend.access.domain.value_objects.application_key_id import ApplicationKeyId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
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
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ConflictError,
    DependencyUnavailableError,
    InvalidInputError,
    ResourceNotFoundError,
    StaleRevisionError,
)
from inframeld_backend.shared.application.protocols.operation_idempotency import (
    OperationIdempotency,
)
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
NOW = datetime(2026, 11, 8, 11, 12, 13, 123456, tzinfo=UTC)
HTTP = ApplicationKeyVerificationProfileDTO(
    ApplicationKeyAudience("https://api.example.test"), ApplicationKeyAdapter.HTTP
)
MCP = ApplicationKeyVerificationProfileDTO(
    ApplicationKeyAudience("https://api.example.test/mcp/"), ApplicationKeyAdapter.MCP
)
COMMAND = IssueApplicationKeyCommand(PROJECT, APPLICATION.id, (ApplicationKeyAdapter.HTTP,), 7)
CONTEXT = IdempotencyContextDTO(
    HttpMethod.POST,
    f"/v1/projects/{PROJECT.value}/application-accounts/{APPLICATION.id.value}/keys",
    IdempotencyKey("issue-original"),
)
OPERATION = CompletedSynchronousOperationDTO(
    OperationId("key-original"), False, OperationReplayKind.ISSUED_SECRET, NOW + timedelta(days=7)
)
RESERVATION = NewOperationReservationDTO(OPERATION.operation_id)
FACTS = ApplicationKeyIssuanceFactsDTO(
    organization_id=ORG,
    project_id=PROJECT,
    installation_id=INSTALLATION,
    actor=ProjectActionFactsDTO(
        principal=HUMAN,
        has_pending_recovery=False,
        oauth_credential_facts=None,
        project_status=ProjectStatus.ACTIVE,
        is_project_member=True,
        has_exact_action_grant=True,
    ),
    application_principal=APPLICATION,
    is_application_project_member=True,
    has_all_action_delegation=True,
    manages_all_groups=True,
    access_revision=7,
    checked_at=NOW,
    usable_key_count=0,
)
ORIGINAL = ApplicationKeyIssuanceRecordDTO(
    operation_id=OPERATION.operation_id,
    organization_id=ORG,
    installation_id=INSTALLATION,
    issuer_principal_id=HUMAN.id,
    access_revision=8,
    metadata=ApplicationKeyMetadataDTO(
        key_id=ApplicationKeyId(UUID(int=10)),
        application_principal_id=APPLICATION.id,
        project_id=PROJECT,
        allowed_adapters=COMMAND.allowed_adapters,
        created_at=NOW,
        expires_at=NOW + timedelta(days=90),
        revoked_at=None,
    ),
)


class MockKeyFacts(ApplicationKeyIssuanceFactsReader):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.result: ApplicationKeyIssuanceFactsDTO | None = FACTS
        self.original: ApplicationKeyIssuanceRecordDTO | None = ORIGINAL

    @override
    async def lock_for_issue(
        self,
        *,
        access: AccessContextDTO,
        project_id: ProjectId,
        application_principal_id: PrincipalId,
    ) -> ApplicationKeyIssuanceFactsDTO | None:
        self.events.append("facts")
        return self.result

    @override
    async def read_original(
        self,
        *,
        organization_id: OrganizationId,
        project_id: ProjectId,
        application_principal_id: PrincipalId,
        issuer_principal_id: PrincipalId,
        operation_id: OperationId,
    ) -> ApplicationKeyIssuanceRecordDTO | None:
        self.events.append("original")
        assert (
            organization_id,
            project_id,
            application_principal_id,
            issuer_principal_id,
            operation_id,
        ) == (ORG, PROJECT, APPLICATION.id, HUMAN.id, OPERATION.operation_id)
        return self.original


class MockKeyWriter(ApplicationKeyIssuanceWriter):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.saved: list[ApplicationKeyCreationDTO] = []
        self.error: Exception | None = None

    @override
    async def create(
        self, *, key: ApplicationKeyCreationDTO, expected_project_revision: int
    ) -> None:
        self.events.append("write")
        assert expected_project_revision == 7
        self.saved.append(key)
        if self.error is not None:
            raise self.error


class MockKeyOperations(OperationIdempotency):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.result: NewOperationReservationDTO | CompletedSynchronousOperationDTO = RESERVATION
        self.completed = replace(OPERATION, created=True)
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
    ) -> (
        NewOperationReservationDTO
        | CompletedSynchronousOperationDTO
        | AcceptedAsyncOperationDTO
        | RecoveryRequiredOperationDTO
    ):
        self.events.append("reserve")
        assert context == CONTEXT and access == ACCESS
        assert expected_replay_kind is OperationReplayKind.ISSUED_SECRET
        assert lookup_authority is None
        self.fingerprint = fingerprint
        return self.result

    @override
    async def record_completed_result(
        self, operation: NewOperationReservationDTO, *, replay_kind: OperationReplayKind
    ) -> CompletedSynchronousOperationDTO:
        self.events.append("complete")
        assert operation == RESERVATION and replay_kind is OperationReplayKind.ISSUED_SECRET
        return self.completed


def scenario(
    *,
    http: ApplicationKeyVerificationProfileDTO | None = HTTP,
    mcp: ApplicationKeyVerificationProfileDTO | None = MCP,
    default: int = 90 * 86400,
    maximum: int = 365 * 86400,
) -> tuple[
    ApplicationKeyIssuanceService, MockKeyFacts, MockKeyWriter, MockKeyOperations, list[str]
]:
    events: list[str] = []
    facts = MockKeyFacts(events)
    writer = MockKeyWriter(events)
    operations = MockKeyOperations(events)
    service = ApplicationKeyIssuanceService(
        transaction_manager=MockTransactions(events),
        issuance_facts_reader=facts,
        issuance_writer=writer,
        operation_idempotency=operations,
        issuance_fingerprint_service=ApplicationKeyIssuanceFingerprintService(
            RequestFingerprintService(RequestFingerprintKey(b"f" * 32))
        ),
        http_profile=http,
        mcp_profile=mcp,
        default_lifetime_seconds=default,
        maximum_lifetime_seconds=maximum,
    )
    return service, facts, writer, operations, events


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "adapters",
    [
        (ApplicationKeyAdapter.HTTP,),
        (ApplicationKeyAdapter.MCP,),
        (ApplicationKeyAdapter.HTTP, ApplicationKeyAdapter.MCP),
        (ApplicationKeyAdapter.MCP, ApplicationKeyAdapter.HTTP),
    ],
)
async def test_fresh_issuance_persists_one_verifier_and_exact_selected_bindings(
    adapters: tuple[ApplicationKeyAdapter, ...],
) -> None:
    service, _, writer, _, events = scenario()
    result = await service.issue(
        access=ACCESS,
        command=replace(COMMAND, allowed_adapters=adapters, expires_in_seconds=3600),
        context=CONTEXT,
    )

    assert result.credential is not None and result.operation.created
    assert result.original.metadata.key_id == result.credential.key_id
    assert result.original.metadata.allowed_adapters == adapters
    assert result.original.metadata.expires_at == NOW + timedelta(seconds=3600)
    assert result.original.access_revision == 8
    assert len(writer.saved) == 1
    saved = writer.saved[0]
    assert saved.original == result.original and saved.verifier == result.credential.digest()
    assert saved.http_audience == (
        HTTP.audience if ApplicationKeyAdapter.HTTP in adapters else None
    )
    assert saved.mcp_audience == (MCP.audience if ApplicationKeyAdapter.MCP in adapters else None)
    assert result.credential.value not in repr(saved) + repr(result)
    assert repr(saved.verifier) not in repr(saved)
    assert events == ["begin", "facts", "reserve", "write", "complete", "commit"]


@pytest.mark.asyncio
async def test_unselected_profile_may_be_absent_and_default_applies_only_to_fresh_issue() -> None:
    service, _, writer, _, _ = scenario(mcp=None)
    result = await service.issue(access=ACCESS, command=COMMAND, context=CONTEXT)

    assert result.original.metadata.expires_at == NOW + timedelta(days=90)
    assert writer.saved[0].mcp_audience is None


@pytest.mark.asyncio
async def test_equal_profiles_remain_two_bindings_of_one_parent_key() -> None:
    service, _, writer, _, _ = scenario(mcp=replace(MCP, audience=HTTP.audience))
    result = await service.issue(
        access=ACCESS,
        command=replace(
            COMMAND, allowed_adapters=(ApplicationKeyAdapter.HTTP, ApplicationKeyAdapter.MCP)
        ),
        context=CONTEXT,
    )

    assert result.credential is not None and len(writer.saved) == 1
    assert writer.saved[0].http_audience == writer.saved[0].mcp_audience == HTTP.audience


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "adapters,http,mcp",
    [
        ((ApplicationKeyAdapter.HTTP,), None, MCP),
        ((ApplicationKeyAdapter.MCP,), HTTP, None),
        ((ApplicationKeyAdapter.HTTP, ApplicationKeyAdapter.MCP), HTTP, None),
    ],
)
async def test_missing_selected_profile_has_no_secret_or_persisted_key(
    adapters: tuple[ApplicationKeyAdapter, ...],
    http: ApplicationKeyVerificationProfileDTO | None,
    mcp: ApplicationKeyVerificationProfileDTO | None,
) -> None:
    service, _, writer, _, events = scenario(http=http, mcp=mcp)
    with (
        patch.object(
            ApplicationKeyCredential, "generate", side_effect=AssertionError("secret allocated")
        ),
        pytest.raises(DependencyUnavailableError),
    ):
        await service.issue(
            access=ACCESS, command=replace(COMMAND, allowed_adapters=adapters), context=CONTEXT
        )

    assert not writer.saved and "complete" not in events


@pytest.mark.asyncio
async def test_original_replay_precedes_fresh_profiles_lifetime_slot_and_review_checks() -> None:
    service, facts, writer, operations, events = scenario(http=None, mcp=None, default=1, maximum=1)
    facts.result = replace(
        FACTS, access_revision=999, usable_key_count=2, checked_at=NOW + timedelta(days=100)
    )
    operations.result = OPERATION
    with patch.object(
        ApplicationKeyCredential, "generate", side_effect=AssertionError("secret allocated")
    ):
        result = await service.issue(access=ACCESS, command=COMMAND, context=CONTEXT)

    assert (
        result.original == ORIGINAL and result.operation == OPERATION and result.credential is None
    )
    assert not writer.saved
    assert events == ["begin", "facts", "reserve", "original", "commit"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changed",
    [
        replace(FACTS, has_all_action_delegation=False),
        replace(FACTS, manages_all_groups=False),
        replace(FACTS, is_application_project_member=False),
        replace(FACTS, actor=replace(FACTS.actor, has_exact_action_grant=False)),
        replace(FACTS, actor=replace(FACTS.actor, has_pending_recovery=True)),
        replace(
            FACTS, application_principal=replace(APPLICATION, status=PrincipalStatus.SUSPENDED)
        ),
        replace(FACTS, application_principal=replace(APPLICATION, status=PrincipalStatus.RETIRED)),
    ],
)
async def test_incomplete_current_authority_denies_before_original_history(
    changed: ApplicationKeyIssuanceFactsDTO,
) -> None:
    service, facts, writer, operations, events = scenario()
    facts.result = changed
    operations.result = OPERATION
    with pytest.raises(AccessDeniedError):
        await service.issue(access=ACCESS, command=COMMAND, context=CONTEXT)

    assert not writer.saved and "reserve" not in events and "original" not in events


@pytest.mark.asyncio
async def test_missing_or_hidden_target_has_no_history_or_issuance() -> None:
    service, facts, writer, _, events = scenario()
    facts.result = None
    with pytest.raises(ResourceNotFoundError):
        await service.issue(access=ACCESS, command=COMMAND, context=CONTEXT)
    assert not writer.saved and "reserve" not in events


@pytest.mark.asyncio
async def test_valid_application_cannot_issue_keys_or_read_human_originals() -> None:
    service, facts, writer, _, events = scenario()
    facts.result = replace(FACTS, actor=replace(FACTS.actor, principal=APPLICATION))
    access = AccessContextDTO(
        APPLICATION.id, ApplicationKeyAuthenticationDTO(ApplicationKeyId(UUID(int=20)))
    )
    with pytest.raises(AccessDeniedError):
        await service.issue(access=access, command=COMMAND, context=CONTEXT)
    assert not writer.saved and "reserve" not in events


@pytest.mark.asyncio
async def test_changed_principal_kind_is_an_internal_contract_failure() -> None:
    service, _, writer, _, events = scenario()
    access = AccessContextDTO(
        HUMAN.id, ApplicationKeyAuthenticationDTO(ApplicationKeyId(UUID(int=20)))
    )
    with pytest.raises(RuntimeError, match="kind"):
        await service.issue(access=access, command=COMMAND, context=CONTEXT)
    assert not writer.saved and "reserve" not in events


@pytest.mark.asyncio
async def test_stale_fresh_review_has_no_secret_or_key() -> None:
    service, _, writer, _, events = scenario()
    with pytest.raises(StaleRevisionError):
        await service.issue(
            access=ACCESS, command=replace(COMMAND, expected_access_revision=6), context=CONTEXT
        )
    assert not writer.saved and "complete" not in events


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [2, 3])
async def test_two_parent_keys_cannot_be_evicted_to_make_a_slot(count: int) -> None:
    service, facts, writer, _, events = scenario()
    facts.result = replace(FACTS, usable_key_count=count)
    with pytest.raises(ConflictError):
        await service.issue(access=ACCESS, command=COMMAND, context=CONTEXT)
    assert not writer.saved and "complete" not in events


@pytest.mark.asyncio
async def test_exhausted_revision_cannot_create_a_key() -> None:
    service, facts, writer, _, _ = scenario()
    facts.result = replace(FACTS, access_revision=RevisionValidation.MAX_VALUE)
    with pytest.raises(ConflictError):
        await service.issue(
            access=ACCESS,
            command=replace(COMMAND, expected_access_revision=RevisionValidation.MAX_VALUE),
            context=CONTEXT,
        )
    assert not writer.saved


@pytest.mark.asyncio
@pytest.mark.parametrize("seconds", [3601, 2**53 - 1])
async def test_invalid_fresh_lifetime_precedes_secret_generation(seconds: int) -> None:
    service, _, writer, _, events = scenario(default=1, maximum=3600)
    with (
        patch.object(
            ApplicationKeyCredential, "generate", side_effect=AssertionError("secret allocated")
        ),
        pytest.raises(InvalidInputError),
    ):
        await service.issue(
            access=ACCESS, command=replace(COMMAND, expires_in_seconds=seconds), context=CONTEXT
        )
    assert not writer.saved and "complete" not in events


@pytest.mark.asyncio
async def test_timestamp_overflow_precedes_secret_generation() -> None:
    service, facts, writer, _, _ = scenario(default=2, maximum=2)
    facts.result = replace(
        FACTS, checked_at=datetime.max.replace(tzinfo=UTC) - timedelta(seconds=1)
    )
    with (
        patch.object(
            ApplicationKeyCredential, "generate", side_effect=AssertionError("secret allocated")
        ),
        pytest.raises(InvalidInputError),
    ):
        await service.issue(access=ACCESS, command=COMMAND, context=CONTEXT)
    assert not writer.saved


@pytest.mark.asyncio
async def test_writer_failure_propagates_without_completion_or_automatic_retry() -> None:
    service, _, writer, _, events = scenario()
    writer.error = RuntimeError("controlled pre-commit failure")
    with pytest.raises(RuntimeError, match="controlled"):
        await service.issue(access=ACCESS, command=COMMAND, context=CONTEXT)
    assert len(writer.saved) == 1 and events.count("reserve") == 1
    assert events[-1] == "rollback" and "complete" not in events


@pytest.mark.asyncio
async def test_missing_original_does_not_mint_replacement() -> None:
    service, facts, writer, operations, _ = scenario()
    operations.result = OPERATION
    facts.original = None
    with pytest.raises(DependencyUnavailableError):
        await service.issue(access=ACCESS, command=COMMAND, context=CONTEXT)
    assert not writer.saved


@pytest.mark.asyncio
async def test_incoherent_original_actor_is_not_disclosed_or_replaced() -> None:
    service, facts, writer, operations, _ = scenario()
    operations.result = OPERATION
    facts.original = replace(ORIGINAL, issuer_principal_id=PrincipalId(UUID(int=99)))
    with pytest.raises(ConflictError):
        await service.issue(access=ACCESS, command=COMMAND, context=CONTEXT)
    assert not writer.saved


def test_fingerprint_preserves_omitted_lifetime_adapter_order_and_original_scope() -> None:
    service = ApplicationKeyIssuanceFingerprintService(
        RequestFingerprintService(RequestFingerprintKey(b"f" * 32))
    )
    dual = replace(
        COMMAND, allowed_adapters=(ApplicationKeyAdapter.HTTP, ApplicationKeyAdapter.MCP)
    )
    original = service.for_issue(dual)
    assert service.for_issue(dual) == original
    for changed in [
        replace(dual, allowed_adapters=tuple(reversed(dual.allowed_adapters))),
        replace(dual, expires_in_seconds=90 * 86400),
        replace(dual, expected_access_revision=8),
        replace(dual, application_principal_id=PrincipalId(UUID(int=99))),
    ]:
        assert service.for_issue(changed) != original
