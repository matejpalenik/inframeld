"""Exercise real retirement storage with stored human credential facts and controlled provider evidence."""

import asyncio
import os
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from alembic import command as alembic_command
from alembic.config import Config
from sqlalchemy import DateTime, Integer, String, column, delete, event, func, select, table, update
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from tests.support.access_group_scenarios import change_group, create_group
from tests.support.application_account_scenarios import create_account
from tests.support.application_key_scenarios import issue_application_key, store_application_key
from tests.support.project_creation_scenarios import ProjectCreationSeedDTO, create_project
from tests.support.project_grant_changes import create_project_grant_change_service
from tests.support.project_upload_default_scenarios import (
    upload_default_context,
    upload_default_service,
)

from inframeld_backend.access.application.commands.delete_application_account_command import (
    DeleteApplicationAccountCommand,
)
from inframeld_backend.access.application.commands.issue_application_key_command import (
    IssueApplicationKeyCommand,
)
from inframeld_backend.access.application.commands.revoke_application_key_command import (
    RevokeApplicationKeyCommand,
)
from inframeld_backend.access.application.commands.set_project_action_grant_command import (
    SetProjectActionGrantCommand,
)
from inframeld_backend.access.application.commands.set_project_upload_default_command import (
    SetProjectUploadDefaultCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.application_account_deletion_record_dto import (
    ApplicationAccountDeletionRecordDTO,
)
from inframeld_backend.access.application.dtos.application_account_deletion_result_dto import (
    ApplicationAccountDeletionResultDTO,
)
from inframeld_backend.access.application.dtos.application_key_creation_dto import (
    ApplicationKeyCreationDTO,
)
from inframeld_backend.access.application.dtos.application_key_issue_result_dto import (
    ApplicationKeyIssueResultDTO,
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
from inframeld_backend.access.application.enums.access_group_change_kind import (
    AccessGroupChangeKind,
)
from inframeld_backend.access.application.errors.human_oauth_credential_rejected_error import (
    HumanOAuthCredentialRejectedError,
)
from inframeld_backend.access.application.services.action_authorization_service import (
    ActionAuthorizationService,
)
from inframeld_backend.access.application.services.application_account_deletion_fingerprint_service import (
    ApplicationAccountDeletionFingerprintService,
)
from inframeld_backend.access.application.services.application_account_deletion_service import (
    ApplicationAccountDeletionService,
)
from inframeld_backend.access.application.services.application_authentication_service import (
    ApplicationAuthenticationService,
)
from inframeld_backend.access.application.services.application_key_issuance_fingerprint_service import (
    ApplicationKeyIssuanceFingerprintService,
)
from inframeld_backend.access.domain.enums.access_group_action import AccessGroupAction
from inframeld_backend.access.domain.enums.application_account_action import (
    ApplicationAccountAction,
)
from inframeld_backend.access.domain.enums.application_key_adapter import ApplicationKeyAdapter
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.enums.project_action import ProjectAction
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.application_key_audience import (
    ApplicationKeyAudience,
)
from inframeld_backend.access.domain.value_objects.upload_audience import UploadAudience
from inframeld_backend.access.infrastructure.readers.postgres_application_account_deletion_facts_reader import (
    PostgresApplicationAccountDeletionFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_application_authentication_facts_reader import (
    PostgresApplicationAuthenticationFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_application_key_revocation_facts_reader import (
    PostgresApplicationKeyRevocationFactsReader,
)
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.access.infrastructure.rows.access_group_row import AccessGroupRow
from inframeld_backend.access.infrastructure.rows.application_account_creation_result_row import (
    ApplicationAccountCreationResultRow,
)
from inframeld_backend.access.infrastructure.rows.application_account_deletion_result_row import (
    ApplicationAccountDeletionResultRow,
)
from inframeld_backend.access.infrastructure.rows.application_account_name_reservation_row import (
    ApplicationAccountNameReservationRow,
)
from inframeld_backend.access.infrastructure.rows.application_account_row import (
    ApplicationAccountRow,
)
from inframeld_backend.access.infrastructure.rows.application_action_grant_row import (
    ApplicationActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.application_key_issuance_result_row import (
    ApplicationKeyIssuanceResultRow,
)
from inframeld_backend.access.infrastructure.rows.application_key_row import ApplicationKeyRow
from inframeld_backend.access.infrastructure.rows.group_action_grant_row import GroupActionGrantRow
from inframeld_backend.access.infrastructure.rows.group_manager_row import GroupManagerRow
from inframeld_backend.access.infrastructure.rows.group_membership_row import GroupMembershipRow
from inframeld_backend.access.infrastructure.rows.human_credential_version_row import (
    HumanCredentialVersionRow,
)
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.project_membership_row import ProjectMembershipRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.access.infrastructure.rows.project_upload_default_group_row import (
    ProjectUploadDefaultGroupRow,
)
from inframeld_backend.access.infrastructure.rows.project_upload_default_result_row import (
    ProjectUploadDefaultResultRow,
)
from inframeld_backend.access.infrastructure.settings.application_key_issuance_settings import (
    ApplicationKeyIssuanceSettings,
)
from inframeld_backend.access.infrastructure.verifiers.postgres_application_key_verifier import (
    PostgresApplicationKeyVerifier,
)
from inframeld_backend.access.infrastructure.writers.postgres_application_account_deletion_writer import (
    PostgresApplicationAccountDeletionWriter,
)
from inframeld_backend.access.infrastructure.writers.postgres_application_key_issuance_writer import (
    PostgresApplicationKeyIssuanceWriter,
)
from inframeld_backend.access.infrastructure.writers.postgres_human_credential_state_initializer import (
    PostgresHumanCredentialStateInitializer,
)
from inframeld_backend.bootstrap.application_key_composition import open_application_key_issuance
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
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.enums.operation_reservation_state import (
    OperationReservationState,
)
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    AuthenticationRequiredError,
    ConflictError,
    ResourceNotFoundError,
    StaleRevisionError,
)
from inframeld_backend.shared.application.services.idempotency_service import IdempotencyService
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.application.value_objects.request_fingerprint_key import (
    RequestFingerprintKey,
)
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation
from inframeld_backend.shared.infrastructure.migrations.migration_runner import ALEMBIC_CONFIG_PATH
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.resources.sqlalchemy_transaction_manager import (
    SqlAlchemyTransactionManager,
)
from inframeld_backend.shared.infrastructure.rows.alembic_version_row import AlembicVersionRow
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)
from inframeld_backend.shared.infrastructure.settings.database_settings import DatabaseSettings
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


def deletion_service(session: AsyncSession) -> ApplicationAccountDeletionService:
    """Compose the real adapters on one caller session, without public registration."""
    return ApplicationAccountDeletionService(
        transaction_manager=SqlAlchemyTransactionManager(session),
        deletion_facts_reader=PostgresApplicationAccountDeletionFactsReader(session),
        deletion_writer=PostgresApplicationAccountDeletionWriter(session),
        operation_idempotency=IdempotencyService(PostgresOperationReservationWriter(session)),
        deletion_fingerprint_service=ApplicationAccountDeletionFingerprintService(
            RequestFingerprintService(RequestFingerprintKey(b"r" * 32))
        ),
    )


@pytest_asyncio.fixture
async def retirement_scope(
    database: Database,
) -> tuple[AccessContextDTO, ApplicationKeyIssueResultDTO]:
    creator, issued = await issue_application_key(
        database, adapters=(ApplicationKeyAdapter.HTTP, ApplicationKeyAdapter.MCP)
    )
    evidence = creator.authentication_evidence
    assert isinstance(evidence, BrowserSessionAuthenticationDTO)
    state = await PostgresHumanCredentialStateInitializer(database).initialize(evidence.identity)
    assert state.version is not None
    access = replace(
        creator,
        authentication_evidence=HumanOAuthCredentialBindingDTO(
            evidence.identity, state.installation_id, state.version
        ),
    )
    metadata = issued.original.metadata
    assert issued.credential is not None
    for profile in (HTTP, MCP):
        authenticated = await ApplicationAuthenticationService(
            key_verifier=PostgresApplicationKeyVerifier(database),
            authentication_facts_reader=PostgresApplicationAuthenticationFactsReader(database),
            verification_profile=profile,
        ).authenticate(issued.credential)
        assert authenticated.actor_principal_id == metadata.application_principal_id

    async with database.session() as session, session.begin():
        facts = await PostgresApplicationKeyRevocationFactsReader(session).lock_for_revoke(
            access=access,
            command=RevokeApplicationKeyCommand(
                metadata.project_id,
                metadata.application_principal_id,
                metadata.key_id,
                issued.original.access_revision,
            ),
        )
        assert facts is not None and facts.metadata == metadata
        assert facts.actor.oauth_credential_facts is not None
        assert facts.actor.oauth_credential_facts.binding_matches_actor
        assert facts.actor.oauth_credential_facts.current_version == state.version
        ActionAuthorizationService.require_authorization_from_facts(
            access=access, facts=facts.actor
        )
        assert (
            await session.scalar(
                select(ApplicationActionGrantRow.recipient_principal_id).where(
                    ApplicationActionGrantRow.project_id == metadata.project_id.value,
                    ApplicationActionGrantRow.application_principal_id
                    == metadata.application_principal_id.value,
                    ApplicationActionGrantRow.recipient_principal_id
                    == access.actor_principal_id.value,
                    ApplicationActionGrantRow.recipient_kind == PrincipalKind.HUMAN,
                    ApplicationActionGrantRow.action
                    == ApplicationAccountAction.DELETE_ACCOUNT.value,
                )
            )
            == access.actor_principal_id.value
        )
        assert facts.access_revision == issued.original.access_revision
    return access, issued


async def test_existing_issued_key_and_stored_oauth_scope_are_valid(
    database: Database,
    retirement_scope: tuple[AccessContextDTO, ApplicationKeyIssueResultDTO],
) -> None:
    """Keep an independent positive control before exercising the new retirement adapters."""
    access, issued = retirement_scope
    metadata = issued.original.metadata
    async with database.session() as session:
        principal = await session.get(PrincipalRow, metadata.application_principal_id.value)
        membership = await session.get(
            ProjectMembershipRow,
            (metadata.project_id.value, metadata.application_principal_id.value),
        )
        assert principal is not None and principal.status is PrincipalStatus.ACTIVE
        assert membership is not None and membership.principal_kind is PrincipalKind.APPLICATION
        assert membership.organization_id == issued.original.organization_id.value
        assert isinstance(access.authentication_evidence, HumanOAuthCredentialBindingDTO)


async def test_valid_retirement_commits_account_key_and_original(
    database: Database,
    retirement_scope: tuple[AccessContextDTO, ApplicationKeyIssueResultDTO],
) -> None:
    access, issued = retirement_scope
    metadata = issued.original.metadata
    command = DeleteApplicationAccountCommand(
        metadata.project_id, metadata.application_principal_id, issued.original.access_revision
    )
    context = IdempotencyContextDTO(
        HttpMethod.DELETE,
        f"/v1/projects/{metadata.project_id.value}/application-accounts/{metadata.application_principal_id.value}",
        IdempotencyKey("retire-exact-original"),
    )
    async with database.session() as session:
        account = await session.get(ApplicationAccountRow, metadata.application_principal_id.value)
        assert account is not None
        original_name = account.resource_name
        assert (
            await session.get(
                ProjectMembershipRow,
                (metadata.project_id.value, metadata.application_principal_id.value),
            )
            is not None
        )

    async with database.session() as session:
        result = await deletion_service(session).delete(
            access=access, command=command, context=context
        )
    assert result.original.application_principal_id == command.application_principal_id
    assert result.original.project_id == command.project_id
    assert result.original.actor_principal_id == access.actor_principal_id
    assert result.original.access_revision == command.expected_access_revision + 1
    assert (
        result.operation.created and result.operation.replay_kind is OperationReplayKind.SAFE_RESULT
    )

    async with database.session() as session:
        principal = await session.get(PrincipalRow, metadata.application_principal_id.value)
        account = await session.get(ApplicationAccountRow, metadata.application_principal_id.value)
        key = await session.get(ApplicationKeyRow, metadata.key_id.value)
        assert principal is not None and principal.status is PrincipalStatus.RETIRED
        assert account is not None and account.resource_name == original_name
        assert key is not None and key.revoked_at is not None
        assert key.allowed_adapters == [adapter.value for adapter in metadata.allowed_adapters]
        assert (
            await session.get(
                ProjectMembershipRow,
                (metadata.project_id.value, metadata.application_principal_id.value),
            )
            is None
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ApplicationActionGrantRow)
                .where(
                    ApplicationActionGrantRow.project_id == metadata.project_id.value,
                    ApplicationActionGrantRow.application_principal_id
                    == metadata.application_principal_id.value,
                )
            )
            == 0
        )
        assert (
            await session.scalar(
                select(ProjectRow.access_revision).where(ProjectRow.id == metadata.project_id.value)
            )
            == command.expected_access_revision + 1
        )
        stored = await session.get(
            ApplicationAccountDeletionResultRow, result.operation.operation_id.value
        )
        assert stored is not None
        assert (
            stored.installation_id,
            stored.organization_id,
            stored.project_id,
            stored.actor_principal_id,
            stored.application_principal_id,
            stored.before_revision,
            stored.access_revision,
        ) == (
            issued.original.installation_id.value,
            issued.original.organization_id.value,
            metadata.project_id.value,
            access.actor_principal_id.value,
            metadata.application_principal_id.value,
            command.expected_access_revision,
            command.expected_access_revision + 1,
        )
        reservation = await session.get(
            IdempotencyReservationRow, result.operation.operation_id.value
        )
        assert reservation is not None
        assert (reservation.method, reservation.requested_route, reservation.principal_id) == (
            "DELETE",
            context.requested_route,
            access.actor_principal_id.value,
        )
        assert reservation.state is OperationReservationState.REPLAYABLE
        assert reservation.replay_kind is OperationReplayKind.SAFE_RESULT
        assert reservation.expires_at == result.operation.expires_at
        audits = list(
            await session.scalars(
                select(AccessAuditEventRow).where(
                    AccessAuditEventRow.correlation_id == result.operation.operation_id.value
                )
            )
        )
        assert len(audits) == 1
        assert (audits[0].event_type, audits[0].action, audits[0].affected_principal_id) == (
            "application_account_retired",
            ApplicationAccountAction.DELETE_ACCOUNT.value,
            metadata.application_principal_id.value,
        )
        human = await session.get(PrincipalRow, access.actor_principal_id.value)
        assert human is not None and human.status is PrincipalStatus.ACTIVE
        assert (
            await session.get(
                ProjectMembershipRow, (metadata.project_id.value, access.actor_principal_id.value)
            )
            is not None
        )

    assert issued.credential is not None
    for profile in (HTTP, MCP):
        assert (
            await PostgresApplicationKeyVerifier(database).verify(
                issued.credential, profile=profile
            )
            is None
        )
        with pytest.raises(AuthenticationRequiredError):
            await ApplicationAuthenticationService(
                key_verifier=PostgresApplicationKeyVerifier(database),
                authentication_facts_reader=PostgresApplicationAuthenticationFactsReader(database),
                verification_profile=profile,
            ).authenticate(issued.credential)

    with pytest.raises(AccessDeniedError):
        async with database.session() as session:
            await deletion_service(session).delete(access=access, command=command, context=context)

    # This is an internal retained-reader contract, not post-retirement public authority.
    async with database.session() as session, session.begin():
        original = await PostgresApplicationAccountDeletionFactsReader(session).read_original(
            organization_id=issued.original.organization_id,
            project_id=metadata.project_id,
            actor_principal_id=access.actor_principal_id,
            operation_id=result.operation.operation_id,
        )
    assert original == result.original


def retirement_request(
    issued: ApplicationKeyIssueResultDTO, *, revision: int | None = None
) -> tuple[DeleteApplicationAccountCommand, IdempotencyContextDTO]:
    metadata = issued.original.metadata
    return (
        DeleteApplicationAccountCommand(
            metadata.project_id,
            metadata.application_principal_id,
            issued.original.access_revision if revision is None else revision,
        ),
        IdempotencyContextDTO(
            HttpMethod.DELETE,
            f"/v1/projects/{metadata.project_id.value}/application-accounts/{metadata.application_principal_id.value}",
            IdempotencyKey("retire-exact-original"),
        ),
    )


@dataclass(frozen=True, slots=True)
class RetirementEffects:
    status: PrincipalStatus
    revoked_at: datetime | None
    revision: int
    member: bool
    name_retired: bool
    targeting_actions: tuple[str, ...]
    reservation_ids: tuple[str, ...]
    original_ids: tuple[str, ...]
    audit_ids: tuple[UUID, ...]


async def retirement_effects(
    database: Database,
    issued: ApplicationKeyIssueResultDTO,
    context: IdempotencyContextDTO,
) -> RetirementEffects:
    """Observe the complete small fixture independently of the retirement adapters."""
    metadata = issued.original.metadata
    project, account = metadata.project_id.value, metadata.application_principal_id.value
    async with database.session() as session:
        principal = await session.get(PrincipalRow, account)
        key = await session.get(ApplicationKeyRow, metadata.key_id.value)
        project_row = await session.get(ProjectRow, project)
        assert principal is not None and key is not None and project_row is not None
        name = (
            await session.scalars(
                select(ApplicationAccountNameReservationRow).where(
                    ApplicationAccountNameReservationRow.project_id == project,
                    ApplicationAccountNameReservationRow.application_principal_id == account,
                )
            )
        ).one()
        return RetirementEffects(
            status=principal.status,
            revoked_at=key.revoked_at,
            revision=project_row.access_revision,
            member=await session.get(ProjectMembershipRow, (project, account)) is not None,
            name_retired=name.retired,
            targeting_actions=tuple(
                await session.scalars(
                    select(ApplicationActionGrantRow.action)
                    .where(
                        ApplicationActionGrantRow.project_id == project,
                        ApplicationActionGrantRow.application_principal_id == account,
                    )
                    .order_by(ApplicationActionGrantRow.action)
                )
            ),
            reservation_ids=tuple(
                await session.scalars(
                    select(IdempotencyReservationRow.operation_id)
                    .where(
                        IdempotencyReservationRow.project_id == project,
                        IdempotencyReservationRow.method == context.method.value,
                        IdempotencyReservationRow.requested_route == context.requested_route,
                        IdempotencyReservationRow.request_key == context.key.value,
                    )
                    .order_by(IdempotencyReservationRow.operation_id)
                )
            ),
            original_ids=tuple(
                await session.scalars(
                    select(ApplicationAccountDeletionResultRow.operation_id)
                    .where(
                        ApplicationAccountDeletionResultRow.project_id == project,
                        ApplicationAccountDeletionResultRow.application_principal_id == account,
                    )
                    .order_by(ApplicationAccountDeletionResultRow.operation_id)
                )
            ),
            audit_ids=tuple(
                await session.scalars(
                    select(AccessAuditEventRow.id)
                    .where(
                        AccessAuditEventRow.project_id == project,
                        AccessAuditEventRow.target_id == account,
                        AccessAuditEventRow.event_type == "application_account_retired",
                    )
                    .order_by(AccessAuditEventRow.id)
                )
            ),
        )


@pytest.mark.parametrize("failure", ["audit", "original", "before-commit", "cancellation"])
async def test_retirement_failure_rolls_back_the_entire_local_bundle(
    database: Database,
    retirement_scope: tuple[AccessContextDTO, ApplicationKeyIssueResultDTO],
    failure: str,
) -> None:
    access, issued = retirement_scope
    command, context = retirement_request(issued)
    before = await retirement_effects(database, issued, context)
    assert before.status is PrincipalStatus.ACTIVE and before.revoked_at is None
    assert before.member and not before.name_retired and before.targeting_actions
    assert before.reservation_ids == before.original_ids == before.audit_ids == ()

    def reject_flush(current: Session, _context: object, _instances: object) -> None:
        if any(
            (
                isinstance(row, AccessAuditEventRow)
                and row.event_type == "application_account_retired"
            )
            if failure == "audit"
            else isinstance(row, ApplicationAccountDeletionResultRow)
            for row in current.new
        ):
            raise RuntimeError("Controlled retirement persistence failure")

    def reject_commit(_session: Session) -> None:
        if failure == "cancellation":
            raise asyncio.CancelledError("Controlled retirement cancellation before COMMIT")
        raise RuntimeError("Controlled retirement failure before COMMIT")

    hook = "before_flush" if failure in ("audit", "original") else "before_commit"
    callback = reject_flush if failure in ("audit", "original") else reject_commit
    error = asyncio.CancelledError if failure == "cancellation" else RuntimeError
    async with database.session() as session:
        event.listen(session.sync_session, hook, callback)
        try:
            with pytest.raises(error, match="Controlled retirement"):
                await deletion_service(session).delete(
                    access=access, command=command, context=context
                )
        finally:
            event.remove(session.sync_session, hook, callback)
    assert await retirement_effects(database, issued, context) == before


async def test_lost_retirement_ack_denies_replay_and_preserves_the_actual_commit(
    database: Database,
    retirement_scope: tuple[AccessContextDTO, ApplicationKeyIssueResultDTO],
) -> None:
    """Lose the application acknowledgment after COMMIT and keep current denial authoritative."""
    access, issued = retirement_scope
    command, context = retirement_request(issued)
    before = await retirement_effects(database, issued, context)

    def lose_ack(_session: Session) -> None:
        raise RuntimeError("Controlled lost retirement COMMIT acknowledgment")

    async with database.session() as session:
        event.listen(session.sync_session, "after_commit", lose_ack)
        try:
            with pytest.raises(RuntimeError, match="lost retirement COMMIT acknowledgment"):
                await deletion_service(session).delete(
                    access=access, command=command, context=context
                )
        finally:
            event.remove(session.sync_session, "after_commit", lose_ack)

    committed = await retirement_effects(database, issued, context)
    assert committed.status is PrincipalStatus.RETIRED and committed.revoked_at is not None
    assert committed.revision == before.revision + 1
    assert committed.name_retired and not committed.member and not committed.targeting_actions
    assert committed.reservation_ids == committed.original_ids
    assert len(committed.original_ids) == len(committed.audit_ids) == 1
    async with database.session() as session:
        with pytest.raises(AccessDeniedError):
            await deletion_service(session).delete(access=access, command=command, context=context)

    evidence = access.authentication_evidence
    assert isinstance(evidence, HumanOAuthCredentialBindingDTO)
    async with database.session() as session, session.begin():
        version = await session.scalar(
            update(HumanCredentialVersionRow)
            .where(
                HumanCredentialVersionRow.installation_id == evidence.installation_id.value,
                HumanCredentialVersionRow.authority == evidence.identity.authority.value,
                HumanCredentialVersionRow.subject == evidence.identity.subject.value,
                HumanCredentialVersionRow.version == evidence.version.value,
            )
            .values(version=evidence.version.value + 1)
            .returning(HumanCredentialVersionRow.version)
        )
        assert version == evidence.version.value + 1
    async with database.session() as session:
        with pytest.raises(HumanOAuthCredentialRejectedError):
            await deletion_service(session).delete(access=access, command=command, context=context)
    assert await retirement_effects(database, issued, context) == committed


async def test_suspended_target_without_project_membership_can_be_retired(
    database: Database,
    retirement_scope: tuple[AccessContextDTO, ApplicationKeyIssueResultDTO],
) -> None:
    access, issued = retirement_scope
    command, context = retirement_request(issued)
    project, account = command.project_id.value, command.application_principal_id.value
    async with database.session() as session, session.begin():
        await session.execute(
            update(PrincipalRow)
            .where(PrincipalRow.id == account)
            .values(status=PrincipalStatus.SUSPENDED)
        )
        await session.execute(
            delete(ProjectMembershipRow).where(
                ProjectMembershipRow.project_id == project,
                ProjectMembershipRow.principal_id == account,
            )
        )
    before = await retirement_effects(database, issued, context)
    assert before.status is PrincipalStatus.SUSPENDED and not before.member
    async with database.session() as session:
        await deletion_service(session).delete(access=access, command=command, context=context)
    after = await retirement_effects(database, issued, context)
    assert after.status is PrincipalStatus.RETIRED and after.revoked_at is not None
    assert not after.member and after.revision == before.revision + 1
    assert after.reservation_ids == after.original_ids and len(after.original_ids) == 1


@pytest.mark.parametrize(
    "incoherent", ["actor", "account", "installation", "no-change", "jump", "overflow"]
)
async def test_persisted_retirement_original_rejects_incoherent_scope_or_revision(
    database: Database,
    retirement_scope: tuple[AccessContextDTO, ApplicationKeyIssueResultDTO],
    incoherent: str,
) -> None:
    access, issued = retirement_scope
    command, context = retirement_request(issued)
    async with database.session() as session:
        result = await deletion_service(session).delete(
            access=access, command=command, context=context
        )
    async with database.session() as session, session.begin():
        row = await session.get(
            ApplicationAccountDeletionResultRow, result.operation.operation_id.value
        )
        assert row is not None
        with pytest.raises(IntegrityError):
            async with session.begin_nested():
                if incoherent == "actor":
                    row.actor_principal_id = uuid4()
                elif incoherent == "account":
                    row.application_principal_id = uuid4()
                elif incoherent == "installation":
                    row.installation_id = uuid4()
                elif incoherent == "no-change":
                    row.access_revision = row.before_revision
                elif incoherent == "jump":
                    row.access_revision = row.before_revision + 2
                else:
                    row.access_revision = RevisionValidation.MAX_VALUE + 1
                await session.flush()


async def test_retirement_original_lifetime_follows_only_its_native_reservation(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
    retirement_scope: tuple[AccessContextDTO, ApplicationKeyIssueResultDTO],
) -> None:
    access, issued = retirement_scope
    command, context = retirement_request(issued)
    async with database.session() as session:
        result = await deletion_service(session).delete(
            access=access, command=command, context=context
        )
    operation_id = result.operation.operation_id
    config = Config(str(ALEMBIC_CONFIG_PATH))
    config.attributes["database_settings"] = temporary_postgres_settings
    with pytest.raises(RuntimeError, match="Retained application retirement originals"):
        alembic_command.downgrade(config, "0031_project_deletion")
    async with database.session() as session, session.begin():
        assert (
            await session.scalar(select(AlembicVersionRow.version_num))
            == "0033_stranded_authority_repair"
        )
        assert (
            await session.get(ApplicationAccountDeletionResultRow, operation_id.value) is not None
        )
        await session.execute(
            update(IdempotencyReservationRow)
            .where(IdempotencyReservationRow.operation_id == operation_id.value)
            .values(
                expires_at=func.clock_timestamp(type_=DateTime(timezone=True))
                - timedelta(seconds=1)
            )
        )
    async with database.session() as session, session.begin():
        assert (
            await PostgresApplicationAccountDeletionFactsReader(session).read_original(
                organization_id=issued.original.organization_id,
                project_id=command.project_id,
                actor_principal_id=access.actor_principal_id,
                operation_id=operation_id,
            )
            is None
        )
        assert (
            await session.get(ApplicationAccountDeletionResultRow, operation_id.value) is not None
        )
        # Model removal of this expired native reservation without invoking public retirement.
        removed = await session.scalar(
            delete(IdempotencyReservationRow)
            .where(
                IdempotencyReservationRow.operation_id == operation_id.value,
                IdempotencyReservationRow.expires_at <= func.clock_timestamp(),
            )
            .returning(IdempotencyReservationRow.operation_id)
        )
        assert removed == operation_id.value
    after = await retirement_effects(database, issued, context)
    assert after.original_ids == after.reservation_ids == ()
    assert after.status is PrincipalStatus.RETIRED and after.revoked_at is not None
    assert after.name_retired and not after.member and len(after.audit_ids) == 1
    async with database.session() as session:
        assert (
            await session.get(ApplicationKeyIssuanceResultRow, issued.original.operation_id.value)
            is not None
        )


async def test_retirement_removes_only_exact_received_access_and_preserves_project_work(
    database: Database,
    retirement_scope: tuple[AccessContextDTO, ApplicationKeyIssueResultDTO],
) -> None:
    access, issued = retirement_scope
    metadata = issued.original.metadata
    project, account = metadata.project_id, metadata.application_principal_id
    organization = issued.original.organization_id
    group = (await create_group(database, access, project, issued.original.access_revision)).group
    joined = await change_group(
        database,
        access,
        group,
        account,
        AccessGroupChangeKind.ADD_MEMBER,
        group.access_revision,
        "join-retirement-target",
    )
    other = (
        await create_account(
            database,
            access,
            project,
            joined.access_revision,
            name="unrelated-bot",
            key="create-unrelated-retirement-account",
        )
    ).account
    other_joined = await change_group(
        database,
        access,
        group,
        other.principal_id,
        AccessGroupChangeKind.ADD_MEMBER,
        other.access_revision,
        "join-unrelated-account",
    )
    async with database.session() as session:
        default = await upload_default_service(session).set(
            access=access,
            command=SetProjectUploadDefaultCommand(
                project,
                UploadAudience((group.group_id,)),
                other_joined.access_revision,
            ),
            context=upload_default_context(project, "keep-retirement-default"),
        )

    live_keys = [
        (
            await store_application_key(
                database,
                principal_id=account,
                organization_id=organization,
                project_id=project,
                issued_by=access.actor_principal_id,
                audience=profile.audience.value,
                adapters=(profile.adapter,),
            ),
            profile,
        )
        for profile in (HTTP, MCP)
    ]
    expired = await store_application_key(
        database,
        principal_id=account,
        organization_id=organization,
        project_id=project,
        issued_by=access.actor_principal_id,
    )
    previously_revoked = await store_application_key(
        database,
        principal_id=account,
        organization_id=organization,
        project_id=project,
        issued_by=access.actor_principal_id,
        audience=MCP.audience.value,
        adapters=(ApplicationKeyAdapter.MCP,),
    )
    other_key = await store_application_key(
        database,
        principal_id=other.principal_id,
        organization_id=organization,
        project_id=project,
        issued_by=access.actor_principal_id,
    )
    project_action = ProjectAction.INSPECT_BUDGET.value
    group_action = AccessGroupAction.ADD_DOCUMENTS.value
    async with database.session() as session, session.begin():
        now = await session.scalar(select(func.clock_timestamp(type_=DateTime(timezone=True))))
        assert now is not None
        previous_revocation = now - timedelta(days=1)
        await session.execute(
            update(ApplicationKeyRow)
            .where(ApplicationKeyRow.key_id == expired.key_id.value)
            .values(created_at=now - timedelta(days=3), expires_at=now - timedelta(days=2))
        )
        await session.execute(
            update(ApplicationKeyRow)
            .where(ApplicationKeyRow.key_id == previously_revoked.key_id.value)
            .values(
                created_at=now - timedelta(days=3),
                expires_at=now + timedelta(days=1),
                revoked_at=previous_revocation,
            )
        )
        # Controlled existing relationships isolate retirement effects from grant admission.
        for recipient in (account, other.principal_id):
            session.add(
                ProjectActionGrantRow(
                    project_id=project.value,
                    recipient_principal_id=recipient.value,
                    recipient_kind=PrincipalKind.APPLICATION,
                    action=project_action,
                    can_grant=False,
                    assigned_by_principal_id=access.actor_principal_id.value,
                )
            )
            session.add(
                GroupActionGrantRow(
                    project_id=project.value,
                    group_id=group.group_id.value,
                    recipient_principal_id=recipient.value,
                    recipient_kind=PrincipalKind.APPLICATION,
                    action=group_action,
                    can_grant=False,
                    assigned_by_principal_id=access.actor_principal_id.value,
                )
            )

    verifier = PostgresApplicationKeyVerifier(database)
    for credential, profile in live_keys:
        verified = await verifier.verify(credential, profile=profile)
        assert verified is not None and verified.principal_id == account
    verified_other = await verifier.verify(other_key, profile=HTTP)
    assert verified_other is not None and verified_other.principal_id == other.principal_id

    group_id = group.group_id.value
    target_member = (project.value, group_id, account.value)
    target_project_grant = (project.value, account.value, project_action)
    target_group_grant = (*target_member, group_action)
    async with database.session() as session:
        assert await session.get(GroupMembershipRow, target_member) is not None
        assert await session.get(ProjectActionGrantRow, target_project_grant) is not None
        assert await session.get(GroupActionGrantRow, target_group_grant) is not None
        assert (
            await session.get(ProjectUploadDefaultGroupRow, (project.value, group_id)) is not None
        )
        account_original = (
            await session.scalars(
                select(ApplicationAccountCreationResultRow).where(
                    ApplicationAccountCreationResultRow.principal_id == account.value
                )
            )
        ).one()
        saved_creation = (
            account_original.operation_id,
            account_original.name,
            account_original.creator_principal_id,
            account_original.access_revision,
        )
        project_row = await session.get(ProjectRow, project.value)
        assert project_row is not None and project_row.status is ProjectStatus.ACTIVE
        project_metadata = (
            project_row.resource_name,
            project_row.name,
            project_row.metadata_revision,
        )

    command, context = retirement_request(issued, revision=default.default.access_revision)
    async with database.session() as session:
        result = await deletion_service(session).delete(
            access=access, command=command, context=context
        )
    assert result.original.access_revision == command.expected_access_revision + 1

    async with database.session() as session:
        assert await session.get(GroupMembershipRow, target_member) is None
        assert await session.get(ProjectActionGrantRow, target_project_grant) is None
        assert await session.get(GroupActionGrantRow, target_group_grant) is None
        assert await session.get(ProjectMembershipRow, (project.value, account.value)) is None
        other_member = (project.value, group_id, other.principal_id.value)
        assert await session.get(GroupMembershipRow, other_member) is not None
        assert (
            await session.get(
                ProjectActionGrantRow, (project.value, other.principal_id.value, project_action)
            )
            is not None
        )
        assert await session.get(GroupActionGrantRow, (*other_member, group_action)) is not None
        assert (
            await session.get(
                GroupManagerRow, (project.value, group_id, access.actor_principal_id.value)
            )
            is not None
        )
        assert await session.get(AccessGroupRow, group_id) is not None
        assert (
            await session.get(ProjectUploadDefaultGroupRow, (project.value, group_id)) is not None
        )
        default_original = await session.get(
            ProjectUploadDefaultResultRow, default.operation.operation_id.value
        )
        assert default_original is not None and default_original.group_ids == [group_id]
        project_row = await session.get(ProjectRow, project.value)
        assert project_row is not None and project_row.status is ProjectStatus.ACTIVE
        assert (
            project_row.resource_name,
            project_row.name,
            project_row.metadata_revision,
        ) == project_metadata
        original = await session.get(ApplicationAccountCreationResultRow, saved_creation[0])
        assert original is not None
        assert (
            original.operation_id,
            original.name,
            original.creator_principal_id,
            original.access_revision,
        ) == saved_creation
        name = await session.get(
            ApplicationAccountNameReservationRow, (project.value, saved_creation[1])
        )
        assert name is not None and name.retired and name.application_principal_id == account.value
        keys = {
            row.key_id: row
            for row in await session.scalars(
                select(ApplicationKeyRow).where(
                    ApplicationKeyRow.application_principal_id == account.value
                )
            )
        }
        assert set(keys) == {
            metadata.key_id.value,
            expired.key_id.value,
            previously_revoked.key_id.value,
            *(credential.key_id.value for credential, _ in live_keys),
        }
        assert all(row.revoked_at is not None for row in keys.values())
        assert all(
            row.issued_by_principal_id == access.actor_principal_id.value for row in keys.values()
        )
        assert keys[previously_revoked.key_id.value].revoked_at == previous_revocation
        expired_row = keys[expired.key_id.value]
        assert (
            expired_row.revoked_at is not None and expired_row.revoked_at > expired_row.expires_at
        )

    for credential, profile in live_keys:
        assert await verifier.verify(credential, profile=profile) is None
    verified_other = await verifier.verify(other_key, profile=HTTP)
    assert verified_other is not None and verified_other.principal_id == other.principal_id
    with pytest.raises(ConflictError):
        await create_account(
            database,
            access,
            project,
            result.original.access_revision,
            name=saved_creation[1],
            key="retired-name-reuse",
        )


async def wait_for_retirement_race_lock(database: Database) -> None:
    """Observe real lock contention in the isolated test database before releasing the winner."""
    pid, name = column("pid", Integer), column("datname", String)
    activity = table("pg_stat_activity", pid, name)
    async with asyncio.timeout(3):
        while True:
            async with database.session() as observer:
                blocked = await observer.scalar(
                    select(pid)
                    .select_from(activity)
                    .where(
                        name == func.current_database(type_=String()),
                        func.cardinality(func.pg_blocking_pids(pid, type_=ARRAY(Integer))) > 0,
                    )
                )
            if blocked is not None:
                return
            await asyncio.sleep(0.01)


@pytest_asyncio.fixture
async def browser_retirement_scope(
    database: Database,
) -> tuple[AccessContextDTO, ApplicationKeyIssueResultDTO]:
    """Reuse issuance's captured Browser evidence and verify the stored actor facts."""
    access, issued = await issue_application_key(
        database, adapters=(ApplicationKeyAdapter.HTTP, ApplicationKeyAdapter.MCP)
    )
    evidence = access.authentication_evidence
    assert isinstance(evidence, BrowserSessionAuthenticationDTO)
    command, _ = retirement_request(issued)
    async with database.session() as session, session.begin():
        facts = await PostgresApplicationAccountDeletionFactsReader(session).lock_for_deletion(
            access=access, command=command
        )
        assert facts is not None
        assert facts.installation_id == evidence.installation_id
        assert facts.actor.principal.id == access.actor_principal_id
        credential = facts.actor.oauth_credential_facts
        assert credential is not None and credential.binding_matches_actor
        assert credential.current_version == evidence.version
        ActionAuthorizationService.require_authorization_from_facts(
            access=access, facts=facts.actor
        )
    return access, issued


async def test_current_stored_browser_can_retire_application_account(
    database: Database,
    browser_retirement_scope: tuple[AccessContextDTO, ApplicationKeyIssueResultDTO],
) -> None:
    access, issued = browser_retirement_scope
    command, context = retirement_request(issued)
    before = await retirement_effects(database, issued, context)
    assert before.status is PrincipalStatus.ACTIVE and before.revoked_at is None
    assert before.member and not before.name_retired and before.targeting_actions
    assert before.revision == command.expected_access_revision
    assert not before.reservation_ids and not before.original_ids and not before.audit_ids

    async with database.session() as session:
        result = await deletion_service(session).delete(
            access=access, command=command, context=context
        )

    after = await retirement_effects(database, issued, context)
    assert result.original.actor_principal_id == access.actor_principal_id
    assert result.original.project_id == command.project_id
    assert result.original.application_principal_id == command.application_principal_id
    assert result.original.access_revision == after.revision == before.revision + 1
    assert after.status is PrincipalStatus.RETIRED and after.revoked_at is not None
    assert not after.member and after.name_retired and not after.targeting_actions
    assert after.reservation_ids == after.original_ids == (result.original.operation_id.value,)
    assert len(after.audit_ids) == 1


async def test_browser_version_changed_during_retirement_lock_wait_denies_before_reservation(
    database: Database,
    browser_retirement_scope: tuple[AccessContextDTO, ApplicationKeyIssueResultDTO],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    access, issued = browser_retirement_scope
    evidence = access.authentication_evidence
    assert isinstance(evidence, BrowserSessionAuthenticationDTO)
    command, context = retirement_request(issued)
    before = await retirement_effects(database, issued, context)
    assert not before.reservation_ids and not before.original_ids and not before.audit_ids
    reserve = AsyncMock(side_effect=AssertionError("Stale Browser evidence must not reserve."))
    monkeypatch.setattr(IdempotencyService, "reserve_or_recover", reserve)

    async def retire() -> None:
        async with database.session() as session:
            with pytest.raises(AuthenticationRequiredError) as rejected:
                await deletion_service(session).delete(
                    access=access, command=command, context=context
                )
        assert rejected.type is AuthenticationRequiredError

    credential_key = (
        evidence.installation_id.value,
        evidence.identity.authority.value,
        evidence.identity.subject.value,
    )
    retirement: asyncio.Task[None] | None = None
    primary: BaseException | None = None
    try:
        async with database.session() as holder, holder.begin():
            locked = await holder.scalar(
                select(ProjectRow.id)
                .where(ProjectRow.id == command.project_id.value)
                .with_for_update()
            )
            assert locked == command.project_id.value
            version = await holder.get(HumanCredentialVersionRow, credential_key)
            assert version is not None and version.version == evidence.version.value
            retirement = asyncio.create_task(retire())
            await wait_for_retirement_race_lock(database)
            assert not retirement.done()
            version.version += 1
        async with asyncio.timeout(3):
            await asyncio.shield(retirement)
    except BaseException as error:
        primary = error
        raise
    finally:
        if retirement is not None:
            if not retirement.done():
                retirement.cancel()
            try:
                async with asyncio.timeout(3):
                    (outcome,) = await asyncio.shield(
                        asyncio.gather(retirement, return_exceptions=True)
                    )
                if (
                    isinstance(outcome, BaseException)
                    and not isinstance(outcome, asyncio.CancelledError)
                    and outcome is not primary
                ):
                    raise outcome
            except BaseException as settlement_error:
                if settlement_error is not primary:
                    raise BaseExceptionGroup(
                        "Browser retirement and task settlement failed",
                        ([primary] if primary is not None else []) + [settlement_error],
                    ) from None

    reserve.assert_not_awaited()
    async with database.session() as session:
        version = await session.get(HumanCredentialVersionRow, credential_key)
        assert version is not None and version.version == evidence.version.value + 1
    assert await retirement_effects(database, issued, context) == before


@pytest.mark.parametrize(
    "retirement_first", [True, False], ids=["retirement-wins", "issuance-wins"]
)
async def test_real_issuance_and_retirement_share_the_reviewed_revision(
    database: Database,
    retirement_scope: tuple[AccessContextDTO, ApplicationKeyIssueResultDTO],
    monkeypatch: pytest.MonkeyPatch,
    retirement_first: bool,
) -> None:
    access, issued = retirement_scope
    command, context = retirement_request(issued)
    saved, release = asyncio.Event(), asyncio.Event()
    issue_original = PostgresApplicationKeyIssuanceWriter.create
    retire_original = PostgresApplicationAccountDeletionWriter.save

    async def hold_issuance(
        writer: PostgresApplicationKeyIssuanceWriter,
        *,
        key: ApplicationKeyCreationDTO,
        expected_project_revision: int,
    ) -> None:
        await issue_original(writer, key=key, expected_project_revision=expected_project_revision)
        saved.set()
        await release.wait()

    async def hold_retirement(
        writer: PostgresApplicationAccountDeletionWriter,
        *,
        original: ApplicationAccountDeletionRecordDTO,
        expected_project_revision: int,
        checked_at: datetime,
    ) -> None:
        await retire_original(
            writer,
            original=original,
            expected_project_revision=expected_project_revision,
            checked_at=checked_at,
        )
        saved.set()
        await release.wait()

    if retirement_first:
        monkeypatch.setattr(PostgresApplicationAccountDeletionWriter, "save", hold_retirement)
    else:
        monkeypatch.setattr(PostgresApplicationKeyIssuanceWriter, "create", hold_issuance)

    async def issue() -> ApplicationKeyIssueResultDTO | None:
        try:
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
                    access=access,
                    command=IssueApplicationKeyCommand(
                        command.project_id,
                        command.application_principal_id,
                        (ApplicationKeyAdapter.HTTP,),
                        command.expected_access_revision,
                    ),
                    context=IdempotencyContextDTO(
                        HttpMethod.POST,
                        context.requested_route + "/keys",
                        IdempotencyKey("issue-racing-retirement"),
                    ),
                )
        except AccessDeniedError:
            if not retirement_first:
                raise
            return None

    async def retire() -> ApplicationAccountDeletionResultDTO | None:
        try:
            async with database.session() as session:
                return await deletion_service(session).delete(
                    access=access, command=command, context=context
                )
        except StaleRevisionError:
            if retirement_first:
                raise
            return None

    issuance: asyncio.Task[ApplicationKeyIssueResultDTO | None] | None = None
    retirement: asyncio.Task[ApplicationAccountDeletionResultDTO | None] | None = None
    primary: BaseException | None = None
    try:
        if retirement_first:
            retirement = asyncio.create_task(retire())
        else:
            issuance = asyncio.create_task(issue())
        async with asyncio.timeout(3):
            await saved.wait()
        if retirement_first:
            issuance = asyncio.create_task(issue())
        else:
            retirement = asyncio.create_task(retire())
        await wait_for_retirement_race_lock(database)
        release.set()
        assert issuance is not None and retirement is not None
        async with asyncio.timeout(3):
            new_key = await asyncio.shield(issuance)
            retired = await asyncio.shield(retirement)
    except BaseException as error:
        primary = error
        raise
    finally:
        release.set()
        for task in (issuance, retirement):
            if task is not None and not task.done():
                task.cancel()
        cleanup_errors: list[BaseException] = []
        try:
            async with asyncio.timeout(3):
                if issuance is not None and retirement is not None:
                    outcomes = await asyncio.shield(
                        asyncio.gather(issuance, retirement, return_exceptions=True)
                    )
                elif issuance is not None:
                    outcomes = await asyncio.shield(
                        asyncio.gather(issuance, return_exceptions=True)
                    )
                elif retirement is not None:
                    outcomes = await asyncio.shield(
                        asyncio.gather(retirement, return_exceptions=True)
                    )
                else:
                    outcomes = ()
            for outcome in outcomes:
                if (
                    isinstance(outcome, BaseException)
                    and not isinstance(outcome, asyncio.CancelledError)
                    and outcome is not primary
                ):
                    cleanup_errors.append(outcome)
        except BaseException as error:
            if error is not primary:
                cleanup_errors.append(error)
        if cleanup_errors:
            raise BaseExceptionGroup(
                "Issuance/retirement work and task settlement failed",
                ([primary] if primary is not None else []) + cleanup_errors,
            ) from None

    after = await retirement_effects(database, issued, context)
    assert after.revision == command.expected_access_revision + 1
    if retirement_first:
        assert retired is not None and new_key is None
        assert after.status is PrincipalStatus.RETIRED and after.revoked_at is not None
        async with database.session() as session:
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(ApplicationKeyRow)
                    .where(
                        ApplicationKeyRow.application_principal_id
                        == command.application_principal_id.value
                    )
                )
                == 1
            )
        return

    assert retired is None and new_key is not None and new_key.credential is not None
    assert after.status is PrincipalStatus.ACTIVE and after.revoked_at is None
    assert after.reservation_ids == after.original_ids == after.audit_ids == ()
    verifier = PostgresApplicationKeyVerifier(database)
    assert await verifier.verify(new_key.credential, profile=HTTP) is not None

    # A new, explicitly reviewed intent follows the known stale rejection.
    reviewed, _ = retirement_request(issued, revision=new_key.original.access_revision)
    fresh_context = replace(context, key=IdempotencyKey("retire-reviewed-after-issuance"))
    async with database.session() as session:
        await deletion_service(session).delete(
            access=access, command=reviewed, context=fresh_context
        )
    assert await verifier.verify(new_key.credential, profile=HTTP) is None


@pytest.mark.parametrize("mutation", ["grant", "membership"])
@pytest.mark.parametrize(
    "retirement_first", [True, False], ids=["retirement-wins", "mutation-wins"]
)
async def test_retirement_and_real_access_mutation_share_the_reviewed_revision(
    database: Database,
    retirement_scope: tuple[AccessContextDTO, ApplicationKeyIssueResultDTO],
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
    retirement_first: bool,
) -> None:
    access, issued = retirement_scope
    metadata = issued.original.metadata
    project, account = metadata.project_id, metadata.application_principal_id
    action = ActionId(ProjectAction.INSPECT_BUDGET.value)
    group = (
        (await create_group(database, access, project, issued.original.access_revision)).group
        if mutation == "membership"
        else None
    )
    revision = issued.original.access_revision if group is None else group.access_revision
    command, context = retirement_request(issued, revision=revision)
    mutation_key = "access-mutation-racing-retirement"
    mutation_route = (
        f"/v1/projects/{project.value}/grants/{account.value}/{action.value}"
        if group is None
        else f"/v1/projects/{project.value}/access-groups/{group.group_id.value}/members/{account.value}"
    )

    async def change(reviewed_revision: int, key: str) -> tuple[int, OperationId]:
        if group is not None:
            membership = await change_group(
                database,
                access,
                group,
                account,
                AccessGroupChangeKind.ADD_MEMBER,
                reviewed_revision,
                key,
            )
            assert membership.changed
            return membership.access_revision, membership.operation.operation_id
        async with database.session() as session:
            grant = await create_project_grant_change_service(session).set_action_grant(
                access=access,
                command=SetProjectActionGrantCommand(
                    project, account, action, False, reviewed_revision
                ),
                context=IdempotencyContextDTO(HttpMethod.PUT, mutation_route, IdempotencyKey(key)),
            )
        assert grant.changed
        return grant.access_revision, grant.operation.operation_id

    async def observed_mutation() -> tuple[bool, tuple[tuple[str, OperationReservationState], ...]]:
        async with database.session() as session:
            present = (
                await session.get(
                    ProjectActionGrantRow, (project.value, account.value, action.value)
                )
                if group is None
                else await session.get(
                    GroupMembershipRow, (project.value, group.group_id.value, account.value)
                )
            ) is not None
            reservations = (
                (
                    await session.execute(
                        select(
                            IdempotencyReservationRow.operation_id, IdempotencyReservationRow.state
                        )
                        .where(
                            IdempotencyReservationRow.project_id == project.value,
                            IdempotencyReservationRow.principal_id
                            == access.actor_principal_id.value,
                            IdempotencyReservationRow.method == HttpMethod.PUT.value,
                            IdempotencyReservationRow.requested_route == mutation_route,
                        )
                        .order_by(IdempotencyReservationRow.operation_id)
                    )
                )
                .tuples()
                .all()
            )
        return present, tuple((operation_id, state) for operation_id, state in reservations)

    before = await retirement_effects(database, issued, context)
    assert before.revision == revision and before.member and before.revoked_at is None
    assert before.status is PrincipalStatus.ACTIVE and before.targeting_actions
    assert await observed_mutation() == (False, ())
    saved, release = asyncio.Event(), asyncio.Event()
    original_completion = IdempotencyService.record_completed_result

    async def hold_first_completion(
        service: IdempotencyService,
        operation: NewOperationReservationDTO,
        *,
        replay_kind: OperationReplayKind,
    ) -> CompletedSynchronousOperationDTO | AcceptedAsyncOperationDTO:
        completed = await original_completion(service, operation, replay_kind=replay_kind)
        if not saved.is_set():
            saved.set()
            await release.wait()
        return completed

    monkeypatch.setattr(IdempotencyService, "record_completed_result", hold_first_completion)

    async def contend_mutation() -> tuple[int, OperationId] | None:
        try:
            return await change(revision, mutation_key)
        except StaleRevisionError:
            if not retirement_first:
                raise
            return None

    async def contend_retirement() -> tuple[int, OperationId] | None:
        try:
            async with database.session() as session:
                result = await deletion_service(session).delete(
                    access=access, command=command, context=context
                )
            return result.original.access_revision, result.operation.operation_id
        except StaleRevisionError:
            if retirement_first:
                raise
            return None

    tasks: list[asyncio.Task[tuple[int, OperationId] | None]] = []
    primary: BaseException | None = None
    try:
        first = asyncio.create_task(
            contend_retirement() if retirement_first else contend_mutation()
        )
        tasks.append(first)
        async with asyncio.timeout(3):
            await saved.wait()
        second = asyncio.create_task(
            contend_mutation() if retirement_first else contend_retirement()
        )
        tasks.append(second)
        await wait_for_retirement_race_lock(database)
        release.set()
        async with asyncio.timeout(3):
            winning = await asyncio.shield(first)
            losing = await asyncio.shield(second)
    except BaseException as error:
        primary = error
        raise
    finally:
        release.set()
        for task in tasks:
            if not task.done():
                task.cancel()
        cleanup_errors: list[BaseException] = []
        try:
            async with asyncio.timeout(3):
                outcomes = await asyncio.shield(asyncio.gather(*tasks, return_exceptions=True))
            for outcome in outcomes:
                if (
                    isinstance(outcome, BaseException)
                    and not isinstance(outcome, asyncio.CancelledError)
                    and outcome is not primary
                ):
                    cleanup_errors.append(outcome)
        except BaseException as error:
            if error is not primary:
                cleanup_errors.append(error)
        if cleanup_errors:
            raise BaseExceptionGroup(
                "Access mutation and retirement task settlement failed",
                ([primary] if primary is not None else []) + cleanup_errors,
            ) from None

    assert winning is not None and losing is None and winning[0] == revision + 1
    after_race = await retirement_effects(database, issued, context)
    assert after_race.revision == winning[0]
    if retirement_first:
        assert after_race.status is PrincipalStatus.RETIRED and after_race.revoked_at is not None
        assert after_race.reservation_ids == after_race.original_ids == (winning[1].value,)
        assert await observed_mutation() == (False, ())
        expected = (
            "The recipient is not currently eligible for assignment."
            if group is None
            else "The recipient is not an eligible current Project member."
        )
        with pytest.raises(ConflictError, match=expected):
            await change(winning[0], "explicitly-reviewed-retired-recipient")
        assert await observed_mutation() == (False, ())
        assert await retirement_effects(database, issued, context) == after_race
        return

    assert after_race.status is PrincipalStatus.ACTIVE and after_race.revoked_at is None
    assert after_race.reservation_ids == after_race.original_ids == after_race.audit_ids == ()
    mutation_original = ((winning[1].value, OperationReservationState.REPLAYABLE),)
    assert await observed_mutation() == (True, mutation_original)
    reviewed = replace(command, expected_access_revision=winning[0])
    fresh_context = replace(context, key=IdempotencyKey("retire-after-reviewed-access-mutation"))
    async with database.session() as session:
        retired = await deletion_service(session).delete(
            access=access, command=reviewed, context=fresh_context
        )
    assert retired.original.access_revision == revision + 2
    assert await observed_mutation() == (False, mutation_original)
    assert await change(revision, mutation_key) == winning
    assert await observed_mutation() == (False, mutation_original)
    after_replay = await retirement_effects(database, issued, fresh_context)
    assert after_replay.revision == retired.original.access_revision
    assert after_replay.status is PrincipalStatus.RETIRED and after_replay.revoked_at is not None


async def test_foreign_project_account_is_hidden_without_waiting_on_its_project(
    database: Database,
    retirement_scope: tuple[AccessContextDTO, ApplicationKeyIssueResultDTO],
) -> None:
    access, issued = retirement_scope
    command, context = retirement_request(issued)
    organization = issued.original.organization_id
    evidence = access.authentication_evidence
    assert isinstance(evidence, HumanOAuthCredentialBindingDTO)
    async with database.session() as session:
        organization_revision = await session.scalar(
            select(OrganizationRow.access_revision).where(OrganizationRow.id == organization.value)
        )
    assert organization_revision is not None
    other_project = (
        await create_project(
            database,
            ProjectCreationSeedDTO(access, organization, organization_revision, evidence),
            name="retirement-control-project",
            key="create-retirement-control-project",
        )
    ).project
    assert other_project.project_id != command.project_id
    other = (
        await create_account(
            database,
            access,
            other_project.project_id,
            other_project.access_revision,
            name="support-bot",
            key="create-cross-project-control-account",
        )
    ).account
    other_key = await store_application_key(
        database,
        principal_id=other.principal_id,
        organization_id=organization,
        project_id=other.project_id,
        issued_by=access.actor_principal_id,
    )
    verifier = PostgresApplicationKeyVerifier(database)
    before_other = await verifier.verify(other_key, profile=HTTP)
    assert before_other is not None and before_other.principal_id == other.principal_id
    before = await retirement_effects(database, issued, context)
    wrong = DeleteApplicationAccountCommand(
        other.project_id, command.application_principal_id, other.access_revision
    )
    wrong_context = IdempotencyContextDTO(
        HttpMethod.DELETE,
        f"/v1/projects/{wrong.project_id.value}/application-accounts/{wrong.application_principal_id.value}",
        IdempotencyKey("wrong-project-retirement"),
    )
    async with database.session() as holder, holder.begin():
        locked = await holder.scalar(
            select(ProjectRow.id).where(ProjectRow.id == command.project_id.value).with_for_update()
        )
        assert locked == command.project_id.value
        async with asyncio.timeout(3), database.session() as session:
            with pytest.raises(ResourceNotFoundError):
                await deletion_service(session).delete(
                    access=access, command=wrong, context=wrong_context
                )
    assert await retirement_effects(database, issued, context) == before
    async with database.session() as session:
        assert (
            await session.scalar(
                select(IdempotencyReservationRow.operation_id).where(
                    IdempotencyReservationRow.project_id == wrong.project_id.value,
                    IdempotencyReservationRow.requested_route == wrong_context.requested_route,
                    IdempotencyReservationRow.request_key == wrong_context.key.value,
                )
            )
            is None
        )
    async with database.session() as session:
        result = await deletion_service(session).delete(
            access=access, command=command, context=context
        )
    assert result.original.project_id == command.project_id

    async with database.session() as session:
        principal = await session.get(PrincipalRow, other.principal_id.value)
        row = await session.get(ProjectRow, other.project_id.value)
        name = await session.get(
            ApplicationAccountNameReservationRow, (other.project_id.value, other.name.value)
        )
        assert principal is not None and principal.status is PrincipalStatus.ACTIVE
        assert row is not None and row.status is ProjectStatus.ACTIVE
        assert row.access_revision == other.access_revision
        assert name is not None and not name.retired
        assert name.application_principal_id == other.principal_id.value
        assert (
            await session.get(
                ProjectMembershipRow, (other.project_id.value, other.principal_id.value)
            )
            is not None
        )
    after_other = await verifier.verify(other_key, profile=HTTP)
    assert after_other is not None and after_other.principal_id == before_other.principal_id
