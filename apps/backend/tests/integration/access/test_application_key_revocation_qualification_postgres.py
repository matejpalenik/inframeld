"""Qualify current authorization, retained outcomes and revocation ordering on real rows."""

import asyncio
import os
from collections.abc import Awaitable
from dataclasses import replace
from datetime import datetime, timedelta
from json import dumps
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import DateTime, Integer, String, column, delete, event, func, select, table, update
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from tests.support.application_key_scenarios import issue_application_key, revocation_service
from tests.support.first_administrator_bootstrap_scenarios import MockBootstrapIdentityVerifier
from tests.support.project_grant_changes import create_project_grant_change_service

from inframeld_backend.access.application.commands.add_project_member_command import (
    AddProjectMemberCommand,
)
from inframeld_backend.access.application.commands.admit_human_command import AdmitHumanCommand
from inframeld_backend.access.application.commands.issue_application_key_command import (
    IssueApplicationKeyCommand,
)
from inframeld_backend.access.application.commands.remove_application_account_action_grant_command import (
    RemoveApplicationAccountActionGrantCommand,
)
from inframeld_backend.access.application.commands.revoke_application_key_command import (
    RevokeApplicationKeyCommand,
)
from inframeld_backend.access.application.commands.set_application_account_action_grant_command import (
    SetApplicationAccountActionGrantCommand,
)
from inframeld_backend.access.application.commands.set_project_action_grant_command import (
    SetProjectActionGrantCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.admitted_work_authority_dto import (
    AdmittedWorkAuthorityDTO,
)
from inframeld_backend.access.application.dtos.application_key_issue_result_dto import (
    ApplicationKeyIssueResultDTO,
)
from inframeld_backend.access.application.dtos.application_key_revocation_result_dto import (
    ApplicationKeyRevocationResultDTO,
)
from inframeld_backend.access.application.dtos.application_key_verification_profile_dto import (
    ApplicationKeyVerificationProfileDTO,
)
from inframeld_backend.access.application.dtos.browser_session_authentication_dto import (
    BrowserSessionAuthenticationDTO,
)
from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
    HumanOAuthCredentialBindingDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_event_dto import (
    IdentityRecoveryEventDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.enums.identity_recovery_event_kind import (
    IdentityRecoveryEventKind,
)
from inframeld_backend.access.application.errors.application_key_credential_rejected_error import (
    ApplicationKeyCredentialRejectedError,
)
from inframeld_backend.access.application.errors.human_oauth_credential_rejected_error import (
    HumanOAuthCredentialRejectedError,
)
from inframeld_backend.access.application.services.action_authorization_service import (
    ActionAuthorizationService,
)
from inframeld_backend.access.application.services.admitted_work_authorization_service import (
    AdmittedWorkAuthorizationService,
)
from inframeld_backend.access.application.services.application_authentication_service import (
    ApplicationAuthenticationService,
)
from inframeld_backend.access.application.services.application_key_issuance_fingerprint_service import (
    ApplicationKeyIssuanceFingerprintService,
)
from inframeld_backend.access.application.services.application_session_service import (
    ApplicationSessionService,
)
from inframeld_backend.access.application.services.human_admission_fingerprint_service import (
    HumanAdmissionFingerprintService,
)
from inframeld_backend.access.application.services.identity_recovery_admission_service import (
    IdentityRecoveryAdmissionService,
)
from inframeld_backend.access.application.services.project_membership_change_fingerprint_service import (
    ProjectMembershipChangeFingerprintService,
)
from inframeld_backend.access.domain.enums.application_account_action import (
    ApplicationAccountAction,
)
from inframeld_backend.access.domain.enums.application_key_adapter import ApplicationKeyAdapter
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.enums.project_action import ProjectAction
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.application_key_audience import (
    ApplicationKeyAudience,
)
from inframeld_backend.access.domain.value_objects.identity_recovery_flow_id import (
    IdentityRecoveryFlowId,
)
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.infrastructure.readers.postgres_admitted_work_facts_reader import (
    PostgresAdmittedWorkFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_application_authentication_facts_reader import (
    PostgresApplicationAuthenticationFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_application_key_revocation_facts_reader import (
    PostgresApplicationKeyRevocationFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_human_credential_state_reader import (
    PostgresHumanCredentialStateReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_project_action_facts_reader import (
    PostgresProjectActionFactsReader,
)
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.access.infrastructure.rows.application_action_grant_row import (
    ApplicationActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.application_key_revocation_result_row import (
    ApplicationKeyRevocationResultRow,
)
from inframeld_backend.access.infrastructure.rows.application_key_row import ApplicationKeyRow
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_membership_row import ProjectMembershipRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.access.infrastructure.settings.application_key_issuance_settings import (
    ApplicationKeyIssuanceSettings,
)
from inframeld_backend.access.infrastructure.verifiers.postgres_application_key_verifier import (
    PostgresApplicationKeyVerifier,
)
from inframeld_backend.access.infrastructure.writers.postgres_human_credential_state_initializer import (
    PostgresHumanCredentialStateInitializer,
)
from inframeld_backend.access.infrastructure.writers.postgres_identity_recovery_admission_writer import (
    PostgresIdentityRecoveryAdmissionWriter,
)
from inframeld_backend.access.infrastructure.writers.postgres_job_admission_audit_writer import (
    PostgresJobAdmissionAuditWriter,
)
from inframeld_backend.bootstrap.application_account_grant_composition import (
    open_application_account_grant_change,
)
from inframeld_backend.bootstrap.application_key_composition import open_application_key_issuance
from inframeld_backend.bootstrap.human_admission_composition import open_human_admission
from inframeld_backend.bootstrap.postgres_project_membership_change_service_factory import (
    PostgresProjectMembershipChangeServiceFactory,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.dtos.job_admission_dto import JobAdmissionDTO
from inframeld_backend.shared.application.dtos.product_job_binding_dto import ProductJobBindingDTO
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    AuthenticationRequiredError,
    ConflictError,
    StaleRevisionError,
)
from inframeld_backend.shared.application.services.idempotency_service import IdempotencyService
from inframeld_backend.shared.application.services.job_admission_service import JobAdmissionService
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.job_payload import JobPayload
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)
from inframeld_backend.shared.application.value_objects.request_fingerprint_key import (
    RequestFingerprintKey,
)
from inframeld_backend.shared.application.value_objects.request_id import RequestId
from inframeld_backend.shared.domain.enums.job_status import JobStatus
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation
from inframeld_backend.shared.infrastructure.repositories.postgres_job_store import PostgresJobStore
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.rows.durable_job_row import DurableJobRow
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)
from inframeld_backend.shared.infrastructure.writers.postgres_operation_reservation_writer import (
    PostgresOperationReservationWriter,
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
        reason="Requires isolated PostgreSQL integration services",
    ),
]
HTTP = ApplicationKeyVerificationProfileDTO(
    ApplicationKeyAudience("https://api.test"), ApplicationKeyAdapter.HTTP
)
MCP = ApplicationKeyVerificationProfileDTO(
    ApplicationKeyAudience("https://mcp.test/mcp"), ApplicationKeyAdapter.MCP
)


@pytest_asyncio.fixture
async def issued_key(database: Database) -> tuple[AccessContextDTO, ApplicationKeyIssueResultDTO]:
    return await issue_application_key(database)


def _request(
    issued: ApplicationKeyIssueResultDTO, key: str = "revoke-original"
) -> tuple[RevokeApplicationKeyCommand, IdempotencyContextDTO]:
    metadata = issued.original.metadata
    return (
        RevokeApplicationKeyCommand(
            metadata.project_id,
            metadata.application_principal_id,
            metadata.key_id,
            issued.original.access_revision,
        ),
        IdempotencyContextDTO(
            HttpMethod.POST,
            f"/v1/projects/{metadata.project_id.value}/application-accounts/{metadata.application_principal_id.value}/keys/{metadata.key_id.value}/revoke",
            IdempotencyKey(key),
        ),
    )


async def _revoke(
    database: Database,
    access: AccessContextDTO,
    command: RevokeApplicationKeyCommand,
    context: IdempotencyContextDTO,
) -> ApplicationKeyRevocationResultDTO:
    async with database.session() as session:
        return await revocation_service(session).revoke(
            access=access, command=command, context=context
        )


async def _effects(
    database: Database, issued: ApplicationKeyIssueResultDTO, context: IdempotencyContextDTO
) -> tuple[int, datetime | None, int, int, int]:
    """Observe business and shared effects without interpreting authorization or retry state."""
    metadata = issued.original.metadata
    async with database.session() as session:
        revision = await session.scalar(
            select(ProjectRow.access_revision).where(ProjectRow.id == metadata.project_id.value)
        )
        key = await session.get(ApplicationKeyRow, metadata.key_id.value)
        assert revision is not None and key is not None
        audits = await session.scalar(
            select(func.count())
            .select_from(AccessAuditEventRow)
            .where(
                AccessAuditEventRow.event_type == "application_key_revoked",
                AccessAuditEventRow.target_id == metadata.key_id.value,
            )
        )
        originals = await session.scalar(
            select(func.count())
            .select_from(ApplicationKeyRevocationResultRow)
            .where(ApplicationKeyRevocationResultRow.key_id == metadata.key_id.value)
        )
        operations = await session.scalar(
            select(func.count())
            .select_from(IdempotencyReservationRow)
            .where(IdempotencyReservationRow.requested_route == context.requested_route)
        )
        assert audits is not None and originals is not None and operations is not None
        return revision, key.revoked_at, audits, originals, operations


async def _replacement(
    database: Database,
    creator: AccessContextDTO,
    issued: ApplicationKeyIssueResultDTO,
    revision: int,
) -> ApplicationKeyIssueResultDTO:
    metadata = issued.original.metadata
    async with open_application_key_issuance(
        database,
        ApplicationKeyIssuanceFingerprintService(
            RequestFingerprintService(RequestFingerprintKey(b"r" * 32))
        ),
        http_profile=HTTP,
        mcp_profile=MCP,
        settings=ApplicationKeyIssuanceSettings(),
    ) as issuer:
        return await issuer.issue(
            access=creator,
            command=IssueApplicationKeyCommand(
                metadata.project_id,
                metadata.application_principal_id,
                metadata.allowed_adapters,
                revision,
            ),
            context=IdempotencyContextDTO(
                HttpMethod.POST,
                f"/v1/projects/{metadata.project_id.value}/application-accounts/{metadata.application_principal_id.value}/keys",
                IdempotencyKey("issue-replacement"),
            ),
        )


@pytest.mark.parametrize("exhausted", [False, True], ids=["ordinary-revision", "maximum-revision"])
async def test_fresh_already_revoked_noop_records_only_a_new_original(
    database: Database,
    issued_key: tuple[AccessContextDTO, ApplicationKeyIssueResultDTO],
    exhausted: bool,
) -> None:
    creator, issued = issued_key
    command, context = _request(issued)
    first = await _revoke(database, creator, command, context)
    revision = first.original.access_revision
    if exhausted:
        revision = RevisionValidation.MAX_VALUE
        async with database.session() as session, session.begin():
            await session.execute(
                update(ProjectRow)
                .where(ProjectRow.id == command.project_id.value)
                .values(access_revision=revision)
            )
    before = await _effects(database, issued, context)
    noop = await _revoke(
        database,
        creator,
        replace(command, expected_access_revision=revision),
        replace(context, key=IdempotencyKey("fresh-noop")),
    )
    assert noop.operation.created and noop.operation.operation_id != first.operation.operation_id
    assert noop.original.metadata == first.original.metadata
    assert noop.original.access_revision == revision
    assert await _effects(database, issued, context) == (
        before[0],
        before[1],
        before[2],
        before[3] + 1,
        before[4] + 1,
    )


async def test_lost_response_replay_keeps_original_receipt_after_replacement_and_expiry(
    database: Database, issued_key: tuple[AccessContextDTO, ApplicationKeyIssueResultDTO]
) -> None:
    creator, issued = issued_key
    command, context = _request(issued)
    first = await _revoke(database, creator, command, context)
    replacement = await _replacement(database, creator, issued, first.original.access_revision)
    assert replacement.credential is not None
    async with database.session() as session, session.begin():
        await session.execute(
            update(ApplicationKeyRow)
            .where(ApplicationKeyRow.key_id == command.key_id.value)
            .values(expires_at=func.clock_timestamp(type_=DateTime(timezone=True)))
        )
    before = await _effects(database, issued, context)
    replay = await _revoke(database, creator, command, context)
    assert not replay.operation.created
    assert replay.original == first.original
    assert replay.operation.operation_id == first.operation.operation_id
    assert replay.operation.expires_at == first.operation.expires_at
    assert await _effects(database, issued, context) == before
    assert await PostgresApplicationKeyVerifier(database).verify(
        replacement.credential, profile=HTTP
    )


async def test_changed_original_body_conflicts_without_reapplying_revocation(
    database: Database, issued_key: tuple[AccessContextDTO, ApplicationKeyIssueResultDTO]
) -> None:
    creator, issued = issued_key
    command, context = _request(issued)
    first = await _revoke(database, creator, command, context)
    before = await _effects(database, issued, context)
    with pytest.raises(ConflictError):
        await _revoke(
            database,
            creator,
            replace(command, expected_access_revision=first.original.access_revision),
            context,
        )
    assert await _effects(database, issued, context) == before


async def test_an_already_expired_key_can_still_be_explicitly_revoked(
    database: Database, issued_key: tuple[AccessContextDTO, ApplicationKeyIssueResultDTO]
) -> None:
    creator, issued = issued_key
    command, context = _request(issued)
    async with database.session() as session, session.begin():
        await session.execute(
            update(ApplicationKeyRow)
            .where(ApplicationKeyRow.key_id == command.key_id.value)
            .values(expires_at=func.clock_timestamp(type_=DateTime(timezone=True)))
        )
    result = await _revoke(database, creator, command, context)
    assert result.operation.created and result.original.metadata.revoked_at is not None
    assert result.original.metadata.expires_at <= result.original.metadata.revoked_at
    assert result.original.access_revision == issued.original.access_revision + 1


@pytest.mark.parametrize("oauth", [False, True], ids=["browser-recovery", "stale-oauth-generation"])
async def test_current_recovery_and_credential_checks_precede_saved_receipt(
    database: Database,
    issued_key: tuple[AccessContextDTO, ApplicationKeyIssueResultDTO],
    oauth: bool,
) -> None:
    creator, issued = issued_key
    assert isinstance(creator.authentication_evidence, BrowserSessionAuthenticationDTO)
    identity = creator.authentication_evidence.identity
    state = await PostgresHumanCredentialStateInitializer(database).initialize(identity)
    assert state.version is not None
    access = (
        AccessContextDTO(
            creator.actor_principal_id,
            HumanOAuthCredentialBindingDTO(identity, state.installation_id, state.version),
        )
        if oauth
        else creator
    )
    command, context = _request(issued)
    await _revoke(database, access, command, context)
    async with database.session() as session, session.begin():
        await IdentityRecoveryAdmissionService(
            PostgresIdentityRecoveryAdmissionWriter(
                session, installation_id=state.installation_id, authority=identity.authority
            )
        ).admit(
            IdentityRecoveryEventDTO(
                IdentityRecoveryFlowId(uuid4()), identity, IdentityRecoveryEventKind.RECOVERY
            )
        )
    before = await _effects(database, issued, context)
    rejected = HumanOAuthCredentialRejectedError if oauth else AuthenticationRequiredError
    with pytest.raises(rejected) as error:
        await _revoke(database, access, command, context)
    assert type(error.value) is rejected
    assert await _effects(database, issued, context) == before


@pytest.mark.parametrize("reviewed", [False, True], ids=["stale-old-intent", "explicit-fresh-noop"])
async def test_expired_completed_history_does_not_reapply_the_old_effect(
    database: Database,
    issued_key: tuple[AccessContextDTO, ApplicationKeyIssueResultDTO],
    reviewed: bool,
) -> None:
    creator, issued = issued_key
    command, context = _request(issued)
    first = await _revoke(database, creator, command, context)
    async with database.session() as session, session.begin():
        await session.execute(
            update(IdempotencyReservationRow)
            .where(IdempotencyReservationRow.operation_id == first.operation.operation_id.value)
            .values(
                expires_at=func.clock_timestamp(type_=DateTime(timezone=True))
                - timedelta(seconds=1)
            )
        )
    before = await _effects(database, issued, context)
    if not reviewed:
        with pytest.raises(StaleRevisionError):
            await _revoke(database, creator, command, context)
    else:
        fresh = await _revoke(
            database,
            creator,
            replace(command, expected_access_revision=first.original.access_revision),
            context,
        )
        assert (
            fresh.operation.created and fresh.operation.operation_id != first.operation.operation_id
        )
        assert fresh.original.metadata == first.original.metadata
    assert await _effects(database, issued, context) == before


@pytest.mark.parametrize("failure", ["audit", "original", "before-commit", "cancellation"])
async def test_known_failure_rolls_back_every_business_and_shared_effect(
    database: Database,
    issued_key: tuple[AccessContextDTO, ApplicationKeyIssueResultDTO],
    failure: str,
) -> None:
    creator, issued = issued_key
    command, context = _request(issued)
    before = await _effects(database, issued, context)
    async with database.session() as session:

        def reject_flush(current: Session, _context: object, _instances: object) -> None:
            if any(
                (
                    isinstance(row, AccessAuditEventRow)
                    and row.event_type == "application_key_revoked"
                )
                if failure == "audit"
                else isinstance(row, ApplicationKeyRevocationResultRow)
                for row in current.new
            ):
                raise RuntimeError("Controlled required persistence failure")

        def reject_commit(_session: Session) -> None:
            if failure == "cancellation":
                raise asyncio.CancelledError()
            raise RuntimeError("Controlled failure before COMMIT")

        hook = "before_flush" if failure in ("audit", "original") else "before_commit"
        callback = reject_flush if failure in ("audit", "original") else reject_commit
        event.listen(session.sync_session, hook, callback)
        try:
            with pytest.raises(
                asyncio.CancelledError if failure == "cancellation" else RuntimeError
            ):
                await revocation_service(session).revoke(
                    access=creator, command=command, context=context
                )
        finally:
            event.remove(session.sync_session, hook, callback)
    assert await _effects(database, issued, context) == before


async def test_lost_application_commit_ack_recovers_the_actual_committed_original(
    database: Database, issued_key: tuple[AccessContextDTO, ApplicationKeyIssueResultDTO]
) -> None:
    """Inject the existing application-acknowledgment seam after real COMMIT, not a DB wire fault."""
    creator, issued = issued_key
    command, context = _request(issued)
    async with database.session() as session:

        def lose_ack(_session: Session) -> None:
            raise RuntimeError("Controlled lost COMMIT acknowledgment")

        event.listen(session.sync_session, "after_commit", lose_ack)
        try:
            with pytest.raises(RuntimeError, match="lost COMMIT acknowledgment"):
                await revocation_service(session).revoke(
                    access=creator, command=command, context=context
                )
        finally:
            event.remove(session.sync_session, "after_commit", lose_ack)
    committed = await _effects(database, issued, context)
    assert committed[1] is not None and committed[2:] == (1, 1, 1)
    recovered = await _revoke(database, creator, command, context)
    assert not recovered.operation.created
    assert recovered.original.metadata.revoked_at == committed[1]
    assert await _effects(database, issued, context) == committed


@pytest.mark.parametrize("same_request", [False, True], ids=["distinct-intents", "same-original"])
async def test_concurrent_revocations_keep_one_transition_and_safe_originals(
    database: Database,
    issued_key: tuple[AccessContextDTO, ApplicationKeyIssueResultDTO],
    same_request: bool,
) -> None:
    creator, issued = issued_key
    command, context = _request(issued)

    async def revoke(index: int) -> ApplicationKeyRevocationResultDTO | None:
        selected = (
            context if same_request else replace(context, key=IdempotencyKey(f"revoke-{index}"))
        )
        try:
            return await _revoke(database, creator, command, selected)
        except StaleRevisionError:
            if same_request:
                raise
            return None

    async with asyncio.TaskGroup() as tasks:
        one, two = tasks.create_task(revoke(1)), tasks.create_task(revoke(2))
    results = (one.result(), two.result())
    assert sum(r is not None and r.operation.created for r in results) == 1
    if same_request:
        assert results[0] is not None and results[1] is not None
        assert results[0].original == results[1].original
    else:
        assert sum(r is None for r in results) == 1
    effects = await _effects(database, issued, context)
    assert effects[0] == issued.original.access_revision + 1 and effects[2:] == (1, 1, 1)


@pytest.mark.parametrize("profile", [HTTP, MCP], ids=["http", "mcp"])
async def test_revoked_dual_key_fails_verification_and_current_disclosure(
    database: Database, profile: ApplicationKeyVerificationProfileDTO
) -> None:
    creator, issued = await issue_application_key(
        database, adapters=(ApplicationKeyAdapter.HTTP, ApplicationKeyAdapter.MCP)
    )
    credential = issued.credential
    assert credential is not None
    verifier = PostgresApplicationKeyVerifier(database)
    facts = PostgresApplicationAuthenticationFactsReader(database)
    authenticator = ApplicationAuthenticationService(
        key_verifier=verifier, authentication_facts_reader=facts, verification_profile=profile
    )
    access = await authenticator.authenticate(credential)
    command, context = _request(issued)
    result = await _revoke(database, creator, command, context)
    assert result.original.metadata.allowed_adapters == issued.original.metadata.allowed_adapters
    assert await verifier.verify(credential, profile=profile) is None
    with pytest.raises(AuthenticationRequiredError):
        await authenticator.authenticate(credential)
    with pytest.raises(ApplicationKeyCredentialRejectedError):
        await ApplicationSessionService(
            authentication_facts_reader=facts, verification_profile=profile
        ).read(access=access)
    async with database.session() as session:
        original = await session.get(
            ApplicationKeyRevocationResultRow, result.operation.operation_id.value
        )
        audit = await session.scalar(
            select(AccessAuditEventRow).where(
                AccessAuditEventRow.correlation_id == result.operation.operation_id.value
            )
        )
        assert original is not None and audit is not None
        safe = repr(original) + dumps(audit.before_values) + dumps(audit.after_values)
    assert credential.value not in safe and credential.digest().hex() not in safe
    assert HTTP.audience.value not in safe and MCP.audience.value not in safe


async def test_replay_requires_current_revoke_authority_and_never_regrants_it(
    database: Database, issued_key: tuple[AccessContextDTO, ApplicationKeyIssueResultDTO]
) -> None:
    creator, issued = issued_key
    command, context = _request(issued)
    first = await _revoke(database, creator, command, context)
    assert isinstance(creator.authentication_evidence, BrowserSessionAuthenticationDTO)
    authority = creator.authentication_evidence.identity.authority
    fingerprints = RequestFingerprintService(RequestFingerprintKey(b"r" * 32))
    async with database.session() as session:
        revision = await session.scalar(
            select(OrganizationRow.access_revision).where(
                OrganizationRow.id == issued.original.organization_id.value
            )
        )
        assert revision is not None
    async with open_human_admission(
        database,
        HumanAdmissionFingerprintService(fingerprints),
        MockBootstrapIdentityVerifier(),
        authority,
        5,
    ) as admission:
        bob = await admission.admit(
            access=creator,
            command=AdmitHumanCommand(issued.original.organization_id, UUID(int=200), revision),
            context=IdempotencyContextDTO(
                HttpMethod.POST,
                f"/v1/organizations/{issued.original.organization_id.value}/human-admissions",
                IdempotencyKey("admit-grantor"),
            ),
        )
    factory = PostgresProjectMembershipChangeServiceFactory(
        database, ProjectMembershipChangeFingerprintService(fingerprints)
    )
    async with factory.open() as membership:
        joined = await membership.add_member(
            access=creator,
            command=AddProjectMemberCommand(
                command.project_id, bob.principal_id, first.original.access_revision
            ),
            context=IdempotencyContextDTO(
                HttpMethod.PUT,
                f"/v1/projects/{command.project_id.value}/members/{bob.principal_id.value}",
                IdempotencyKey("join-grantor"),
            ),
        )
    action = ActionId(ApplicationAccountAction.REVOKE_KEYS.value)
    route = f"/v1/projects/{command.project_id.value}/application-accounts/{command.application_principal_id.value}/grants"
    async with open_application_account_grant_change(database, fingerprints) as grants:
        granted = await grants.set_grant(
            access=creator,
            command=SetApplicationAccountActionGrantCommand(
                command.project_id,
                command.application_principal_id,
                bob.principal_id,
                action,
                True,
                joined.access_revision,
            ),
            context=IdempotencyContextDTO(
                HttpMethod.PUT,
                f"{route}/{bob.principal_id.value}/{action.value}",
                IdempotencyKey("delegate-revoke"),
            ),
        )
    async with open_application_account_grant_change(database, fingerprints) as grants:
        removed = await grants.remove_grant(
            access=creator,
            command=RemoveApplicationAccountActionGrantCommand(
                command.project_id,
                command.application_principal_id,
                creator.actor_principal_id,
                action,
                granted.access_revision,
            ),
            context=IdempotencyContextDTO(
                HttpMethod.DELETE,
                f"{route}/{creator.actor_principal_id.value}/{action.value}",
                IdempotencyKey("remove-original-revoke"),
            ),
        )
    before = await _effects(database, issued, context)
    with pytest.raises(AccessDeniedError):
        await _revoke(database, creator, command, context)
    assert await _effects(database, issued, context) == before
    bob_identity = VerifiedHumanIdentityDTO(authority, IdentitySubject(str(UUID(int=200))))
    bob_state = await PostgresHumanCredentialStateReader(database).read(bob_identity)
    assert bob_state.version is not None
    bob_access = AccessContextDTO(
        bob.principal_id,
        BrowserSessionAuthenticationDTO(bob_identity, bob_state.installation_id, bob_state.version),
    )
    async with open_application_account_grant_change(database, fingerprints) as grants:
        await grants.set_grant(
            access=bob_access,
            command=SetApplicationAccountActionGrantCommand(
                command.project_id,
                command.application_principal_id,
                creator.actor_principal_id,
                action,
                False,
                removed.access_revision,
            ),
            context=IdempotencyContextDTO(
                HttpMethod.PUT,
                f"{route}/{creator.actor_principal_id.value}/{action.value}",
                IdempotencyKey("restore-use-only"),
            ),
        )
    before = await _effects(database, issued, context)
    replay = await _revoke(database, creator, command, context)
    assert replay.original == first.original and not replay.operation.created
    assert await _effects(database, issued, context) == before
    async with database.session() as session:
        assert (
            await session.scalar(
                select(ApplicationActionGrantRow.can_grant).where(
                    ApplicationActionGrantRow.project_id == command.project_id.value,
                    ApplicationActionGrantRow.application_principal_id
                    == command.application_principal_id.value,
                    ApplicationActionGrantRow.recipient_principal_id
                    == creator.actor_principal_id.value,
                    ApplicationActionGrantRow.action == action.value,
                )
            )
            is False
        )


def _job_service(session: AsyncSession) -> JobAdmissionService:
    return JobAdmissionService(
        ActionAuthorizationService(
            PostgresProjectActionFactsReader(session, application_key_profile=HTTP)
        ),
        AdmittedWorkAuthorizationService(PostgresAdmittedWorkFactsReader(session)),
        IdempotencyService(PostgresOperationReservationWriter(session)),
        PostgresJobStore(session),
        PostgresJobAdmissionAuditWriter(session),
        supported_payloads=(("test.progress", 1),),
    )


@pytest.mark.parametrize("winner", ["admission", "revocation"])
async def test_real_job_admission_and_revocation_preserve_the_winning_order(
    database: Database,
    issued_key: tuple[AccessContextDTO, ApplicationKeyIssueResultDTO],
    winner: str,
) -> None:
    creator, issued = issued_key
    metadata, credential = issued.original.metadata, issued.credential
    assert credential is not None
    action = ActionId(ProjectAction.INSPECT_FEEDBACK.value)
    async with database.session() as session:
        granted = await create_project_grant_change_service(session).set_action_grant(
            access=creator,
            command=SetProjectActionGrantCommand(
                metadata.project_id,
                metadata.application_principal_id,
                action,
                False,
                issued.original.access_revision,
            ),
            context=IdempotencyContextDTO(
                HttpMethod.PUT,
                f"/v1/projects/{metadata.project_id.value}/grants/{metadata.application_principal_id.value}/{action.value}",
                IdempotencyKey("allow-job"),
            ),
        )
    access = await ApplicationAuthenticationService(
        key_verifier=PostgresApplicationKeyVerifier(database),
        authentication_facts_reader=PostgresApplicationAuthenticationFactsReader(database),
        verification_profile=HTTP,
    ).authenticate(credential)
    authority = AdmittedWorkAuthorityDTO(
        metadata.application_principal_id,
        PrincipalKind.APPLICATION,
        issued.original.installation_id,
        issued.original.organization_id,
        metadata.project_id,
        action,
        None,
    )
    job_context = IdempotencyContextDTO(
        HttpMethod.POST,
        "/test/projects/{project_id}/feedback-reports",
        IdempotencyKey("application-job"),
    )
    fingerprint = RequestFingerprint(b"J" * 32)
    payload = JobPayload("test.progress", 1, b"fixed")
    request_id = RequestId(uuid4())
    command, context = _request(issued)
    command = replace(command, expected_access_revision=granted.access_revision)
    pid, name = column("pid", Integer), column("datname", String)
    activity = table("pg_stat_activity", pid, name)
    revoke_task: asyncio.Task[ApplicationKeyRevocationResultDTO] | None = None
    admission_task: asyncio.Task[JobAdmissionDTO] | None = None
    original: JobAdmissionDTO | None = None
    work_error: BaseException | None = None
    observed_denial: BaseException | None = None

    async def admit() -> JobAdmissionDTO:
        async with database.session() as session, session.begin():
            return await _job_service(session).admit(
                access=access,
                authority=authority,
                context=job_context,
                fingerprint=fingerprint,
                request_id=request_id,
                payload=payload,
            )

    try:
        async with database.session() as holder, holder.begin():
            if winner == "admission":
                original = await _job_service(holder).admit(
                    access=access,
                    authority=authority,
                    context=job_context,
                    fingerprint=fingerprint,
                    request_id=request_id,
                    payload=payload,
                )
            else:
                await holder.scalar(
                    select(ProjectRow.id)
                    .where(ProjectRow.id == metadata.project_id.value)
                    .with_for_update()
                )
            holder_pid = await holder.scalar(select(func.pg_backend_pid(type_=Integer)))
            assert holder_pid is not None
            revoke_task = asyncio.create_task(_revoke(database, creator, command, context))
            revoker_pid = None
            async with asyncio.timeout(3):
                while not revoke_task.done():
                    async with database.session() as observer:
                        revoker_pid = await observer.scalar(
                            select(pid)
                            .select_from(activity)
                            .where(
                                name == func.current_database(type_=String()),
                                func.pg_blocking_pids(pid, type_=ARRAY(Integer)).contains(
                                    [holder_pid]
                                ),
                            )
                        )
                    if revoker_pid is not None:
                        break
                    await asyncio.sleep(0.01)
            if revoker_pid is None:
                await revoke_task
                pytest.fail("Revocation bypassed the winning caller's Project guard.")
            if winner == "revocation":
                admission_task = asyncio.create_task(admit())
                blocked = None
                async with asyncio.timeout(3):
                    while not admission_task.done():
                        async with database.session() as observer:
                            blocked = await observer.scalar(
                                select(pid)
                                .select_from(activity)
                                .where(
                                    name == func.current_database(type_=String()),
                                    pid != revoker_pid,
                                    func.pg_blocking_pids(pid, type_=ARRAY(Integer)).contains(
                                        [holder_pid]
                                    )
                                    | func.pg_blocking_pids(pid, type_=ARRAY(Integer)).contains(
                                        [revoker_pid]
                                    ),
                                )
                            )
                        if blocked is not None:
                            break
                        await asyncio.sleep(0.01)
                if blocked is None:
                    await admission_task
                    pytest.fail("Admission bypassed the queued revocation turn.")
        async with asyncio.timeout(3):
            revoked = await revoke_task
            if admission_task is not None:
                with pytest.raises(ApplicationKeyCredentialRejectedError) as denied:
                    await admission_task
                observed_denial = denied.value
        assert revoked.original.metadata.revoked_at is not None
    except BaseException as error:
        work_error = error
        raise
    finally:
        owned = [task for task in (revoke_task, admission_task) if task is not None]
        try:
            async with asyncio.timeout(3):
                for task in owned:
                    if not task.done():
                        task.cancel()
                pending_results: list[
                    Awaitable[ApplicationKeyRevocationResultDTO | JobAdmissionDTO]
                ] = [task for task in owned]
                outcomes = await asyncio.shield(
                    asyncio.gather(*pending_results, return_exceptions=True)
                )
            errors = [
                e
                for e in outcomes
                if isinstance(e, BaseException)
                and not isinstance(e, asyncio.CancelledError)
                and e is not work_error
                and e is not observed_denial
            ]
            if errors:
                raise BaseExceptionGroup("Owned admission or revocation task failed", errors)
        except BaseException as cleanup_error:
            if work_error is not None and cleanup_error is not work_error:
                raise BaseExceptionGroup(
                    "Job ordering and task cleanup failed", [work_error, cleanup_error]
                ) from None
            raise

    async with database.session() as session:
        jobs = (
            await session.scalars(
                select(DurableJobRow).where(
                    DurableJobRow.principal_id == metadata.application_principal_id.value
                )
            )
        ).all()
        assert len(jobs) == (1 if winner == "admission" else 0)
        reservations = await session.scalar(
            select(func.count())
            .select_from(IdempotencyReservationRow)
            .where(IdempotencyReservationRow.requested_route == job_context.requested_route)
        )
        assert reservations == (1 if winner == "admission" else 0)
    if original is not None:
        assert original.created
        async with database.session() as session, session.begin():
            saved = await PostgresJobStore(session).find(original.operation_id)
            assert saved is not None and isinstance(saved.binding, ProductJobBindingDTO)
            assert saved.binding.authority == authority and saved.status is JobStatus.QUEUED
            assert credential.value not in repr(saved)
            await AdmittedWorkAuthorizationService(
                PostgresAdmittedWorkFactsReader(session)
            ).require_current(authority)
        with pytest.raises(ApplicationKeyCredentialRejectedError):
            await admit()
        replacement = await _replacement(
            database, creator, issued, revoked.original.access_revision
        )
        assert replacement.credential is not None
        access = await ApplicationAuthenticationService(
            key_verifier=PostgresApplicationKeyVerifier(database),
            authentication_facts_reader=PostgresApplicationAuthenticationFactsReader(database),
            verification_profile=HTTP,
        ).authenticate(replacement.credential)
        replay = await admit()
        assert (
            not replay.created
            and replay.operation_id == original.operation_id
            and replay.job_id == original.job_id
        )


async def test_issuance_and_revocation_cannot_both_apply_the_same_reviewed_revision(
    database: Database, issued_key: tuple[AccessContextDTO, ApplicationKeyIssueResultDTO]
) -> None:
    creator, issued = issued_key
    command, context = _request(issued)

    async def revoke() -> ApplicationKeyRevocationResultDTO | None:
        try:
            return await _revoke(database, creator, command, context)
        except StaleRevisionError:
            return None

    async def issue() -> ApplicationKeyIssueResultDTO | None:
        try:
            return await _replacement(database, creator, issued, command.expected_access_revision)
        except StaleRevisionError:
            return None

    async with asyncio.TaskGroup() as tasks:
        revocation, issuance = tasks.create_task(revoke()), tasks.create_task(issue())
    revoked, replacement = revocation.result(), issuance.result()
    assert (revoked is None) != (replacement is None)
    async with database.session() as session:
        assert (
            await session.scalar(
                select(ProjectRow.access_revision).where(ProjectRow.id == command.project_id.value)
            )
            == command.expected_access_revision + 1
        )
        keys = (
            await session.scalars(
                select(ApplicationKeyRow).where(
                    ApplicationKeyRow.application_principal_id
                    == command.application_principal_id.value
                )
            )
        ).all()
        assert len(keys) == (2 if replacement is not None else 1)
        assert sum(row.revoked_at is None for row in keys) == (2 if replacement is not None else 0)


@pytest.mark.parametrize("winner", ["retirement", "revocation"])
async def test_controlled_retirement_orders_revocation_and_retains_only_its_committed_original(
    database: Database,
    issued_key: tuple[AccessContextDTO, ApplicationKeyIssueResultDTO],
    winner: str,
) -> None:
    """Use the accepted retirement row state and lock turn, not the future #233 workflow."""
    creator, issued = issued_key
    command, context = _request(issued)
    pid, name = column("pid", Integer), column("datname", String)
    activity = table("pg_stat_activity", pid, name)
    first_task: asyncio.Task[ApplicationKeyRevocationResultDTO | None] | None = None
    second_task: asyncio.Task[ApplicationKeyRevocationResultDTO | None] | None = None
    work_error: BaseException | None = None

    async def retire() -> ApplicationKeyRevocationResultDTO | None:
        # Only the coordinated terminal rows are controlled here. Retirement's
        # authorization, audit, original result and public API remain with #233.
        async with database.session() as session, session.begin():
            await session.scalar(
                select(OrganizationRow.id)
                .where(OrganizationRow.id == issued.original.organization_id.value)
                .with_for_update(read=True)
            )
            project = await session.scalar(
                select(ProjectRow)
                .where(ProjectRow.id == command.project_id.value)
                .with_for_update()
            )
            keys = (
                await session.scalars(
                    select(ApplicationKeyRow)
                    .where(
                        ApplicationKeyRow.project_id == command.project_id.value,
                        ApplicationKeyRow.application_principal_id
                        == command.application_principal_id.value,
                    )
                    .order_by(ApplicationKeyRow.key_id)
                    .with_for_update()
                )
            ).all()
            now = await session.scalar(select(func.clock_timestamp(type_=DateTime(timezone=True))))
            assert project is not None and now is not None and len(keys) == 1
            assert project.access_revision == command.expected_access_revision + (
                winner == "revocation"
            )
            assert (keys[0].revoked_at is not None) == (winner == "revocation")
            for key in keys:
                if key.revoked_at is None:
                    key.revoked_at = now
            project.access_revision += 1
            await session.execute(
                update(PrincipalRow)
                .where(PrincipalRow.id == command.application_principal_id.value)
                .values(status=PrincipalStatus.RETIRED)
            )
            await session.execute(
                delete(ApplicationActionGrantRow).where(
                    ApplicationActionGrantRow.project_id == command.project_id.value,
                    ApplicationActionGrantRow.application_principal_id
                    == command.application_principal_id.value,
                )
            )
            await session.execute(
                delete(ProjectMembershipRow).where(
                    ProjectMembershipRow.project_id == command.project_id.value,
                    ProjectMembershipRow.principal_id == command.application_principal_id.value,
                )
            )
        return None

    async def revoke() -> ApplicationKeyRevocationResultDTO | None:
        try:
            return await _revoke(database, creator, command, context)
        except AccessDeniedError:
            assert winner == "retirement"
            return None

    try:
        async with database.session() as holder, holder.begin():
            await holder.scalar(
                select(OrganizationRow.id)
                .where(OrganizationRow.id == issued.original.organization_id.value)
                .with_for_update(read=True)
            )
            await holder.scalar(
                select(ProjectRow.id)
                .where(ProjectRow.id == command.project_id.value)
                .with_for_update()
            )
            holder_pid = await holder.scalar(select(func.pg_backend_pid(type_=Integer)))
            assert holder_pid is not None
            first_task = asyncio.create_task(retire() if winner == "retirement" else revoke())
            first_pid = None
            async with asyncio.timeout(3):
                while not first_task.done():
                    async with database.session() as observer:
                        first_pid = await observer.scalar(
                            select(pid)
                            .select_from(activity)
                            .where(
                                name == func.current_database(type_=String()),
                                func.pg_blocking_pids(pid, type_=ARRAY(Integer)).contains(
                                    [holder_pid]
                                ),
                            )
                        )
                    if first_pid is not None:
                        break
                    await asyncio.sleep(0.01)
            if first_pid is None:
                await first_task
                pytest.fail("The winning operation bypassed the Project coordination turn.")

            second_task = asyncio.create_task(revoke() if winner == "retirement" else retire())
            second_pid = None
            async with asyncio.timeout(3):
                while not second_task.done():
                    async with database.session() as observer:
                        second_pid = await observer.scalar(
                            select(pid)
                            .select_from(activity)
                            .where(
                                name == func.current_database(type_=String()),
                                pid != first_pid,
                                func.pg_blocking_pids(pid, type_=ARRAY(Integer)).contains(
                                    [holder_pid]
                                )
                                | func.pg_blocking_pids(pid, type_=ARRAY(Integer)).contains(
                                    [first_pid]
                                ),
                            )
                        )
                    if second_pid is not None:
                        break
                    await asyncio.sleep(0.01)
            if second_pid is None:
                await second_task
                pytest.fail("The losing operation bypassed the queued Project turn.")
        async with asyncio.timeout(3):
            first, second = await first_task, await second_task
        revoked = second if winner == "retirement" else first
        assert (revoked is not None) == (winner == "revocation")
    except BaseException as error:
        work_error = error
        raise
    finally:
        owned = [task for task in (first_task, second_task) if task is not None]
        try:
            async with asyncio.timeout(3):
                for task in owned:
                    if not task.done():
                        task.cancel()
                outcomes = await asyncio.shield(asyncio.gather(*owned, return_exceptions=True))
            errors = [
                error
                for error in outcomes
                if isinstance(error, BaseException)
                and not isinstance(error, asyncio.CancelledError)
                and error is not work_error
            ]
            if errors:
                raise BaseExceptionGroup("Owned retirement or revocation task failed", errors)
        except BaseException as cleanup_error:
            if work_error is not None and cleanup_error is not work_error:
                raise BaseExceptionGroup(
                    "Retirement ordering and task cleanup failed", [work_error, cleanup_error]
                ) from None
            raise

    effects = await _effects(database, issued, context)
    assert effects[0] == command.expected_access_revision + 1 + (winner == "revocation")
    assert effects[1] is not None
    assert effects[2:] == ((1, 1, 1) if revoked is not None else (0, 0, 0))
    async with database.session() as session, session.begin():
        reader = PostgresApplicationKeyRevocationFactsReader(session)
        facts = await reader.lock_for_revoke(access=creator, command=command)
        assert facts is not None and facts.metadata is not None
        assert facts.application_principal.status is PrincipalStatus.RETIRED
        assert not facts.actor.has_exact_action_grant
        assert facts.access_revision == effects[0]
        assert facts.metadata.revoked_at == effects[1]
        assert facts.checked_at >= effects[1]
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ProjectMembershipRow)
                .where(
                    ProjectMembershipRow.project_id == command.project_id.value,
                    ProjectMembershipRow.principal_id == command.application_principal_id.value,
                )
            )
            == 0
        )
        if revoked is not None:
            retained = await reader.read_original(
                organization_id=revoked.original.organization_id,
                project_id=command.project_id,
                actor_principal_id=creator.actor_principal_id,
                operation_id=revoked.operation.operation_id,
            )
            assert retained is not None and retained == revoked.original
            assert retained.metadata.revoked_at == effects[1]
    with pytest.raises(AccessDeniedError):
        await _revoke(database, creator, command, context)
    assert await _effects(database, issued, context) == effects
    assert issued.credential is not None
    assert (
        await PostgresApplicationKeyVerifier(database).verify(issued.credential, profile=HTTP)
        is None
    )
