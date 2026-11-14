"""Qualify digest-only intent and its independent invitation lifetime with PostgreSQL."""

import asyncio
import json
import os
from contextlib import ExitStack
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import HttpUrl
from sqlalchemy import Connection, DateTime, Integer, delete, event, func, select, update
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import ORMExecuteState, Session, SessionTransaction
from tests.support.access_group_scenarios import create_group, delete_group
from tests.support.application_account_scenarios import create_account
from tests.support.application_key_scenarios import store_application_key
from tests.support.project_action_grant_postgres_scenarios import change_project_grant
from tests.support.project_creation_scenarios import (
    ProjectCreationSeedDTO,
    create_project,
    seed_project_creator,
)
from tests.support.project_membership_postgres_scenarios import (
    MembershipProjectSeedDTO,
    change_membership,
    seed_membership_project,
)

from inframeld_backend.access.application.commands.activate_invitation_command import (
    ActivateInvitationCommand,
)
from inframeld_backend.access.application.commands.change_access_group_relationship_command import (
    ChangeAccessGroupRelationshipCommand,
)
from inframeld_backend.access.application.commands.change_model_connection_grant_command import (
    ChangeModelConnectionGrantCommand,
)
from inframeld_backend.access.application.commands.create_model_connection_command import (
    CreateModelConnectionCommand,
)
from inframeld_backend.access.application.commands.issue_invitation_command import (
    IssueInvitationCommand,
)
from inframeld_backend.access.application.commands.remove_organization_action_grant_command import (
    RemoveOrganizationActionGrantCommand,
)
from inframeld_backend.access.application.commands.revoke_invitation_command import (
    RevokeInvitationCommand,
)
from inframeld_backend.access.application.commands.set_access_group_action_grant_command import (
    SetAccessGroupActionGrantCommand,
)
from inframeld_backend.access.application.commands.set_organization_action_grant_command import (
    SetOrganizationActionGrantCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.access_group_change_facts_dto import (
    AccessGroupChangeFactsDTO,
)
from inframeld_backend.access.application.dtos.access_group_grant_management_facts_dto import (
    AccessGroupGrantManagementFactsDTO,
)
from inframeld_backend.access.application.dtos.access_group_grant_target_dto import (
    AccessGroupGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.application_account_grant_management_facts_dto import (
    ApplicationAccountGrantManagementFactsDTO,
)
from inframeld_backend.access.application.dtos.application_account_grant_target_dto import (
    ApplicationAccountGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.created_project_dto import CreatedProjectDTO
from inframeld_backend.access.application.dtos.identity_recovery_event_dto import (
    IdentityRecoveryEventDTO,
)
from inframeld_backend.access.application.dtos.invitation_action_grant_intent_dto import (
    InvitationActionGrantIntentDTO,
)
from inframeld_backend.access.application.dtos.invitation_activation_binding_dto import (
    InvitationActivationBindingDTO,
)
from inframeld_backend.access.application.dtos.invitation_activation_facts_dto import (
    InvitationActivationFactsDTO,
)
from inframeld_backend.access.application.dtos.invitation_activation_result_dto import (
    InvitationActivationResultDTO,
)
from inframeld_backend.access.application.dtos.invitation_admission_only_intent_dto import (
    InvitationAdmissionOnlyIntentDTO,
)
from inframeld_backend.access.application.dtos.invitation_assignment_dto import (
    InvitationAssignmentDTO,
)
from inframeld_backend.access.application.dtos.invitation_browser_proof_dto import (
    InvitationBrowserProofDTO,
)
from inframeld_backend.access.application.dtos.invitation_facts_dto import InvitationFactsDTO
from inframeld_backend.access.application.dtos.invitation_group_manager_intent_dto import (
    InvitationGroupManagerIntentDTO,
)
from inframeld_backend.access.application.dtos.invitation_group_membership_intent_dto import (
    InvitationGroupMembershipIntentDTO,
)
from inframeld_backend.access.application.dtos.invitation_model_connection_target_dto import (
    InvitationModelConnectionTargetDTO,
)
from inframeld_backend.access.application.dtos.invitation_project_access_revision_dto import (
    InvitationProjectAccessRevisionDTO,
)
from inframeld_backend.access.application.dtos.invitation_project_membership_intent_dto import (
    InvitationProjectMembershipIntentDTO,
)
from inframeld_backend.access.application.dtos.invitation_record_dto import InvitationRecordDTO
from inframeld_backend.access.application.dtos.invitation_revocation_result_dto import (
    InvitationRevocationResultDTO,
)
from inframeld_backend.access.application.dtos.model_connection_access_dto import (
    ModelConnectionAccessDTO,
)
from inframeld_backend.access.application.dtos.organization_grant_management_facts_dto import (
    OrganizationGrantManagementFactsDTO,
)
from inframeld_backend.access.application.dtos.organization_grant_target_dto import (
    OrganizationGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.project_grant_target_dto import ProjectGrantTargetDTO
from inframeld_backend.access.application.dtos.project_membership_change_facts_dto import (
    ProjectMembershipChangeFactsDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.enums.access_group_change_kind import (
    AccessGroupChangeKind,
)
from inframeld_backend.access.application.enums.identity_recovery_event_kind import (
    IdentityRecoveryEventKind,
)
from inframeld_backend.access.application.errors.human_oauth_credential_rejected_error import (
    HumanOAuthCredentialRejectedError,
)
from inframeld_backend.access.application.queries.preview_invitation_query import (
    PreviewInvitationQuery,
)
from inframeld_backend.access.application.services.identity_recovery_admission_service import (
    IdentityRecoveryAdmissionService,
)
from inframeld_backend.access.application.services.invitation_activation_service import (
    InvitationActivationService,
)
from inframeld_backend.access.application.services.invitation_administration_service import (
    InvitationAdministrationService,
)
from inframeld_backend.access.application.services.invitation_assignment_service import (
    InvitationAssignmentService,
)
from inframeld_backend.access.application.services.invitation_fingerprint_service import (
    InvitationFingerprintService,
)
from inframeld_backend.access.application.services.invitation_preview_service import (
    InvitationPreviewService,
)
from inframeld_backend.access.application.services.principal_access_evaluation_service import (
    PrincipalAccessEvaluationService,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.identity_recovery_cleanup_state import (
    IdentityRecoveryCleanupState,
)
from inframeld_backend.access.domain.enums.model_connection_action import ModelConnectionAction
from inframeld_backend.access.domain.enums.model_connection_authentication import (
    ModelConnectionAuthentication,
)
from inframeld_backend.access.domain.enums.model_connection_provider import ModelConnectionProvider
from inframeld_backend.access.domain.enums.organization_action import OrganizationAction
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.policies.access_group_relationship_policy import (
    AccessGroupRelationshipPolicy,
)
from inframeld_backend.access.domain.policies.human_admission_policy import HumanAdmissionPolicy
from inframeld_backend.access.domain.policies.invitation_policy import InvitationPolicy
from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
from inframeld_backend.access.domain.value_objects.action_grant_state import ActionGrantState
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.identity_recovery_flow_id import (
    IdentityRecoveryFlowId,
)
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.domain.value_objects.invitation_id import InvitationId
from inframeld_backend.access.domain.value_objects.invitation_token import InvitationToken
from inframeld_backend.access.domain.value_objects.invitation_token_digest import (
    InvitationTokenDigest,
)
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.mappers.postgres_invitation_mapper import (
    PostgresInvitationMapper,
)
from inframeld_backend.access.infrastructure.readers.postgres_access_group_facts_reader import (
    PostgresAccessGroupFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_access_group_grant_management_facts_reader import (
    PostgresAccessGroupGrantManagementFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_application_account_grant_management_facts_reader import (
    PostgresApplicationAccountGrantManagementFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_human_admission_facts_reader import (
    PostgresHumanAdmissionFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_invitation_assignment_facts_reader import (
    PostgresInvitationAssignmentFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_invitation_binding_reader import (
    PostgresInvitationBindingReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_invitation_facts_reader import (
    PostgresInvitationFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_organization_access_facts_reader import (
    PostgresOrganizationAccessFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_organization_grant_management_facts_reader import (
    PostgresOrganizationGrantManagementFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_project_membership_change_facts_reader import (
    PostgresProjectMembershipChangeFactsReader,
)
from inframeld_backend.access.infrastructure.repositories.postgres_project_membership_repository import (
    PostgresProjectMembershipRepository,
)
from inframeld_backend.access.infrastructure.resources.postgres_identity_coordinator import (
    PostgresIdentityCoordinator,
)
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.access.infrastructure.rows.access_group_row import AccessGroupRow
from inframeld_backend.access.infrastructure.rows.application_account_row import (
    ApplicationAccountRow,
)
from inframeld_backend.access.infrastructure.rows.application_action_grant_row import (
    ApplicationActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.group_action_grant_row import GroupActionGrantRow
from inframeld_backend.access.infrastructure.rows.group_manager_row import GroupManagerRow
from inframeld_backend.access.infrastructure.rows.group_membership_row import GroupMembershipRow
from inframeld_backend.access.infrastructure.rows.human_credential_version_row import (
    HumanCredentialVersionRow,
)
from inframeld_backend.access.infrastructure.rows.human_identity_link_row import (
    HumanIdentityLinkRow,
)
from inframeld_backend.access.infrastructure.rows.identity_recovery_admission_row import (
    IdentityRecoveryAdmissionRow,
)
from inframeld_backend.access.infrastructure.rows.invitation_activation_operation_row import (
    InvitationActivationOperationRow,
)
from inframeld_backend.access.infrastructure.rows.invitation_revocation_result_row import (
    InvitationRevocationResultRow,
)
from inframeld_backend.access.infrastructure.rows.invitation_row import InvitationRow
from inframeld_backend.access.infrastructure.rows.model_connection_action_grant_row import (
    ModelConnectionActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.organization_action_grant_row import (
    OrganizationActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.project_membership_row import ProjectMembershipRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.access.infrastructure.settings.application_key_authentication_settings import (
    ApplicationKeyAuthenticationSettings,
)
from inframeld_backend.access.infrastructure.settings.csrf_settings import CSRFSettings
from inframeld_backend.access.infrastructure.settings.kratos_settings import KratosSettings
from inframeld_backend.access.infrastructure.settings.model_connection_destination_settings import (
    ModelConnectionDestinationSettings,
)
from inframeld_backend.access.infrastructure.verifiers.kratos_browser_session_verifier import (
    KratosBrowserSessionVerifier,
)
from inframeld_backend.access.infrastructure.verifiers.kratos_invitation_session_verifier import (
    KratosInvitationSessionVerifier,
)
from inframeld_backend.access.infrastructure.writers.postgres_access_group_action_grant_writer import (
    PostgresAccessGroupActionGrantWriter,
)
from inframeld_backend.access.infrastructure.writers.postgres_access_group_relationship_writer import (
    PostgresAccessGroupRelationshipWriter,
)
from inframeld_backend.access.infrastructure.writers.postgres_application_account_action_grant_writer import (
    PostgresApplicationAccountActionGrantWriter,
)
from inframeld_backend.access.infrastructure.writers.postgres_audit_event_writer import (
    PostgresAuditEventWriter,
)
from inframeld_backend.access.infrastructure.writers.postgres_human_admission_writer import (
    PostgresHumanAdmissionWriter,
)
from inframeld_backend.access.infrastructure.writers.postgres_identity_recovery_admission_writer import (
    PostgresIdentityRecoveryAdmissionWriter,
)
from inframeld_backend.access.infrastructure.writers.postgres_invitation_writer import (
    PostgresInvitationWriter,
)
from inframeld_backend.access.infrastructure.writers.postgres_organization_action_grant_writer import (
    PostgresOrganizationActionGrantWriter,
)
from inframeld_backend.access.infrastructure.writers.postgres_project_membership_change_writer import (
    PostgresProjectMembershipChangeWriter,
)
from inframeld_backend.bootstrap.access_group_grant_composition import (
    open_access_group_grant_change,
)
from inframeld_backend.bootstrap.application_factory import create_app
from inframeld_backend.bootstrap.application_settings import ApplicationSettings, get_settings
from inframeld_backend.bootstrap.invitation_composition import open_invitation_activation
from inframeld_backend.bootstrap.model_connection_composition import (
    open_model_connection_creation,
    open_model_connection_grant_change,
)
from inframeld_backend.bootstrap.organization_grant_composition import (
    open_organization_grant_change,
)
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.dtos.operation_reservation_request_dto import (
    OperationReservationRequestDTO,
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
    DependencyUnavailableError,
    IdempotencyInProgressError,
    IdempotencyKeyReusedError,
    ResourceNotFoundError,
    StaleRevisionError,
)
from inframeld_backend.shared.application.services.idempotency_service import IdempotencyService
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)
from inframeld_backend.shared.application.value_objects.request_fingerprint_key import (
    RequestFingerprintKey,
)
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName
from inframeld_backend.shared.domain.value_objects.submitted_display_name import (
    SubmittedDisplayName,
)
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.resources.sqlalchemy_transaction_manager import (
    SqlAlchemyTransactionManager,
)
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


async def _issue(
    database: Database, *, seed: ProjectCreationSeedDTO | None = None
) -> tuple[InvitationRecordDTO, InvitationToken, int]:
    if seed is None:
        seed = await seed_project_creator(database)
    token = InvitationToken.generate()
    now = datetime.now(UTC)
    async with database.session() as session, session.begin():
        revision = await session.scalar(
            select(OrganizationRow.access_revision)
            .where(OrganizationRow.id == seed.organization_id.value)
            .with_for_update()
        )
        assert revision is not None
        reservations = PostgresOperationReservationWriter(session)
        operation = await reservations.reserve(
            OperationReservationRequestDTO(
                principal_id=seed.access.actor_principal_id,
                organization_id=seed.organization_id,
                project_id=None,
                method=HttpMethod.POST,
                requested_route="/v1/invitations",
                key=IdempotencyKey("issue-admission-only"),
                fingerprint=b"I" * 32,
            )
        )
        assert operation.created
        record = InvitationRecordDTO(
            invitation_id=InvitationId(uuid4()),
            organization_id=seed.organization_id,
            issuer_principal_id=seed.access.actor_principal_id,
            digest=token.digest(),
            assignments=(InvitationAdmissionOnlyIntentDTO(),),
            issued_operation_id=operation.operation_id,
            issued_access_revision=revision + 1,
            issued_at=now,
            expires_at=now + timedelta(days=7),
        )
        await PostgresInvitationWriter(session).save_issue(
            record=record, expected_access_revision=revision
        )
        expiry = await reservations.mark_replayable(
            operation.operation_id, OperationReplayKind.ISSUED_SECRET
        )
        assert expiry is not None and expiry < record.expires_at

    return record, token, revision


async def _assert_persisted(
    database: Database, record: InvitationRecordDTO, token: InvitationToken, revision: int
) -> None:
    async with database.session() as session:
        row = await session.get(InvitationRow, record.invitation_id.value)
        assert row is not None and row.token_digest == token.digest().value
        assert token.value not in json.dumps(row.assignments)
        assert (
            await session.scalar(
                select(OrganizationRow.access_revision).where(
                    OrganizationRow.id == record.organization_id.value
                )
            )
            == revision + 1
        )
        audit = await session.scalar(
            select(AccessAuditEventRow).where(
                AccessAuditEventRow.correlation_id == record.issued_operation_id.value,
                AccessAuditEventRow.event_type == "invitation_issued",
            )
        )
        assert audit is not None
        assert audit.actor_principal_id == record.issuer_principal_id.value
        assert audit.target_id == record.invitation_id.value
        assert audit.before_values == {"access_revision": revision}
        assert audit.after_values == {"access_revision": revision + 1, "assignment_count": 1}
        assert token.value not in json.dumps(audit.after_values)


async def test_issuance_commits_digest_revision_and_audit(database: Database) -> None:
    record, token, revision = await _issue(database)

    await _assert_persisted(database, record, token, revision)


async def test_issuance_intent_survives_ordinary_history_removal(database: Database) -> None:
    record, token, revision = await _issue(database)
    async with database.session() as session, session.begin():
        await session.execute(
            delete(IdempotencyReservationRow).where(
                IdempotencyReservationRow.operation_id == record.issued_operation_id.value
            )
        )

    await _assert_persisted(database, record, token, revision)
    async with database.session() as session:
        assert (
            await session.get(IdempotencyReservationRow, record.issued_operation_id.value) is None
        )
        stored = await PostgresInvitationFactsReader(session).read_by_digest(token.digest())
        assert stored == record


async def test_issue_facts_observe_actual_current_actor_and_complete_intent(
    database: Database,
) -> None:
    seed = await seed_project_creator(database)
    command = IssueInvitationCommand(
        organization_id=seed.organization_id,
        assignments=(InvitationAdmissionOnlyIntentDTO(),),
        expected_access_revision=seed.access_revision,
        expected_project_access_revisions=(),
    )
    async with database.session() as session, session.begin():
        facts = await PostgresInvitationFactsReader(session).lock_for_issue(
            access=seed.access, command=command
        )
        assert facts is not None
        assert facts.organization_id == seed.organization_id
        assert facts.actor.principal.id == seed.access.actor_principal_id
        assert facts.actor.access_revision == seed.access_revision
        assert not facts.actor.has_pending_recovery
        assert any(
            grant.action_id.value == OrganizationAction.ADMIT_USERS.value and grant.can_grant
            for grant in facts.actor.grants
        )
        assert tuple(item.intent for item in facts.assignments) == command.assignments
        assert facts.assignments[0].target_exists and facts.assignments[0].project is None


async def test_original_issue_read_matches_current_authorized_native_binding(
    database: Database,
) -> None:
    seed = await seed_project_creator(database)
    record, _token, _revision = await _issue(database, seed=seed)
    async with database.session() as session, session.begin():
        await session.scalar(
            select(OrganizationRow.id)
            .where(OrganizationRow.id == seed.organization_id.value)
            .with_for_update()
        )
        actor = await PostgresOrganizationAccessFactsReader(session).read(access=seed.access)
        assert actor is not None
        eligibility = PrincipalAccessEvaluationService.evaluate(
            access=seed.access,
            principal=actor.principal,
            has_pending_recovery=actor.has_pending_recovery,
            oauth_credential_facts=actor.oauth_credential_facts,
        )
        assert HumanAdmissionPolicy.may_authorize(
            eligibility,
            has_admit_users=any(
                grant.action_id.value == OrganizationAction.ADMIT_USERS.value
                for grant in actor.grants
            ),
        )
        original = await PostgresOperationReservationWriter(session).reserve(
            OperationReservationRequestDTO(
                principal_id=seed.access.actor_principal_id,
                organization_id=seed.organization_id,
                project_id=None,
                method=HttpMethod.POST,
                requested_route="/v1/invitations",
                key=IdempotencyKey("issue-admission-only"),
                fingerprint=b"I" * 32,
            )
        )
        assert not original.created and original.operation_id == record.issued_operation_id
        assert original.replay_kind is OperationReplayKind.ISSUED_SECRET
        loaded = await PostgresInvitationFactsReader(session).read_issue_original(
            organization_id=seed.organization_id,
            issuer_principal_id=seed.access.actor_principal_id,
            operation_id=original.operation_id,
        )
        assert loaded == record


def _administration(session: AsyncSession) -> InvitationAdministrationService:
    return InvitationAdministrationService(
        transaction_manager=SqlAlchemyTransactionManager(session),
        invitation_facts_reader=PostgresInvitationFactsReader(session),
        invitation_writer=PostgresInvitationWriter(session),
        operation_idempotency=IdempotencyService(PostgresOperationReservationWriter(session)),
        invitation_fingerprint_service=InvitationFingerprintService(
            RequestFingerprintService(RequestFingerprintKey(b"F" * 32))
        ),
        default_lifetime_seconds=7 * 86400,
        maximum_lifetime_seconds=30 * 86400,
    )


async def _review(
    database: Database,
    seed: ProjectCreationSeedDTO,
    assignments: tuple[InvitationAssignmentDTO, ...],
    projects: tuple[ProjectId, ...] = (),
) -> IssueInvitationCommand:
    async with database.session() as session:
        revision = await session.scalar(
            select(OrganizationRow.access_revision).where(
                OrganizationRow.id == seed.organization_id.value
            )
        )
        assert revision is not None
        reviews: list[InvitationProjectAccessRevisionDTO] = []
        for project in projects:
            current = await session.scalar(
                select(ProjectRow.access_revision).where(ProjectRow.id == project.value)
            )
            assert current is not None
            reviews.append(
                InvitationProjectAccessRevisionDTO(project_id=project, access_revision=current)
            )
    return IssueInvitationCommand(
        organization_id=seed.organization_id,
        assignments=assignments,
        expected_access_revision=revision,
        expected_project_access_revisions=tuple(reviews),
    )


def _context(key: str) -> IdempotencyContextDTO:
    return IdempotencyContextDTO(
        method=HttpMethod.POST, requested_route="/v1/invitations", key=IdempotencyKey(key)
    )


async def _new_project(
    database: Database, seed: ProjectCreationSeedDTO, name: str
) -> CreatedProjectDTO:
    async with database.session() as session:
        revision = await session.scalar(
            select(OrganizationRow.access_revision).where(
                OrganizationRow.id == seed.organization_id.value
            )
        )
        assert revision is not None
    return (
        await create_project(
            database, replace(seed, access_revision=revision), name=name, key=f"project-{name}"
        )
    ).project


async def test_application_issuance_replays_original_without_redelivering_secret(
    database: Database,
) -> None:
    seed = await seed_project_creator(database)
    command = await _review(database, seed, (InvitationAdmissionOnlyIntentDTO(),))
    context = _context("application-issue-original")
    async with database.session() as session:
        first = await _administration(session).issue(
            access=seed.access, command=command, context=context
        )
    async with database.session() as session:
        replay = await _administration(session).issue(
            access=seed.access, command=command, context=context
        )
    assert first.token is not None and replay.token is None
    assert first.invitation_id == replay.invitation_id and first.expires_at == replay.expires_at
    assert first.operation.operation_id == replay.operation.operation_id
    assert first.operation.expires_at == replay.operation.expires_at
    assert first.operation.created and not replay.operation.created
    assert first.access_revision == replay.access_revision == command.expected_access_revision + 1
    async with database.session() as session:
        assert await session.scalar(select(func.count()).select_from(InvitationRow)) == 1
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AccessAuditEventRow)
                .where(AccessAuditEventRow.event_type == "invitation_issued")
            )
            == 1
        )
        stored = await session.get(InvitationRow, first.invitation_id.value)
        assert stored is not None and stored.token_digest == first.token.digest().value


@pytest.mark.parametrize(
    ("loss", "expected_error"),
    [
        pytest.param("admission-grant", AccessDeniedError, id="admission-grant"),
        pytest.param("suspension", AccessDeniedError, id="suspension"),
        pytest.param("recovery", AuthenticationRequiredError, id="recovery"),
        pytest.param("oauth-version", HumanOAuthCredentialRejectedError, id="oauth-version"),
    ],
)
async def test_actual_current_issuer_loss_blocks_original_disclosure(
    database: Database, loss: str, expected_error: type[Exception]
) -> None:
    seed = await seed_project_creator(database)
    access = (
        AccessContextDTO(
            actor_principal_id=seed.access.actor_principal_id, authentication_evidence=seed.binding
        )
        if loss == "oauth-version"
        else seed.access
    )
    command = await _review(database, seed, (InvitationAdmissionOnlyIntentDTO(),))
    context = _context("authority-before-original")
    async with database.session() as session:
        original = await _administration(session).issue(
            access=access, command=command, context=context
        )
    async with database.session() as session, session.begin():
        if loss == "admission-grant":
            await session.execute(
                delete(OrganizationActionGrantRow).where(
                    OrganizationActionGrantRow.organization_id == seed.organization_id.value,
                    OrganizationActionGrantRow.recipient_principal_id
                    == seed.access.actor_principal_id.value,
                    OrganizationActionGrantRow.action == OrganizationAction.ADMIT_USERS.value,
                )
            )
        elif loss == "suspension":
            await session.execute(
                update(PrincipalRow)
                .where(PrincipalRow.id == seed.access.actor_principal_id.value)
                .values(status=PrincipalStatus.SUSPENDED)
            )
        elif loss == "oauth-version":
            await session.execute(
                update(HumanCredentialVersionRow)
                .where(
                    HumanCredentialVersionRow.installation_id == seed.binding.installation_id.value,
                    HumanCredentialVersionRow.authority == seed.binding.identity.authority.value,
                    HumanCredentialVersionRow.subject == seed.binding.identity.subject.value,
                )
                .values(version=seed.binding.version.value + 1)
            )
        else:
            await PostgresIdentityRecoveryAdmissionWriter(
                session,
                installation_id=seed.binding.installation_id,
                authority=seed.binding.identity.authority,
            ).reserve(
                IdentityRecoveryEventDTO(
                    flow_id=IdentityRecoveryFlowId(uuid4()),
                    identity=seed.binding.identity,
                    event_kind=IdentityRecoveryEventKind.RECOVERY,
                )
            )
    async with database.session() as session:
        with pytest.raises(expected_error) as rejection:
            await _administration(session).issue(access=access, command=command, context=context)
        assert type(rejection.value) is expected_error
    async with database.session() as session:
        assert await session.scalar(select(func.count()).select_from(InvitationRow)) == 1
        assert (
            await session.scalar(
                select(func.count())
                .select_from(IdempotencyReservationRow)
                .where(IdempotencyReservationRow.request_key == context.key.value)
            )
            == 1
        )
        stored = await session.get(InvitationRow, original.invitation_id.value)
        assert (
            stored is not None
            and stored.issued_operation_id == original.operation.operation_id.value
        )


async def test_exact_promised_delegation_is_rechecked_before_issuance_replay(
    database: Database,
) -> None:
    seed = await seed_project_creator(database)
    intent = InvitationActionGrantIntentDTO(
        target=OrganizationGrantTargetDTO(organization_id=seed.organization_id),
        action_id=ActionId("create-projects"),
        can_grant=False,
    )
    command = await _review(database, seed, (intent,))
    context = _context("delegation-before-original")
    async with database.session() as session:
        await _administration(session).issue(access=seed.access, command=command, context=context)
    # A controlled current-record change tests observation, not the administration mutation path.
    async with database.session() as session, session.begin():
        await session.execute(
            update(OrganizationActionGrantRow)
            .where(
                OrganizationActionGrantRow.organization_id == seed.organization_id.value,
                OrganizationActionGrantRow.recipient_principal_id
                == seed.access.actor_principal_id.value,
                OrganizationActionGrantRow.action == "create-projects",
            )
            .values(can_grant=False)
        )
    async with database.session() as session:
        with pytest.raises(AccessDeniedError):
            await _administration(session).issue(
                access=seed.access, command=command, context=context
            )
    async with database.session() as session:
        assert await session.scalar(select(func.count()).select_from(InvitationRow)) == 1


async def test_issuance_observes_all_actual_access_targets_without_assigning_them(
    database: Database,
) -> None:
    seed = await seed_project_creator(database)
    project = await _new_project(database, seed, "support")
    group = (
        await create_group(
            database,
            seed.access,
            project.project_id,
            revision=project.access_revision,
            name="knowledge",
            key="knowledge-group",
        )
    ).group
    members = (
        await create_group(
            database,
            seed.access,
            project.project_id,
            revision=group.access_revision,
            name="readers",
            key="readers-group",
        )
    ).group
    account = (
        await create_account(
            database,
            seed.access,
            project.project_id,
            revision=members.access_revision,
            key="support-bot",
        )
    ).account
    assignments: tuple[InvitationAssignmentDTO, ...] = (
        InvitationProjectMembershipIntentDTO(project_id=project.project_id),
        InvitationGroupManagerIntentDTO(
            project_id=project.project_id, access_group_id=group.group_id
        ),
        InvitationGroupMembershipIntentDTO(
            project_id=project.project_id, access_group_id=members.group_id
        ),
        InvitationActionGrantIntentDTO(
            target=OrganizationGrantTargetDTO(organization_id=seed.organization_id),
            action_id=ActionId("create-projects"),
            can_grant=False,
        ),
        InvitationActionGrantIntentDTO(
            target=ProjectGrantTargetDTO(project_id=project.project_id),
            action_id=ActionId("create-access-groups"),
            can_grant=True,
        ),
        InvitationActionGrantIntentDTO(
            target=AccessGroupGrantTargetDTO(
                project_id=project.project_id, access_group_id=group.group_id
            ),
            action_id=ActionId("add-documents"),
            can_grant=True,
        ),
        InvitationActionGrantIntentDTO(
            target=ApplicationAccountGrantTargetDTO(
                project_id=project.project_id, application_principal_id=account.principal_id
            ),
            action_id=ActionId("issue-application-keys"),
            can_grant=True,
        ),
    )
    command = await _review(database, seed, assignments, (project.project_id,))
    async with database.session() as session:
        principals_before = await session.scalar(select(func.count()).select_from(PrincipalRow))
    async with database.session() as session:
        issued = await _administration(session).issue(
            access=seed.access, command=command, context=_context("all-actual-access-intents")
        )
    assert issued.token is not None and issued.assignments == assignments
    async with database.session() as session:
        stored = await PostgresInvitationFactsReader(session).read_by_digest(issued.token.digest())
        assert stored is not None and stored.assignments == assignments
        await session.scalar(
            select(OrganizationRow.id)
            .where(OrganizationRow.id == seed.organization_id.value)
            .with_for_update()
        )
        await session.scalar(
            select(ProjectRow.id).where(ProjectRow.id == project.project_id.value).with_for_update()
        )
        current_issuer = await PostgresInvitationAssignmentFactsReader(session).read_current_issuer(
            invitation=stored
        )
        assert current_issuer is not None and current_issuer.has_coherent_identity
        assert tuple(item.intent for item in current_issuer.assignments) == assignments
        assert all(item.target_exists for item in current_issuer.assignments)
        group_grant = current_issuer.assignments[5]
        assert group_grant.actor_is_group_member and group_grant.actor_is_group_manager
        assert not group_grant.actor_can_grant
        assert current_issuer.assignments[4].actor_can_grant
        assert current_issuer.assignments[6].actor_can_grant
        assert (
            await session.scalar(select(func.count()).select_from(PrincipalRow))
            == principals_before
        )
        assert (
            await session.scalar(
                select(ProjectRow.access_revision).where(ProjectRow.id == project.project_id.value)
            )
            == command.expected_project_access_revisions[0].access_revision
        )
        # Group management authorized the document promise, without manufacturing a direct grant.
        assert await session.scalar(select(func.count()).select_from(GroupActionGrantRow)) == 0


@pytest.mark.parametrize("kind", ["group", "application"])
async def test_authoritative_target_parent_cannot_be_replaced_by_requested_project(
    database: Database, kind: str
) -> None:
    seed = await seed_project_creator(database)
    support = await _new_project(database, seed, "support")
    sales = await _new_project(database, seed, "sales")
    if kind == "group":
        group = (
            await create_group(
                database,
                seed.access,
                sales.project_id,
                revision=sales.access_revision,
                key="foreign-group",
            )
        ).group
        intent = InvitationGroupManagerIntentDTO(
            project_id=support.project_id, access_group_id=group.group_id
        )
    else:
        account = (
            await create_account(
                database,
                seed.access,
                sales.project_id,
                revision=sales.access_revision,
                key="foreign-app",
            )
        ).account
        intent = InvitationActionGrantIntentDTO(
            target=ApplicationAccountGrantTargetDTO(
                project_id=support.project_id, application_principal_id=account.principal_id
            ),
            action_id=ActionId("issue-application-keys"),
            can_grant=True,
        )
    command = await _review(database, seed, (intent,), (support.project_id,))
    async with database.session() as session:
        with pytest.raises(ResourceNotFoundError):
            await _administration(session).issue(
                access=seed.access, command=command, context=_context("foreign-parent")
            )
    async with database.session() as session:
        assert await session.scalar(select(func.count()).select_from(InvitationRow)) == 0
        assert (
            await session.scalar(
                select(OrganizationRow.access_revision).where(
                    OrganizationRow.id == seed.organization_id.value
                )
            )
            == command.expected_access_revision
        )


async def test_completion_failure_rolls_back_invitation_revision_audit_and_reservation(
    database: Database,
) -> None:
    seed = await seed_project_creator(database)
    command = await _review(database, seed, (InvitationAdmissionOnlyIntentDTO(),))
    context = _context("completion-rollback")
    with patch.object(
        PostgresOperationReservationWriter,
        "mark_replayable",
        side_effect=ConflictError("Controlled completion failure"),
    ):
        async with database.session() as session:
            with pytest.raises(ConflictError):
                await _administration(session).issue(
                    access=seed.access, command=command, context=context
                )
    async with database.session() as session:
        assert await session.scalar(select(func.count()).select_from(InvitationRow)) == 0
        assert (
            await session.scalar(
                select(OrganizationRow.access_revision).where(
                    OrganizationRow.id == seed.organization_id.value
                )
            )
            == command.expected_access_revision
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AccessAuditEventRow)
                .where(AccessAuditEventRow.event_type == "invitation_issued")
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(IdempotencyReservationRow)
                .where(IdempotencyReservationRow.request_key == context.key.value)
            )
            == 0
        )


@pytest.mark.parametrize("isolation", ["REPEATABLE READ", "SERIALIZABLE"])
async def test_issue_observation_rejects_stale_snapshot_isolation(
    database: Database, isolation: str
) -> None:
    seed = await seed_project_creator(database)
    command = await _review(database, seed, (InvitationAdmissionOnlyIntentDTO(),))
    async with database.session() as session, session.begin():
        await session.connection(execution_options={"isolation_level": isolation})
        with pytest.raises(RuntimeError, match="READ COMMITTED"):
            await PostgresInvitationFactsReader(session).lock_for_issue(
                access=seed.access, command=command
            )


async def test_project_turns_are_sorted_and_held_until_caller_transaction_finishes(
    database: Database,
) -> None:
    seed = await seed_project_creator(database)
    first = await _new_project(database, seed, "support")
    second = await _new_project(database, seed, "sales")
    low, high = sorted((first.project_id, second.project_id), key=lambda item: item.value.int)
    command = await _review(
        database,
        seed,
        (
            InvitationProjectMembershipIntentDTO(project_id=high),
            InvitationProjectMembershipIntentDTO(project_id=low),
        ),
        (high, low),
    )
    loop = asyncio.get_running_loop()
    started: asyncio.Future[int] = loop.create_future()
    observed: asyncio.Future[InvitationFactsDTO | None] = loop.create_future()
    release = asyncio.Event()

    async def read_in_caller_turn() -> None:
        async with database.session() as session, session.begin():
            pid = await session.scalar(select(func.pg_backend_pid()))
            assert isinstance(pid, int)
            started.set_result(pid)
            facts = await PostgresInvitationFactsReader(session).lock_for_issue(
                access=seed.access, command=command
            )
            observed.set_result(facts)
            await release.wait()

    task: asyncio.Task[None] | None = None
    try:
        async with database.session() as holder, holder.begin():
            holder_pid = await holder.scalar(select(func.pg_backend_pid()))
            assert isinstance(holder_pid, int)
            await holder.scalar(
                select(ProjectRow.id).where(ProjectRow.id == high.value).with_for_update()
            )
            task = asyncio.create_task(read_in_caller_turn())
            reader_pid = await started
            async with asyncio.timeout(2):
                async with database.session() as observer:
                    while True:
                        blockers = await observer.scalar(
                            select(func.pg_blocking_pids(reader_pid, type_=ARRAY(Integer)))
                        )
                        if blockers is not None and holder_pid in blockers:
                            break
                        await asyncio.sleep(0.01)
            await holder.execute(
                update(ProjectRow)
                .where(ProjectRow.id == high.value)
                .values(access_revision=ProjectRow.access_revision + 1)
            )
            # Input was high→low. A low lock held while waiting for high proves sorted acquisition.
            async with database.session() as contender, contender.begin():
                with pytest.raises(OperationalError):
                    await contender.scalar(
                        select(ProjectRow.id)
                        .where(ProjectRow.id == low.value)
                        .with_for_update(nowait=True)
                    )
        async with asyncio.timeout(2):
            facts = await observed
        assert facts is not None and len(facts.assignments) == 2
        high_facts = facts.assignments[0].project
        assert high_facts is not None and high_facts.project_id == high
        assert (
            high_facts.access_revision
            == command.expected_project_access_revisions[0].access_revision + 1
        )
        async with database.session() as contender, contender.begin():
            with pytest.raises(OperationalError):
                await contender.scalar(
                    select(ProjectRow.id)
                    .where(ProjectRow.id == high.value)
                    .with_for_update(nowait=True)
                )
        release.set()
        assert task is not None
        await task
        async with database.session() as contender, contender.begin():
            for project in (low, high):
                assert (
                    await contender.scalar(
                        select(ProjectRow.id)
                        .where(ProjectRow.id == project.value)
                        .with_for_update(nowait=True)
                    )
                    == project.value
                )
    finally:
        release.set()
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


async def _prepare_revocation(
    session: AsyncSession, seed: ProjectCreationSeedDTO, record: InvitationRecordDTO
) -> tuple[InvitationRevocationResultDTO, int]:
    """Establish real current administration and a completed exact native reservation."""
    await session.scalar(
        select(OrganizationRow.id)
        .where(OrganizationRow.id == seed.organization_id.value)
        .with_for_update()
    )
    actor = await PostgresOrganizationAccessFactsReader(session).read(access=seed.access)
    assert actor is not None
    eligibility = PrincipalAccessEvaluationService.evaluate(
        access=seed.access,
        principal=actor.principal,
        has_pending_recovery=actor.has_pending_recovery,
        oauth_credential_facts=actor.oauth_credential_facts,
    )
    admission = tuple(
        grant
        for grant in actor.grants
        if grant.action_id.value == OrganizationAction.ADMIT_USERS.value
    )
    assert InvitationPolicy.may_revoke(
        eligibility,
        organization_id=record.organization_id,
        issuer_principal_id=record.issuer_principal_id,
        has_admit_users=bool(admission),
        can_grant_admit_users=any(grant.can_grant for grant in admission),
    )
    request = OperationReservationRequestDTO(
        principal_id=seed.access.actor_principal_id,
        organization_id=record.organization_id,
        project_id=None,
        method=HttpMethod.POST,
        requested_route=f"/v1/invitations/{record.invitation_id.value}/revoke",
        key=IdempotencyKey("revoke-original"),
        fingerprint=b"R" * 32,
    )
    reservations = PostgresOperationReservationWriter(session)
    operation = await reservations.reserve(request)
    assert operation.created
    expiry = await reservations.mark_replayable(
        operation.operation_id, OperationReplayKind.SAFE_RESULT
    )
    assert expiry is not None
    recovered = await reservations.reserve(request)
    assert not recovered.created and recovered.operation_id == operation.operation_id
    return InvitationRevocationResultDTO(
        invitation_id=record.invitation_id,
        organization_id=record.organization_id,
        access_revision=actor.access_revision + 1,
        operation=CompletedSynchronousOperationDTO(
            operation_id=operation.operation_id,
            created=True,
            replay_kind=OperationReplayKind.SAFE_RESULT,
            expires_at=expiry,
        ),
    ), actor.access_revision


async def test_revocation_facts_observe_current_actor_and_original_scope(
    database: Database,
) -> None:
    seed = await seed_project_creator(database)
    record, _, _ = await _issue(database, seed=seed)
    async with database.session() as session, session.begin():
        facts = await PostgresInvitationFactsReader(session).lock_for_revocation(
            access=seed.access, invitation_id=record.invitation_id
        )
        assert facts is not None and facts.invitation == record
        assert (
            facts.organization_id == seed.organization_id
            and facts.actor.principal.id == seed.access.actor_principal_id
        )
        assert facts.actor.access_revision == record.issued_access_revision
        assert not facts.actor.has_pending_recovery
        unknown = replace(seed.access, actor_principal_id=PrincipalId(uuid4()))
        assert (
            await PostgresInvitationFactsReader(session).lock_for_revocation(
                access=unknown, invitation_id=record.invitation_id
            )
            is None
        )


async def test_revocation_atomically_marks_audits_and_retains_original(database: Database) -> None:
    seed = await seed_project_creator(database)
    record, token, _ = await _issue(database, seed=seed)
    now = datetime.now(UTC)
    async with database.session() as session, session.begin():
        result, revision = await _prepare_revocation(session, seed, record)
        await PostgresInvitationWriter(session).save_revocation(
            invitation=record,
            result=result,
            actor_principal_id=seed.access.actor_principal_id,
            expected_access_revision=revision,
            revoked_at=now,
        )
    async with database.session() as session:
        stored = await PostgresInvitationFactsReader(session).read_by_digest(token.digest())
        assert stored == replace(record, revoked_at=now)
        assert (
            await session.scalar(
                select(OrganizationRow.access_revision).where(
                    OrganizationRow.id == seed.organization_id.value
                )
            )
            == revision + 1
        )
        audit = await session.scalar(
            select(AccessAuditEventRow).where(
                AccessAuditEventRow.correlation_id == result.operation.operation_id.value
            )
        )
        assert audit is not None and audit.event_type == "invitation_revoked"
        assert audit.actor_principal_id == seed.access.actor_principal_id.value
        assert audit.target_id == record.invitation_id.value
        assert audit.before_values == {"access_revision": revision, "revoked": False}
        assert audit.after_values == {"access_revision": revision + 1, "revoked": True}
        original = await PostgresInvitationFactsReader(session).read_revocation_original(
            organization_id=record.organization_id,
            actor_principal_id=seed.access.actor_principal_id,
            invitation_id=record.invitation_id,
            operation_id=result.operation.operation_id,
        )
        assert original == replace(result, operation=replace(result.operation, created=False))


async def test_revocation_original_is_absent_without_business_result(database: Database) -> None:
    seed = await seed_project_creator(database)
    record, _, _ = await _issue(database, seed=seed)
    async with database.session() as session, session.begin():
        result, _ = await _prepare_revocation(session, seed, record)
        assert (
            await PostgresInvitationFactsReader(session).read_revocation_original(
                organization_id=record.organization_id,
                actor_principal_id=seed.access.actor_principal_id,
                invitation_id=record.invitation_id,
                operation_id=result.operation.operation_id,
            )
            is None
        )


async def _current_org_revision(database: Database, seed: ProjectCreationSeedDTO) -> int:
    async with database.session() as session:
        revision = await session.scalar(
            select(OrganizationRow.access_revision).where(
                OrganizationRow.id == seed.organization_id.value
            )
        )
        assert revision is not None
        return revision


def _revoke_context(
    record: InvitationRecordDTO, key: str = "service-revoke-original"
) -> IdempotencyContextDTO:
    return IdempotencyContextDTO(
        method=HttpMethod.POST,
        requested_route=f"/v1/invitations/{record.invitation_id.value}/revoke",
        key=IdempotencyKey(key),
    )


async def test_revocation_service_preserves_original_and_noop_revision_timestamp(
    database: Database,
) -> None:
    seed = await seed_project_creator(database)
    project = await _new_project(database, seed, "support")
    record, token, _ = await _issue(database, seed=seed)
    revision = await _current_org_revision(database, seed)
    command = RevokeInvitationCommand(
        invitation_id=record.invitation_id, expected_access_revision=revision
    )
    context = _revoke_context(record)
    async with database.session() as session:
        first = await _administration(session).revoke(
            access=seed.access, command=command, context=context
        )
    async with database.session() as session:
        replay = await _administration(session).revoke(
            access=seed.access, command=command, context=context
        )
    assert replay == replace(first, operation=replace(first.operation, created=False))
    assert first.access_revision == revision + 1
    async with database.session() as session:
        marked = await PostgresInvitationFactsReader(session).read_by_digest(token.digest())
        assert marked is not None and marked.revoked_at is not None
        after_replay = (
            await session.scalars(
                select(AccessAuditEventRow).where(
                    AccessAuditEventRow.event_type == "invitation_revoked"
                )
            )
        ).all()
        assert len(after_replay) == 1
        assert after_replay[0].correlation_id == first.operation.operation_id.value
        before_noop = await session.scalar(
            select(func.clock_timestamp(type_=DateTime(timezone=True)))
        )
        assert before_noop is not None
    noop_context = _revoke_context(record, "already-revoked-new-key")
    async with database.session() as session:
        noop = await _administration(session).revoke(
            access=seed.access,
            command=replace(command, expected_access_revision=first.access_revision),
            context=noop_context,
        )
    assert noop.access_revision == first.access_revision and noop.operation.created
    async with database.session() as session:
        assert await PostgresInvitationFactsReader(session).read_by_digest(token.digest()) == marked
        assert (
            await session.scalar(
                select(OrganizationRow.access_revision).where(
                    OrganizationRow.id == seed.organization_id.value
                )
            )
            == first.access_revision
        )
        assert (
            await session.scalar(
                select(ProjectRow.access_revision).where(ProjectRow.id == project.project_id.value)
            )
            == project.access_revision
        )
        assert (
            await session.scalar(select(func.count()).select_from(InvitationRevocationResultRow))
            == 2
        )
        after_noop = await session.scalar(
            select(func.clock_timestamp(type_=DateTime(timezone=True)))
        )
        assert after_noop is not None
        audits = (
            await session.scalars(
                select(AccessAuditEventRow).where(
                    AccessAuditEventRow.event_type == "invitation_revoked"
                )
            )
        ).all()
        assert len(audits) == 2
        by_operation = {audit.correlation_id: audit for audit in audits}
        assert first.operation.operation_id != noop.operation.operation_id
        assert set(by_operation) == {
            first.operation.operation_id.value,
            noop.operation.operation_id.value,
        }
        first_audit = by_operation[first.operation.operation_id.value]
        noop_audit = by_operation[noop.operation.operation_id.value]
        assert first_audit.occurred_at < noop_audit.occurred_at
        assert before_noop <= noop_audit.occurred_at <= after_noop
        for audit, result, request, before_revision, was_revoked in (
            (first_audit, first, context, revision, False),
            (noop_audit, noop, noop_context, first.access_revision, True),
        ):
            assert (
                audit.actor_kind == PrincipalKind.HUMAN.value
                and audit.actor_principal_id == seed.access.actor_principal_id.value
            )
            assert audit.organization_id == seed.organization_id.value and audit.project_id is None
            assert (
                audit.target_kind == "invitation" and audit.target_id == record.invitation_id.value
            )
            assert audit.action == OrganizationAction.ADMIT_USERS.value
            assert audit.before_values == {
                "access_revision": before_revision,
                "revoked": was_revoked,
            }
            assert audit.after_values == {
                "access_revision": result.access_revision,
                "revoked": True,
            }
            native = await session.get(
                IdempotencyReservationRow, result.operation.operation_id.value
            )
            assert native is not None and native.principal_id == audit.actor_principal_id
            assert (
                native.organization_id == audit.organization_id and native.method == request.method
            )
            assert (
                native.requested_route == request.requested_route
                and native.request_key == request.key.value
            )

        results = (
            await session.scalars(
                select(InvitationRevocationResultRow).order_by(
                    InvitationRevocationResultRow.changed.desc()
                )
            )
        ).all()
        assert [(item.before_revision, item.access_revision, item.changed) for item in results] == [
            (revision, revision + 1, True),
            (revision + 1, revision + 1, False),
        ]


@pytest.mark.parametrize(
    ("loss", "expected_error"),
    [
        pytest.param("admission-grant", AccessDeniedError, id="admission-grant"),
        pytest.param("suspension", AccessDeniedError, id="suspension"),
        pytest.param("recovery", AuthenticationRequiredError, id="recovery"),
        pytest.param("oauth-version", HumanOAuthCredentialRejectedError, id="oauth-version"),
    ],
)
async def test_current_revocation_authority_loss_precedes_retained_result(
    database: Database, loss: str, expected_error: type[Exception]
) -> None:
    seed = await seed_project_creator(database)
    record, token, _ = await _issue(database, seed=seed)
    access = (
        replace(seed.access, authentication_evidence=seed.binding)
        if loss == "oauth-version"
        else seed.access
    )
    command = RevokeInvitationCommand(
        invitation_id=record.invitation_id,
        expected_access_revision=await _current_org_revision(database, seed),
    )
    context = _revoke_context(record)
    async with database.session() as session:
        first = await _administration(session).revoke(
            access=access, command=command, context=context
        )
    async with database.session() as session, session.begin():
        if loss == "admission-grant":
            await session.execute(
                delete(OrganizationActionGrantRow).where(
                    OrganizationActionGrantRow.organization_id == seed.organization_id.value,
                    OrganizationActionGrantRow.recipient_principal_id
                    == seed.access.actor_principal_id.value,
                    OrganizationActionGrantRow.action == OrganizationAction.ADMIT_USERS.value,
                )
            )
        elif loss == "suspension":
            await session.execute(
                update(PrincipalRow)
                .where(PrincipalRow.id == seed.access.actor_principal_id.value)
                .values(status=PrincipalStatus.SUSPENDED)
            )
        elif loss == "oauth-version":
            await session.execute(
                update(HumanCredentialVersionRow)
                .where(
                    HumanCredentialVersionRow.installation_id == seed.binding.installation_id.value,
                    HumanCredentialVersionRow.authority == seed.binding.identity.authority.value,
                    HumanCredentialVersionRow.subject == seed.binding.identity.subject.value,
                )
                .values(version=seed.binding.version.value + 1)
            )
        else:
            await PostgresIdentityRecoveryAdmissionWriter(
                session,
                installation_id=seed.binding.installation_id,
                authority=seed.binding.identity.authority,
            ).reserve(
                IdentityRecoveryEventDTO(
                    flow_id=IdentityRecoveryFlowId(uuid4()),
                    identity=seed.binding.identity,
                    event_kind=IdentityRecoveryEventKind.RECOVERY,
                )
            )
    async with database.session() as session:
        with pytest.raises(expected_error) as rejection:
            await _administration(session).revoke(access=access, command=command, context=context)
        assert type(rejection.value) is expected_error
    async with database.session() as session:
        current = await PostgresInvitationFactsReader(session).read_by_digest(token.digest())
        assert current is not None and current.revoked_at is not None
        assert (
            await session.scalar(select(func.count()).select_from(InvitationRevocationResultRow))
            == 1
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AccessAuditEventRow)
                .where(AccessAuditEventRow.event_type == "invitation_revoked")
            )
            == 1
        )
        assert (
            await session.scalar(
                select(OrganizationRow.access_revision).where(
                    OrganizationRow.id == seed.organization_id.value
                )
            )
            == first.access_revision
        )


@pytest.mark.parametrize("can_grant", [False, True])
async def test_other_admitted_human_needs_current_admission_delegation_to_revoke(
    database: Database, can_grant: bool
) -> None:
    seed = await seed_membership_project(database)
    record, token, _ = await _issue(database, seed=seed.actor)
    revision = await _current_org_revision(database, seed.actor)
    async with open_organization_grant_change(
        database, RequestFingerprintService(RequestFingerprintKey(b"K" * 32))
    ) as service:
        granted = await service.set_grant(
            access=seed.actor.access,
            command=SetOrganizationActionGrantCommand(
                organization_id=seed.actor.organization_id,
                recipient_principal_id=seed.bob_id,
                action_id=ActionId("admit-users"),
                can_grant=can_grant,
                expected_access_revision=revision,
            ),
            context=IdempotencyContextDTO(
                method=HttpMethod.PUT,
                requested_route=f"/v1/organizations/{seed.actor.organization_id.value}/grants/{seed.bob_id.value}/admit-users",
                key=IdempotencyKey("bob-admit-users"),
            ),
        )
    bob = seed.bob_access
    command = RevokeInvitationCommand(
        invitation_id=record.invitation_id, expected_access_revision=granted.access_revision
    )
    async with database.session() as session:
        if can_grant:
            result = await _administration(session).revoke(
                access=bob, command=command, context=_revoke_context(record)
            )
            assert result.access_revision == granted.access_revision + 1
        else:
            with pytest.raises(AccessDeniedError):
                await _administration(session).revoke(
                    access=bob, command=command, context=_revoke_context(record)
                )
    async with database.session() as session:
        current = await PostgresInvitationFactsReader(session).read_by_digest(token.digest())
        assert (
            current is not None
            and current.issuer_principal_id == seed.actor.access.actor_principal_id
        )
        assert (current.revoked_at is not None) is can_grant
        audit = await session.scalar(
            select(AccessAuditEventRow).where(
                AccessAuditEventRow.event_type == "invitation_revoked"
            )
        )
        if can_grant:
            assert audit is not None and audit.actor_principal_id == seed.bob_id.value
        else:
            assert audit is None


async def test_missing_revocation_business_result_cannot_reapply_an_original(
    database: Database,
) -> None:
    seed = await seed_project_creator(database)
    record, token, _ = await _issue(database, seed=seed)
    command = RevokeInvitationCommand(
        invitation_id=record.invitation_id,
        expected_access_revision=await _current_org_revision(database, seed),
    )
    context = _revoke_context(record)
    async with database.session() as session:
        first = await _administration(session).revoke(
            access=seed.access, command=command, context=context
        )
    async with database.session() as session, session.begin():
        await session.execute(
            delete(InvitationRevocationResultRow).where(
                InvitationRevocationResultRow.operation_id == first.operation.operation_id.value
            )
        )
    async with database.session() as session:
        with pytest.raises(DependencyUnavailableError):
            await _administration(session).revoke(
                access=seed.access, command=command, context=context
            )
    async with database.session() as session:
        current = await PostgresInvitationFactsReader(session).read_by_digest(token.digest())
        assert current is not None and current.revoked_at is not None
        assert (
            await session.scalar(
                select(OrganizationRow.access_revision).where(
                    OrganizationRow.id == seed.organization_id.value
                )
            )
            == first.access_revision
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AccessAuditEventRow)
                .where(AccessAuditEventRow.event_type == "invitation_revoked")
            )
            == 1
        )


@pytest.mark.parametrize("failure", ["completion", "after-write"])
async def test_revocation_failure_rolls_back_mark_revision_audit_and_original(
    database: Database, failure: str
) -> None:
    seed = await seed_project_creator(database)
    record, token, _ = await _issue(database, seed=seed)
    revision = await _current_org_revision(database, seed)
    command = RevokeInvitationCommand(
        invitation_id=record.invitation_id, expected_access_revision=revision
    )
    context = _revoke_context(record)
    save = PostgresInvitationWriter.save_revocation

    async def fail_after_write(
        self: PostgresInvitationWriter,
        *,
        invitation: InvitationRecordDTO,
        result: InvitationRevocationResultDTO,
        actor_principal_id: PrincipalId,
        expected_access_revision: int,
        revoked_at: datetime,
    ) -> None:
        await save(
            self,
            invitation=invitation,
            result=result,
            actor_principal_id=actor_principal_id,
            expected_access_revision=expected_access_revision,
            revoked_at=revoked_at,
        )
        raise ConflictError("Controlled failure after real revocation persistence")

    patcher = (
        patch.object(
            PostgresOperationReservationWriter,
            "mark_replayable",
            side_effect=ConflictError("Controlled completion failure"),
        )
        if failure == "completion"
        else patch.object(PostgresInvitationWriter, "save_revocation", new=fail_after_write)
    )
    with patcher:
        async with database.session() as session:
            with pytest.raises(ConflictError):
                await _administration(session).revoke(
                    access=seed.access, command=command, context=context
                )
    async with database.session() as session:
        assert await PostgresInvitationFactsReader(session).read_by_digest(token.digest()) == record
        assert (
            await session.scalar(
                select(OrganizationRow.access_revision).where(
                    OrganizationRow.id == seed.organization_id.value
                )
            )
            == revision
        )
        assert (
            await session.scalar(select(func.count()).select_from(InvitationRevocationResultRow))
            == 0
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AccessAuditEventRow)
                .where(AccessAuditEventRow.event_type == "invitation_revoked")
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(IdempotencyReservationRow)
                .where(IdempotencyReservationRow.request_key == context.key.value)
            )
            == 0
        )


async def test_revocation_history_removal_cascades_only_its_result(database: Database) -> None:
    seed = await seed_project_creator(database)
    record, token, _ = await _issue(database, seed=seed)
    command = RevokeInvitationCommand(
        invitation_id=record.invitation_id,
        expected_access_revision=await _current_org_revision(database, seed),
    )
    context = _revoke_context(record)
    async with database.session() as session:
        first = await _administration(session).revoke(
            access=seed.access, command=command, context=context
        )
    async with database.session() as session, session.begin():
        await session.execute(
            delete(IdempotencyReservationRow).where(
                IdempotencyReservationRow.operation_id == first.operation.operation_id.value
            )
        )
    async with database.session() as session:
        with pytest.raises(StaleRevisionError):
            await _administration(session).revoke(
                access=seed.access, command=command, context=context
            )
    async with database.session() as session:
        current = await PostgresInvitationFactsReader(session).read_by_digest(token.digest())
        assert current is not None and current.revoked_at is not None
        assert (
            await session.scalar(select(func.count()).select_from(InvitationRevocationResultRow))
            == 0
        )
        assert (
            await session.get(IdempotencyReservationRow, record.issued_operation_id.value)
            is not None
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(IdempotencyReservationRow)
                .where(IdempotencyReservationRow.request_key == context.key.value)
            )
            == 0
        )


@pytest.mark.parametrize("binding", ["route", "method", "kind", "expired"])
async def test_revocation_original_requires_exact_live_native_binding(
    database: Database, binding: str
) -> None:
    seed = await seed_project_creator(database)
    record, _, _ = await _issue(database, seed=seed)
    async with database.session() as session, session.begin():
        result, revision = await _prepare_revocation(session, seed, record)
        await PostgresInvitationWriter(session).save_revocation(
            invitation=record,
            result=result,
            actor_principal_id=seed.access.actor_principal_id,
            expected_access_revision=revision,
            revoked_at=datetime.now(UTC),
        )
    async with database.session() as session, session.begin():
        if binding == "route":
            await session.execute(
                update(IdempotencyReservationRow)
                .where(
                    IdempotencyReservationRow.operation_id == result.operation.operation_id.value
                )
                .values(requested_route="/v1/invitations/other/revoke")
            )
        elif binding == "method":
            await session.execute(
                update(IdempotencyReservationRow)
                .where(
                    IdempotencyReservationRow.operation_id == result.operation.operation_id.value
                )
                .values(method=HttpMethod.PUT)
            )
        elif binding == "kind":
            await session.execute(
                update(IdempotencyReservationRow)
                .where(
                    IdempotencyReservationRow.operation_id == result.operation.operation_id.value
                )
                .values(replay_kind=OperationReplayKind.ISSUED_SECRET)
            )
        else:
            await session.execute(
                update(IdempotencyReservationRow)
                .where(
                    IdempotencyReservationRow.operation_id == result.operation.operation_id.value
                )
                .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
            )
        # This controlled history mutation checks disclosure integrity, not fresh authorization.
        assert (
            await PostgresInvitationFactsReader(session).read_revocation_original(
                organization_id=record.organization_id,
                actor_principal_id=seed.access.actor_principal_id,
                invitation_id=record.invitation_id,
                operation_id=result.operation.operation_id,
            )
            is None
        )


@pytest.mark.parametrize("isolation", ["REPEATABLE READ", "SERIALIZABLE"])
async def test_revocation_observation_rejects_stale_snapshot_isolation(
    database: Database, isolation: str
) -> None:
    seed = await seed_project_creator(database)
    record, _, _ = await _issue(database, seed=seed)
    async with database.session() as session, session.begin():
        await session.connection(execution_options={"isolation_level": isolation})
        with pytest.raises(RuntimeError, match="READ COMMITTED"):
            await PostgresInvitationFactsReader(session).lock_for_revocation(
                access=seed.access, invitation_id=record.invitation_id
            )


def _preview_service(session: AsyncSession) -> InvitationPreviewService:
    return InvitationPreviewService(
        transaction_manager=SqlAlchemyTransactionManager(session),
        invitation_preview_facts_reader=PostgresInvitationBindingReader(session),
    )


def _unadmitted_invitation_proof(seed: ProjectCreationSeedDTO) -> InvitationBrowserProofDTO:
    return InvitationBrowserProofDTO(
        identity=VerifiedHumanIdentityDTO(
            authority=seed.binding.identity.authority, subject=IdentitySubject(str(UUID(int=900)))
        ),
        password_completed=None,
    )


@pytest.mark.parametrize("legacy_names", [False, True])
async def test_preview_reads_actual_scope_without_admission_or_reservation(
    database: Database, legacy_names: bool
) -> None:
    seed = await seed_project_creator(database)
    project = await _new_project(database, seed, "support")
    group = (
        await create_group(
            database, seed.access, project.project_id, revision=project.access_revision
        )
    ).group
    account = (
        await create_account(
            database, seed.access, project.project_id, revision=group.access_revision
        )
    ).account
    assignments: tuple[InvitationAssignmentDTO, ...] = (
        InvitationProjectMembershipIntentDTO(project_id=project.project_id),
        InvitationGroupMembershipIntentDTO(
            project_id=project.project_id, access_group_id=group.group_id
        ),
        InvitationActionGrantIntentDTO(
            target=ApplicationAccountGrantTargetDTO(
                project_id=project.project_id, application_principal_id=account.principal_id
            ),
            action_id=ActionId("issue-application-keys"),
            can_grant=True,
        ),
    )
    command = await _review(database, seed, assignments, (project.project_id,))
    async with database.session() as session:
        issued = await _administration(session).issue(
            access=seed.access, command=command, context=_context("preview-all-current-targets")
        )
    assert issued.token is not None
    if legacy_names:
        # Read legacy presentation labels even when the later exact Name field is absent.
        async with database.session() as session, session.begin():
            await session.execute(
                update(ProjectRow)
                .where(ProjectRow.id == project.project_id.value)
                .values(resource_name=None)
            )
            await session.execute(
                update(AccessGroupRow)
                .where(AccessGroupRow.id == group.group_id.value)
                .values(resource_name=None)
            )
            await session.execute(
                update(ApplicationAccountRow)
                .where(ApplicationAccountRow.principal_id == account.principal_id.value)
                .values(resource_name=None)
            )
    proof = _unadmitted_invitation_proof(seed)
    async with database.session() as session:
        org_name = await session.scalar(
            select(OrganizationRow.name).where(OrganizationRow.id == seed.organization_id.value)
        )
        reservations_before = await session.scalar(
            select(func.count()).select_from(IdempotencyReservationRow)
        )
        audits_before = await session.scalar(select(func.count()).select_from(AccessAuditEventRow))
    async with database.session() as session:
        result = await _preview_service(session).preview(
            proof=proof, query=PreviewInvitationQuery(token=issued.token)
        )
    assert result.invitation_id == issued.invitation_id
    assert (
        result.organization_id == issued.organization_id
        and result.assignments == assignments
        and result.expires_at == issued.expires_at
    )
    assert len(result.scopes) == 4
    assert {scope.target: scope.display_name for scope in result.scopes} == {
        OrganizationGrantTargetDTO(organization_id=seed.organization_id): org_name,
        ProjectGrantTargetDTO(project_id=project.project_id): project.display_name,
        AccessGroupGrantTargetDTO(
            project_id=project.project_id, access_group_id=group.group_id
        ): group.display_name,
        ApplicationAccountGrantTargetDTO(
            project_id=project.project_id, application_principal_id=account.principal_id
        ): account.display_name,
    }
    async with database.session() as session:
        assert await session.scalar(select(func.count()).select_from(PrincipalRow)) == 2
        assert (
            await session.get(
                HumanIdentityLinkRow, (proof.identity.authority.value, proof.identity.subject.value)
            )
            is None
        )
        assert (
            await session.get(
                HumanCredentialVersionRow,
                (
                    seed.binding.installation_id.value,
                    proof.identity.authority.value,
                    proof.identity.subject.value,
                ),
            )
            is None
        )
        assert (
            await session.scalar(select(func.count()).select_from(IdempotencyReservationRow))
            == reservations_before
        )
        assert (
            await session.scalar(select(func.count()).select_from(AccessAuditEventRow))
            == audits_before
        )
        assert (
            await session.scalar(
                select(OrganizationRow.access_revision).where(
                    OrganizationRow.id == seed.organization_id.value
                )
            )
            == issued.access_revision
        )
        assert (
            await session.scalar(
                select(ProjectRow.access_revision).where(ProjectRow.id == project.project_id.value)
            )
            == account.access_revision
        )
        retained = await PostgresInvitationFactsReader(session).read_by_digest(
            issued.token.digest()
        )
        assert retained is not None and retained.revoked_at is None and retained.consumed_at is None


async def test_preview_observes_recovery_for_unlinked_identity(database: Database) -> None:
    seed = await seed_project_creator(database)
    record, token, _ = await _issue(database, seed=seed)
    proof = _unadmitted_invitation_proof(seed)
    async with database.session() as session, session.begin():
        await PostgresIdentityRecoveryAdmissionWriter(
            session,
            installation_id=seed.binding.installation_id,
            authority=proof.identity.authority,
        ).reserve(
            IdentityRecoveryEventDTO(
                flow_id=IdentityRecoveryFlowId(uuid4()),
                identity=proof.identity,
                event_kind=IdentityRecoveryEventKind.RECOVERY,
            )
        )
    async with database.session() as session:
        with pytest.raises(ConflictError):
            await _preview_service(session).preview(
                proof=proof, query=PreviewInvitationQuery(token=token)
            )
    async with database.session() as session:
        assert (
            await session.get(
                HumanIdentityLinkRow, (proof.identity.authority.value, proof.identity.subject.value)
            )
            is None
        )
        assert await PostgresInvitationFactsReader(session).read_by_digest(token.digest()) == record
        assert await session.scalar(select(func.count()).select_from(PrincipalRow)) == 1


async def test_preview_rejects_delivered_target_deletion_without_partial_scope(
    database: Database,
) -> None:
    seed = await seed_project_creator(database)
    project = await _new_project(database, seed, "support")
    group = (
        await create_group(
            database, seed.access, project.project_id, revision=project.access_revision
        )
    ).group
    assignments = (
        InvitationProjectMembershipIntentDTO(project_id=project.project_id),
        InvitationGroupMembershipIntentDTO(
            project_id=project.project_id, access_group_id=group.group_id
        ),
    )
    command = await _review(database, seed, assignments, (project.project_id,))
    async with database.session() as session:
        issued = await _administration(session).issue(
            access=seed.access, command=command, context=_context("preview-before-target-deletion")
        )
    assert issued.token is not None
    await delete_group(database, seed.access, group, group.access_revision)
    async with database.session() as session:
        with pytest.raises(ConflictError):
            await _preview_service(session).preview(
                proof=_unadmitted_invitation_proof(seed),
                query=PreviewInvitationQuery(token=issued.token),
            )
    async with database.session() as session:
        retained = await PostgresInvitationFactsReader(session).read_by_digest(
            issued.token.digest()
        )
        assert retained is not None and retained.consumed_at is None
        assert await session.scalar(select(func.count()).select_from(PrincipalRow)) == 1


@pytest.mark.parametrize("suspended", [False, True])
async def test_preview_reads_current_linked_human_without_admission_repair(
    database: Database, suspended: bool
) -> None:
    seed = await seed_membership_project(database)
    record, token, _ = await _issue(database, seed=seed.actor)
    proof = InvitationBrowserProofDTO(
        identity=VerifiedHumanIdentityDTO(
            authority=seed.actor.binding.identity.authority,
            subject=IdentitySubject(str(UUID(int=200))),
        ),
        password_completed=None,
    )
    if suspended:
        async with database.session() as session, session.begin():
            await session.execute(
                update(PrincipalRow)
                .where(PrincipalRow.id == seed.bob_id.value)
                .values(status=PrincipalStatus.SUSPENDED)
            )
    async with database.session() as session:
        if suspended:
            with pytest.raises(ConflictError):
                await _preview_service(session).preview(
                    proof=proof, query=PreviewInvitationQuery(token=token)
                )
        else:
            result = await _preview_service(session).preview(
                proof=proof, query=PreviewInvitationQuery(token=token)
            )
            assert result.invitation_id == record.invitation_id and len(result.scopes) == 1
    async with database.session() as session:
        bob = await session.get(PrincipalRow, seed.bob_id.value)
        assert bob is not None and bob.status == (
            PrincipalStatus.SUSPENDED if suspended else PrincipalStatus.ACTIVE
        )
        assert await PostgresInvitationFactsReader(session).read_by_digest(token.digest()) == record


@pytest.mark.parametrize("has_version", [False, True])
async def test_preview_distinguishes_released_history_from_missing_current_version(
    database: Database, has_version: bool
) -> None:
    seed = await seed_project_creator(database)
    record, token, _ = await _issue(database, seed=seed)
    proof = _unadmitted_invitation_proof(seed)
    async with database.session() as session, session.begin():
        # Seed a retained released receipt as in the existing directory/security SQL cases.
        history = IdentityRecoveryAdmissionRow(
            operation_id=str(uuid4()),
            installation_id=seed.binding.installation_id.value,
            authority=proof.identity.authority.value,
            flow_id=uuid4(),
            subject=proof.identity.subject.value,
            event_kind=IdentityRecoveryEventKind.RECOVERY,
        )
        history.kratos_cleanup_state = IdentityRecoveryCleanupState.CONFIRMED
        history.hydra_cleanup_state = IdentityRecoveryCleanupState.CONFIRMED
        history.released_at = datetime.now(UTC)
        session.add(history)
        if has_version:
            session.add(
                HumanCredentialVersionRow(
                    installation_id=seed.binding.installation_id.value,
                    authority=proof.identity.authority.value,
                    subject=proof.identity.subject.value,
                    version=2,
                )
            )
    async with database.session() as session:
        if has_version:
            result = await _preview_service(session).preview(
                proof=proof, query=PreviewInvitationQuery(token=token)
            )
            assert result.invitation_id == record.invitation_id
        else:
            with pytest.raises(DependencyUnavailableError):
                await _preview_service(session).preview(
                    proof=proof, query=PreviewInvitationQuery(token=token)
                )
    async with database.session() as session:
        version = await session.get(
            HumanCredentialVersionRow,
            (
                seed.binding.installation_id.value,
                proof.identity.authority.value,
                proof.identity.subject.value,
            ),
        )
        assert (version.version if version is not None else None) == (2 if has_version else None)
        assert (
            await session.get(
                HumanIdentityLinkRow, (proof.identity.authority.value, proof.identity.subject.value)
            )
            is None
        )


@pytest.mark.parametrize("kind", ["group", "application"])
async def test_preview_cannot_reparent_a_real_target_through_stored_selectors(
    database: Database, kind: str
) -> None:
    seed = await seed_project_creator(database)
    support = await _new_project(database, seed, "support")
    sales = await _new_project(database, seed, "sales")
    if kind == "group":
        group = (
            await create_group(
                database, seed.access, sales.project_id, revision=sales.access_revision
            )
        ).group
        original_effect: InvitationAssignmentDTO = InvitationGroupMembershipIntentDTO(
            project_id=sales.project_id, access_group_id=group.group_id
        )
        changed_effect: InvitationAssignmentDTO = replace(
            original_effect, project_id=support.project_id
        )
    else:
        account = (
            await create_account(
                database, seed.access, sales.project_id, revision=sales.access_revision
            )
        ).account
        original_effect = InvitationActionGrantIntentDTO(
            target=ApplicationAccountGrantTargetDTO(
                project_id=sales.project_id, application_principal_id=account.principal_id
            ),
            action_id=ActionId("issue-application-keys"),
            can_grant=True,
        )
        changed_effect = replace(
            original_effect,
            target=ApplicationAccountGrantTargetDTO(
                project_id=support.project_id, application_principal_id=account.principal_id
            ),
        )
    original_intent = (
        InvitationProjectMembershipIntentDTO(project_id=sales.project_id),
        original_effect,
    )
    command = await _review(database, seed, original_intent, (sales.project_id,))
    async with database.session() as session:
        issued = await _administration(session).issue(
            access=seed.access, command=command, context=_context("preview-reparent-guard")
        )
    assert issued.token is not None
    async with database.session() as session, session.begin():
        # Corrupt retained selectors cannot reparent an immutable actual resource.
        await session.execute(
            update(InvitationRow)
            .where(InvitationRow.id == issued.invitation_id.value)
            .values(
                assignments=PostgresInvitationMapper.to_payload(
                    (
                        InvitationProjectMembershipIntentDTO(project_id=support.project_id),
                        changed_effect,
                    )
                )
            )
        )
    async with database.session() as session:
        with pytest.raises(ConflictError):
            await _preview_service(session).preview(
                proof=_unadmitted_invitation_proof(seed),
                query=PreviewInvitationQuery(token=issued.token),
            )


async def test_preview_unknown_digest_returns_no_scope_or_identity_state_changes(
    database: Database,
) -> None:
    seed = await seed_project_creator(database)
    async with database.session() as session:
        with pytest.raises(ResourceNotFoundError):
            await _preview_service(session).preview(
                proof=_unadmitted_invitation_proof(seed),
                query=PreviewInvitationQuery(token=InvitationToken("B" + "A" * 42)),
            )
    async with database.session() as session:
        assert await session.scalar(select(func.count()).select_from(PrincipalRow)) == 1
        assert await session.scalar(select(func.count()).select_from(InvitationRow)) == 0
        assert (
            await session.scalar(select(func.count()).select_from(IdempotencyReservationRow)) == 0
        )


async def test_activation_facts_observe_current_recipient_and_database_time(
    database: Database,
) -> None:
    seed = await seed_project_creator(database)
    record, token, _ = await _issue(database, seed=seed)
    proof = _unadmitted_invitation_proof(seed)
    async with database.session() as session, session.begin():
        before = await session.scalar(select(func.clock_timestamp(type_=DateTime(timezone=True))))
        facts = await PostgresInvitationAssignmentFactsReader(session).lock_for_activation(
            identity=proof.identity, digest=token.digest()
        )
        after = await session.scalar(select(func.clock_timestamp(type_=DateTime(timezone=True))))
        assert facts is not None and before is not None and after is not None
        assert facts.invitation == record and facts.principal is None
        assert facts.credential_state.identity == proof.identity
        assert (
            facts.credential_state.version is None
            and not facts.credential_state.has_pending_recovery
        )
        assert not facts.has_credential_history and not facts.project_memberships
        assert facts.organization_access_revision == record.issued_access_revision
        assert before <= facts.current_time <= after
        assert (
            await session.scalar(
                select(func.count())
                .select_from(HumanIdentityLinkRow)
                .where(
                    HumanIdentityLinkRow.authority == proof.identity.authority.value,
                    HumanIdentityLinkRow.subject == proof.identity.subject.value,
                )
            )
            == 0
        )


async def test_activation_issuer_observes_retained_principal_without_issuer_session(
    database: Database,
) -> None:
    seed = await seed_project_creator(database)
    record, _, _ = await _issue(database, seed=seed)
    async with database.session() as session, session.begin():
        await session.scalar(
            select(OrganizationRow.id)
            .where(OrganizationRow.id == record.organization_id.value)
            .with_for_update()
        )
        facts = await PostgresInvitationAssignmentFactsReader(session).read_current_issuer(
            invitation=record
        )
        assert facts is not None and facts.has_coherent_identity
        assert facts.organization_access.principal.id == record.issuer_principal_id
        assert facts.organization_access.access_revision == record.issued_access_revision
        assert not facts.organization_access.has_pending_recovery
        assert any(
            grant.action_id.value == OrganizationAction.ADMIT_USERS.value
            for grant in facts.organization_access.grants
        )
        assert tuple(item.intent for item in facts.assignments) == record.assignments
        assert facts.assignments[0].target_exists and facts.assignments[0].project is None


async def test_activation_original_is_absent_before_recipient_business_completion(
    database: Database,
) -> None:
    seed = await seed_project_creator(database)
    record, token, _ = await _issue(database, seed=seed)
    proof = _unadmitted_invitation_proof(seed)
    context = IdempotencyContextDTO(
        method=HttpMethod.POST,
        requested_route="/v1/invitations/activate",
        key=IdempotencyKey("fresh-activation"),
    )
    fingerprint = InvitationFingerprintService(
        RequestFingerprintService(RequestFingerprintKey(b"F" * 32))
    ).for_activation(ActivateInvitationCommand(token=token), invitation_id=record.invitation_id)
    async with database.session() as session, session.begin():
        facts = await PostgresHumanAdmissionFactsReader(session).read_for_admission(
            access=seed.access, organization_id=seed.organization_id, identity=proof.identity
        )
        assert facts is not None and facts.principal is None
        result = await PostgresInvitationWriter(session).read_activation_original(
            installation_id=facts.installation_id,
            identity=proof.identity,
            organization_id=record.organization_id,
            invitation_id=record.invitation_id,
            principal_id=None,
            context=context,
            fingerprint=fingerprint,
        )
        assert result is None


async def test_activation_reservation_retains_exact_pre_admission_identity_and_intent(
    database: Database,
) -> None:
    seed = await seed_project_creator(database)
    record, token, _ = await _issue(database, seed=seed)
    proof = _unadmitted_invitation_proof(seed)
    context = IdempotencyContextDTO(
        method=HttpMethod.POST,
        requested_route="/v1/invitations/activate",
        key=IdempotencyKey("fresh-activation"),
    )
    fingerprint = InvitationFingerprintService(
        RequestFingerprintService(RequestFingerprintKey(b"F" * 32))
    ).for_activation(ActivateInvitationCommand(token=token), invitation_id=record.invitation_id)
    async with database.session() as session, session.begin():
        facts = await PostgresHumanAdmissionFactsReader(session).read_for_admission(
            access=seed.access, organization_id=seed.organization_id, identity=proof.identity
        )
        assert facts is not None and facts.principal is None
        binding = await PostgresInvitationWriter(session).reserve_activation(
            installation_id=facts.installation_id,
            identity=proof.identity,
            invitation=record,
            principal_id=None,
            context=context,
            fingerprint=fingerprint,
        )
        assert binding.operation_id != record.issued_operation_id
        assert (
            binding.installation_id == facts.installation_id and binding.identity == proof.identity
        )
        assert (
            binding.organization_id == record.organization_id
            and binding.invitation_id == record.invitation_id
        )
        assert (
            binding.issuer_principal_id == record.issuer_principal_id
            and binding.principal_id is None
        )
        assert binding.context == context and binding.fingerprint == fingerprint


@pytest.mark.parametrize("isolation", ["REPEATABLE READ", "SERIALIZABLE"])
async def test_activation_observation_rejects_stale_snapshot_isolation(
    database: Database, isolation: str
) -> None:
    seed = await seed_project_creator(database)
    _, token, _ = await _issue(database, seed=seed)
    async with database.session() as session, session.begin():
        await session.connection(execution_options={"isolation_level": isolation})
        with pytest.raises(RuntimeError, match="READ COMMITTED"):
            await PostgresInvitationAssignmentFactsReader(session).lock_for_activation(
                identity=_unadmitted_invitation_proof(seed).identity, digest=token.digest()
            )


@pytest.mark.parametrize(
    "state",
    ["active", "suspended", "recovery", "history-missing-version", "history-current-version"],
)
async def test_activation_issuer_uses_current_record_coherence_and_recovery(
    database: Database, state: str
) -> None:
    seed = await seed_project_creator(database)
    record, _, _ = await _issue(database, seed=seed)
    async with database.session() as session, session.begin():
        if state == "suspended":
            await session.execute(
                update(PrincipalRow)
                .where(PrincipalRow.id == record.issuer_principal_id.value)
                .values(status=PrincipalStatus.SUSPENDED)
            )
        if state in {"recovery", "history-missing-version", "history-current-version"}:
            history = IdentityRecoveryAdmissionRow(
                operation_id=str(uuid4()),
                installation_id=seed.binding.installation_id.value,
                authority=seed.binding.identity.authority.value,
                subject=seed.binding.identity.subject.value,
                flow_id=uuid4(),
                event_kind=IdentityRecoveryEventKind.RECOVERY,
            )
            if state != "recovery":
                history.kratos_cleanup_state = IdentityRecoveryCleanupState.CONFIRMED
                history.hydra_cleanup_state = IdentityRecoveryCleanupState.CONFIRMED
                history.released_at = datetime.now(UTC)
            session.add(history)
        if state == "history-missing-version":
            await session.execute(
                delete(HumanCredentialVersionRow).where(
                    HumanCredentialVersionRow.installation_id == seed.binding.installation_id.value,
                    HumanCredentialVersionRow.authority == seed.binding.identity.authority.value,
                    HumanCredentialVersionRow.subject == seed.binding.identity.subject.value,
                )
            )
    async with database.session() as session, session.begin():
        await session.scalar(
            select(OrganizationRow.id)
            .where(OrganizationRow.id == seed.organization_id.value)
            .with_for_update()
        )
        facts = await PostgresInvitationAssignmentFactsReader(session).read_current_issuer(
            invitation=record
        )
        assert facts is not None
        assert facts.has_coherent_identity is (state != "history-missing-version")
        assert facts.organization_access.has_pending_recovery is (state == "recovery")
        assert facts.organization_access.principal.status is (
            PrincipalStatus.SUSPENDED if state == "suspended" else PrincipalStatus.ACTIVE
        )
        assert facts.organization_access.oauth_credential_facts is None


async def test_activation_pending_namespace_binds_invitation_meaning_without_a_second_key_space(
    database: Database,
) -> None:
    seed = await seed_project_creator(database)
    record, token, _ = await _issue(database, seed=seed)
    command = await _review(database, seed, (InvitationAdmissionOnlyIntentDTO(),))
    async with database.session() as session:
        second = await _administration(session).issue(
            access=seed.access, command=command, context=_context("second-invitation")
        )
    assert second.token is not None
    proof = _unadmitted_invitation_proof(seed)
    context = IdempotencyContextDTO(
        method=HttpMethod.POST,
        requested_route="/v1/invitations/activate",
        key=IdempotencyKey("original-activation"),
    )
    fingerprints = InvitationFingerprintService(
        RequestFingerprintService(RequestFingerprintKey(b"F" * 32))
    )
    fingerprint = fingerprints.for_activation(
        ActivateInvitationCommand(token=token), invitation_id=record.invitation_id
    )
    async with database.session() as session, session.begin():
        facts = await PostgresHumanAdmissionFactsReader(session).read_for_admission(
            access=seed.access, organization_id=seed.organization_id, identity=proof.identity
        )
        assert facts is not None
        writer = PostgresInvitationWriter(session)
        original = await writer.reserve_activation(
            installation_id=facts.installation_id,
            identity=proof.identity,
            invitation=record,
            principal_id=None,
            context=context,
            fingerprint=fingerprint,
        )
        assert original.principal_id is None
        with pytest.raises(IdempotencyInProgressError) as busy:
            await writer.read_activation_original(
                installation_id=facts.installation_id,
                identity=proof.identity,
                organization_id=record.organization_id,
                invitation_id=record.invitation_id,
                principal_id=None,
                context=context,
                fingerprint=fingerprint,
            )
        assert busy.value.operation_id == original.operation_id
        other = await PostgresInvitationFactsReader(session).read_by_digest(second.token.digest())
        assert other is not None
        with pytest.raises(IdempotencyKeyReusedError):
            await writer.reserve_activation(
                installation_id=facts.installation_id,
                identity=proof.identity,
                invitation=other,
                principal_id=None,
                context=context,
                fingerprint=fingerprints.for_activation(
                    ActivateInvitationCommand(token=second.token), invitation_id=other.invitation_id
                ),
            )
        assert (
            await session.scalar(select(func.count()).select_from(InvitationActivationOperationRow))
            == 1
        )
        stored = await session.get(InvitationActivationOperationRow, original.operation_id.value)
        assert stored is not None and stored.state is OperationReservationState.IN_PROGRESS
        assert (
            stored.principal_id is None
            and stored.completed_at is None
            and stored.expires_at is None
        )
        assert (
            stored.organization_access_revision is None and stored.project_access_revisions is None
        )


async def test_completed_activation_reader_survives_invitation_expiry_issuer_loss_and_target_deletion(
    database: Database,
) -> None:
    seed = await seed_membership_project(database)
    group = (
        await create_group(
            database,
            seed.actor.access,
            seed.project.project_id,
            revision=seed.project.access_revision,
        )
    ).group
    intent = InvitationGroupMembershipIntentDTO(
        project_id=seed.project.project_id, access_group_id=group.group_id
    )
    command = await _review(database, seed.actor, (intent,), (seed.project.project_id,))
    async with database.session() as session:
        issued = await _administration(session).issue(
            access=seed.actor.access, command=command, context=_context("retained-activation")
        )
    assert issued.token is not None
    proof = InvitationBrowserProofDTO(
        identity=VerifiedHumanIdentityDTO(
            authority=seed.actor.binding.identity.authority,
            subject=IdentitySubject(str(UUID(int=200))),
        ),
        password_completed=None,
    )
    context = IdempotencyContextDTO(
        method=HttpMethod.POST,
        requested_route="/v1/invitations/activate",
        key=IdempotencyKey("retained-activation"),
    )
    fingerprints = InvitationFingerprintService(
        RequestFingerprintService(RequestFingerprintKey(b"F" * 32))
    )
    fingerprint = fingerprints.for_activation(
        ActivateInvitationCommand(token=issued.token), invitation_id=issued.invitation_id
    )
    await delete_group(database, seed.actor.access, group, group.access_revision)
    async with database.session() as session, session.begin():
        # Seed a completed original to qualify this read independently of the still-stubbed completion writer.
        now = await session.scalar(select(func.clock_timestamp(type_=DateTime(timezone=True))))
        assert now is not None
        expiry = now + timedelta(hours=24)
        row = InvitationActivationOperationRow(
            operation_id="retained-activation-original",
            installation_id=seed.actor.binding.installation_id.value,
            authority=proof.identity.authority.value,
            subject=proof.identity.subject.value,
            organization_id=seed.actor.organization_id.value,
            invitation_id=issued.invitation_id.value,
            issuer_principal_id=seed.actor.access.actor_principal_id.value,
            principal_id=seed.bob_id.value,
            method=context.method.value,
            requested_route=context.requested_route,
            request_key=context.key.value,
            request_fingerprint=fingerprint.value,
            completed_at=now,
            expires_at=expiry,
            organization_access_revision=issued.access_revision,
            project_access_revisions=[
                {
                    "projectId": str(seed.project.project_id.value),
                    "accessRevision": group.access_revision,
                }
            ],
        )
        row.state = OperationReservationState.REPLAYABLE
        session.add(row)
        old = now - timedelta(days=8)
        await session.execute(
            update(InvitationRow)
            .where(InvitationRow.id == issued.invitation_id.value)
            .values(
                issued_at=old,
                expires_at=old + timedelta(days=7),
                consumed_at=old + timedelta(days=1),
                consumed_by_principal_id=seed.bob_id.value,
            )
        )
        await session.execute(
            update(PrincipalRow)
            .where(PrincipalRow.id == seed.actor.access.actor_principal_id.value)
            .values(status=PrincipalStatus.SUSPENDED)
        )
        await session.execute(
            delete(OrganizationActionGrantRow).where(
                OrganizationActionGrantRow.recipient_principal_id
                == seed.actor.access.actor_principal_id.value
            )
        )
        await session.execute(
            delete(IdempotencyReservationRow).where(
                IdempotencyReservationRow.operation_id
                == (
                    await session.scalar(
                        select(InvitationRow.issued_operation_id).where(
                            InvitationRow.id == issued.invitation_id.value
                        )
                    )
                )
            )
        )
    async with database.session() as session:
        service = InvitationActivationService(
            transaction_manager=SqlAlchemyTransactionManager(session),
            invitation_assignment_facts_reader=PostgresInvitationAssignmentFactsReader(session),
            invitation_activation_operation_store=PostgresInvitationWriter(session),
            invitation_fingerprint_service=fingerprints,
            invitation_admission_writer=PostgresHumanAdmissionWriter(session),
            invitation_assignment_service=_assignment_service(session),
        )
        result = await service.activate(
            proof=proof, command=ActivateInvitationCommand(token=issued.token), context=context
        )
        assert result.principal_id == seed.bob_id and result.invitation_id == issued.invitation_id
        assert (
            result.operation.operation_id.value == "retained-activation-original"
            and result.operation.created is False
        )
        assert (
            result.operation.expires_at == expiry
            and result.organization_access_revision == issued.access_revision
        )
        assert result.project_access_revisions == (
            InvitationProjectAccessRevisionDTO(
                project_id=seed.project.project_id, access_revision=group.access_revision
            ),
        )
    async with database.session() as session:
        stored = await session.get(InvitationActivationOperationRow, "retained-activation-original")
        assert stored is not None and stored.expires_at == expiry and stored.completed_at == now
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AccessAuditEventRow)
                .where(AccessAuditEventRow.correlation_id == stored.operation_id)
            )
            == 0
        )


@pytest.mark.parametrize(
    "invalid", ["completed-without-recipient", "pending-with-expiry", "completion-expiry-equality"]
)
async def test_activation_storage_rejects_incoherent_pending_or_completed_outcomes(
    database: Database, invalid: str
) -> None:
    seed = await seed_project_creator(database)
    record, token, _ = await _issue(database, seed=seed)
    proof = _unadmitted_invitation_proof(seed)
    context = IdempotencyContextDTO(
        method=HttpMethod.POST,
        requested_route="/v1/invitations/activate",
        key=IdempotencyKey("invalid-original"),
    )
    fingerprint = InvitationFingerprintService(
        RequestFingerprintService(RequestFingerprintKey(b"F" * 32))
    ).for_activation(ActivateInvitationCommand(token=token), invitation_id=record.invitation_id)
    async with database.session() as session:
        with pytest.raises(IntegrityError):
            async with session.begin():
                now = await session.scalar(
                    select(func.clock_timestamp(type_=DateTime(timezone=True)))
                )
                assert now is not None
                row = InvitationActivationOperationRow(
                    operation_id=str(uuid4()),
                    installation_id=seed.binding.installation_id.value,
                    authority=proof.identity.authority.value,
                    subject=proof.identity.subject.value,
                    organization_id=seed.organization_id.value,
                    invitation_id=record.invitation_id.value,
                    issuer_principal_id=record.issuer_principal_id.value,
                    principal_id=None,
                    method=context.method.value,
                    requested_route=context.requested_route,
                    request_key=context.key.value,
                    request_fingerprint=fingerprint.value,
                )
                row.expires_at = now + timedelta(hours=24)
                if invalid != "pending-with-expiry":
                    row.state = OperationReservationState.REPLAYABLE
                    row.completed_at = now
                    row.organization_access_revision = record.issued_access_revision
                    row.project_access_revisions = []
                if invalid == "completion-expiry-equality":
                    row.principal_id = seed.access.actor_principal_id.value
                    row.expires_at = now
                session.add(row)
                await session.flush()


@pytest.mark.parametrize(
    "state", ["pending", "released-missing-version", "released-current-version"]
)
async def test_activation_recipient_observes_exact_recovery_and_current_credential_history(
    database: Database, state: str
) -> None:
    seed = await seed_project_creator(database)
    _, token, _ = await _issue(database, seed=seed)
    proof = _unadmitted_invitation_proof(seed)
    async with database.session() as session, session.begin():
        history = IdentityRecoveryAdmissionRow(
            operation_id=str(uuid4()),
            installation_id=seed.binding.installation_id.value,
            authority=proof.identity.authority.value,
            subject=proof.identity.subject.value,
            flow_id=uuid4(),
            event_kind=IdentityRecoveryEventKind.RECOVERY,
        )
        if state != "pending":
            history.kratos_cleanup_state = IdentityRecoveryCleanupState.CONFIRMED
            history.hydra_cleanup_state = IdentityRecoveryCleanupState.CONFIRMED
            history.released_at = datetime.now(UTC)
        session.add(history)
        if state == "released-current-version":
            session.add(
                HumanCredentialVersionRow(
                    installation_id=seed.binding.installation_id.value,
                    authority=proof.identity.authority.value,
                    subject=proof.identity.subject.value,
                    version=2,
                )
            )
    async with database.session() as session, session.begin():
        facts = await PostgresInvitationAssignmentFactsReader(session).lock_for_activation(
            identity=proof.identity, digest=token.digest()
        )
        assert facts is not None and facts.principal is None and facts.has_credential_history
        assert facts.credential_state.identity == proof.identity
        assert facts.credential_state.has_pending_recovery is (state == "pending")
        assert (
            facts.credential_state.version.value if facts.credential_state.version else None
        ) == (2 if state == "released-current-version" else None)
        assert (
            await session.scalar(
                select(func.count())
                .select_from(HumanIdentityLinkRow)
                .where(
                    HumanIdentityLinkRow.authority == proof.identity.authority.value,
                    HumanIdentityLinkRow.subject == proof.identity.subject.value,
                )
            )
            == 0
        )


async def test_activation_rereads_database_time_and_expiry_after_coordination_wait(
    database: Database,
) -> None:
    seed = await seed_project_creator(database)
    record, token, _ = await _issue(database, seed=seed)
    proof = _unadmitted_invitation_proof(seed)
    started: asyncio.Future[tuple[int, datetime]] = asyncio.get_running_loop().create_future()

    async def read_after_wait() -> InvitationActivationFactsDTO | None:
        async with database.session() as session, session.begin():
            pid = await session.scalar(select(func.pg_backend_pid()))
            beginning = await session.scalar(
                select(func.transaction_timestamp(type_=DateTime(timezone=True)))
            )
            assert isinstance(pid, int) and beginning is not None
            started.set_result((pid, beginning))
            return await PostgresInvitationAssignmentFactsReader(session).lock_for_activation(
                identity=proof.identity, digest=token.digest()
            )

    task: asyncio.Task[InvitationActivationFactsDTO | None] | None = None
    try:
        async with database.session() as holder, holder.begin():
            holder_pid = await holder.scalar(select(func.pg_backend_pid()))
            assert isinstance(holder_pid, int)
            await holder.scalar(
                select(OrganizationRow.id)
                .where(OrganizationRow.id == seed.organization_id.value)
                .with_for_update()
            )
            task = asyncio.create_task(read_after_wait())
            reader_pid, beginning = await started
            async with asyncio.timeout(2), database.session() as observer:
                while True:
                    blockers = await observer.scalar(
                        select(func.pg_blocking_pids(reader_pid, type_=ARRAY(Integer)))
                    )
                    if blockers is not None and holder_pid in blockers:
                        break
                    await asyncio.sleep(0.01)
            expiry = await holder.scalar(
                select(func.clock_timestamp(type_=DateTime(timezone=True)))
            )
            assert expiry is not None and beginning < expiry
            await holder.execute(
                update(InvitationRow)
                .where(InvitationRow.id == record.invitation_id.value)
                .values(expires_at=expiry)
            )
            await holder.execute(
                update(OrganizationRow)
                .where(OrganizationRow.id == seed.organization_id.value)
                .values(access_revision=OrganizationRow.access_revision + 1)
            )
        async with asyncio.timeout(2):
            facts = await task
        assert facts is not None and facts.invitation.expires_at == expiry
        assert facts.current_time >= expiry and facts.current_time > beginning
        assert facts.organization_access_revision == record.issued_access_revision + 1
        assert not InvitationPolicy.may_consume(
            expires_at=facts.invitation.expires_at,
            current_time=facts.current_time,
            revoked_at=None,
            consumed_at=None,
        )
    finally:
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


async def test_activation_service_admits_new_human_and_retains_one_atomic_original(
    database: Database,
) -> None:
    seed = await seed_project_creator(database)
    record, token, _ = await _issue(database, seed=seed)
    proof = replace(_unadmitted_invitation_proof(seed), password_completed=True)
    context = IdempotencyContextDTO(
        method=HttpMethod.POST,
        requested_route="/v1/invitations/activate",
        key=IdempotencyKey("new-human-activation"),
    )
    fingerprints = InvitationFingerprintService(
        RequestFingerprintService(RequestFingerprintKey(b"F" * 32))
    )
    async with database.session() as session:
        service = InvitationActivationService(
            transaction_manager=SqlAlchemyTransactionManager(session),
            invitation_assignment_facts_reader=PostgresInvitationAssignmentFactsReader(session),
            invitation_activation_operation_store=PostgresInvitationWriter(session),
            invitation_fingerprint_service=fingerprints,
            invitation_admission_writer=PostgresHumanAdmissionWriter(session),
            invitation_assignment_service=_assignment_service(session),
        )
        result = await service.activate(
            proof=proof, command=ActivateInvitationCommand(token=token), context=context
        )
    assert (
        result.organization_id == record.organization_id
        and result.invitation_id == record.invitation_id
    )
    assert result.principal_id != record.issuer_principal_id
    assert result.organization_access_revision == record.issued_access_revision + 1
    assert result.project_access_revisions == ()
    assert (
        result.operation.created is True
        and result.operation.replay_kind is OperationReplayKind.SAFE_RESULT
    )
    async with database.session() as session:
        principal = await session.get(PrincipalRow, result.principal_id.value)
        link = await session.get(
            HumanIdentityLinkRow, (proof.identity.authority.value, proof.identity.subject.value)
        )
        version = await session.get(
            HumanCredentialVersionRow,
            (
                seed.binding.installation_id.value,
                proof.identity.authority.value,
                proof.identity.subject.value,
            ),
        )
        consumed = await session.get(InvitationRow, record.invitation_id.value)
        operation = await session.get(
            InvitationActivationOperationRow, result.operation.operation_id.value
        )
        organization = await session.get(OrganizationRow, record.organization_id.value)
        assert principal is not None and principal.organization_id == record.organization_id.value
        assert principal.kind is PrincipalKind.HUMAN and principal.status is PrincipalStatus.ACTIVE
        assert (
            link is not None
            and link.principal_id == principal.id
            and link.organization_id == principal.organization_id
        )
        assert version is not None and version.version == 1
        assert (
            consumed is not None
            and consumed.consumed_at is not None
            and consumed.consumed_by_principal_id == principal.id
        )
        assert operation is not None and operation.principal_id == principal.id
        assert (
            operation.state is OperationReservationState.REPLAYABLE
            and operation.completed_at is not None
        )
        assert (
            operation.expires_at
            == operation.completed_at + timedelta(hours=24)
            == result.operation.expires_at
        )
        assert (
            operation.organization_access_revision == result.organization_access_revision
            and operation.project_access_revisions == []
        )
        assert (
            organization is not None
            and organization.access_revision == result.organization_access_revision
        )
        audits = (
            await session.scalars(
                select(AccessAuditEventRow).where(
                    AccessAuditEventRow.correlation_id == result.operation.operation_id.value
                )
            )
        ).all()
        assert len(audits) == 2
        admission = next(audit for audit in audits if audit.event_type == "human_admitted")
        assert (
            admission.actor_principal_id == record.issuer_principal_id.value
            and admission.affected_principal_id == principal.id
        )
        assert admission.before_values == {
            "access_revision": record.issued_access_revision,
            "admitted": False,
        }
        assert admission.after_values == {
            "access_revision": result.organization_access_revision,
            "admitted": True,
        }
        completion = next(audit for audit in audits if audit.target_kind == "invitation")
        assert (
            completion.target_id == record.invitation_id.value
            and completion.actor_principal_id == principal.id
        )
        assert completion.affected_principal_id == principal.id
        assert await session.scalar(select(func.count()).select_from(PrincipalRow)) == 2
    async with database.session() as session:
        service = InvitationActivationService(
            transaction_manager=SqlAlchemyTransactionManager(session),
            invitation_assignment_facts_reader=PostgresInvitationAssignmentFactsReader(session),
            invitation_activation_operation_store=PostgresInvitationWriter(session),
            invitation_fingerprint_service=fingerprints,
            invitation_admission_writer=PostgresHumanAdmissionWriter(session),
            invitation_assignment_service=_assignment_service(session),
        )
        replay = await service.activate(
            proof=replace(proof, password_completed=None),
            command=ActivateInvitationCommand(token=token),
            context=context,
        )
    assert replay == replace(result, operation=replace(result.operation, created=False))
    async with database.session() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AccessAuditEventRow)
                .where(AccessAuditEventRow.correlation_id == result.operation.operation_id.value)
            )
            == 2
        )
        assert (
            await session.scalar(
                select(OrganizationRow.access_revision).where(
                    OrganizationRow.id == record.organization_id.value
                )
            )
            == result.organization_access_revision
        )


async def test_activation_binding_keeps_real_already_admitted_recipient_and_pending_namespace(
    database: Database,
) -> None:
    seed = await seed_membership_project(database)
    record, token, _ = await _issue(database, seed=seed.actor)
    proof = InvitationBrowserProofDTO(
        identity=VerifiedHumanIdentityDTO(
            authority=seed.actor.binding.identity.authority,
            subject=IdentitySubject(str(UUID(int=200))),
        ),
        password_completed=True,
    )
    context = IdempotencyContextDTO(
        method=HttpMethod.POST,
        requested_route="/v1/invitations/activate",
        key=IdempotencyKey("bind-existing-human"),
    )
    fingerprint = InvitationFingerprintService(
        RequestFingerprintService(RequestFingerprintKey(b"F" * 32))
    ).for_activation(ActivateInvitationCommand(token=token), invitation_id=record.invitation_id)
    async with database.session() as session, session.begin():
        reader = PostgresInvitationAssignmentFactsReader(session)
        facts = await reader.lock_for_activation(identity=proof.identity, digest=token.digest())
        issuer = await reader.read_current_issuer(invitation=record)
        assert (
            facts is not None and facts.principal is not None and facts.principal.id == seed.bob_id
        )
        assert (
            issuer is not None
            and issuer.has_coherent_identity
            and not issuer.organization_access.has_pending_recovery
        )
        assert any(
            grant.action_id.value == OrganizationAction.ADMIT_USERS.value
            for grant in issuer.organization_access.grants
        )
        writer = PostgresInvitationWriter(session)
        binding = await writer.reserve_activation(
            installation_id=facts.credential_state.installation_id,
            identity=proof.identity,
            invitation=record,
            principal_id=facts.principal.id,
            context=context,
            fingerprint=fingerprint,
        )
        # Existing native admission supplies the real identity link. Binding is isolated here from new account creation.
        bound = await writer.bind_activation_principal(binding=binding, principal=facts.principal)
        assert bound == binding and bound.principal_id == seed.bob_id
        stored = await session.get(InvitationActivationOperationRow, binding.operation_id.value)
        assert stored is not None and stored.principal_id == seed.bob_id.value
        assert (
            stored.authority == proof.identity.authority.value
            and stored.subject == proof.identity.subject.value
        )
        assert (
            stored.state is OperationReservationState.IN_PROGRESS
            and stored.expires_at is None
            and stored.completed_at is None
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AccessAuditEventRow)
                .where(AccessAuditEventRow.correlation_id == binding.operation_id.value)
            )
            == 0
        )
        assert (
            await session.scalar(
                select(OrganizationRow.access_revision).where(
                    OrganizationRow.id == seed.actor.organization_id.value
                )
            )
            == facts.organization_access_revision
        )


async def test_activation_completion_consumes_real_bound_intent_and_captures_original_expiry(
    database: Database,
) -> None:
    seed = await seed_membership_project(database)
    record, token, _ = await _issue(database, seed=seed.actor)
    proof = InvitationBrowserProofDTO(
        identity=VerifiedHumanIdentityDTO(
            authority=seed.actor.binding.identity.authority,
            subject=IdentitySubject(str(UUID(int=200))),
        ),
        password_completed=True,
    )
    context = IdempotencyContextDTO(
        method=HttpMethod.POST,
        requested_route="/v1/invitations/activate",
        key=IdempotencyKey("complete-existing-human"),
    )
    fingerprint = InvitationFingerprintService(
        RequestFingerprintService(RequestFingerprintKey(b"F" * 32))
    ).for_activation(ActivateInvitationCommand(token=token), invitation_id=record.invitation_id)
    async with database.session() as session, session.begin():
        reader = PostgresInvitationAssignmentFactsReader(session)
        facts = await reader.lock_for_activation(identity=proof.identity, digest=token.digest())
        issuer = await reader.read_current_issuer(invitation=record)
        assert (
            facts is not None and facts.principal is not None and facts.principal.id == seed.bob_id
        )
        assert (
            issuer is not None
            and issuer.has_coherent_identity
            and not issuer.organization_access.has_pending_recovery
        )
        assert any(
            grant.action_id.value == OrganizationAction.ADMIT_USERS.value
            for grant in issuer.organization_access.grants
        )
        writer = PostgresInvitationWriter(session)
        binding = await writer.reserve_activation(
            installation_id=facts.credential_state.installation_id,
            identity=proof.identity,
            invitation=record,
            principal_id=facts.principal.id,
            context=context,
            fingerprint=fingerprint,
        )
        stored = await session.get(InvitationActivationOperationRow, binding.operation_id.value)
        assert stored is not None and stored.principal_id == seed.bob_id.value
        # The delivered admission fixture and qualified reservation already establish a legitimate bound state.
        before = await session.scalar(select(func.clock_timestamp(type_=DateTime(timezone=True))))
        result = await writer.complete_activation(
            binding=binding,
            digest=token.digest(),
            organization_access_revision=facts.organization_access_revision,
            project_access_revisions=(),
        )
        after = await session.scalar(select(func.clock_timestamp(type_=DateTime(timezone=True))))
        assert before is not None and after is not None
        assert (
            result.operation.operation_id == binding.operation_id
            and result.operation.created is True
        )
        assert (
            result.principal_id == seed.bob_id
            and result.organization_access_revision == facts.organization_access_revision
        )
        assert (
            result.invitation_id == record.invitation_id and result.project_access_revisions == ()
        )
        await session.refresh(stored)
        assert (
            stored.state is OperationReservationState.REPLAYABLE and stored.completed_at is not None
        )
        assert before <= stored.completed_at <= after
        assert (
            stored.expires_at
            == stored.completed_at + timedelta(hours=24)
            == result.operation.expires_at
        )
        consumed = await session.get(InvitationRow, record.invitation_id.value)
        assert (
            consumed is not None
            and consumed.consumed_at is not None
            and consumed.consumed_by_principal_id == seed.bob_id.value
        )
        assert before <= consumed.consumed_at <= after
        audit = (
            await session.scalars(
                select(AccessAuditEventRow).where(
                    AccessAuditEventRow.correlation_id == binding.operation_id.value
                )
            )
        ).one()
        assert (
            audit.actor_principal_id == seed.bob_id.value
            and audit.affected_principal_id == seed.bob_id.value
        )
        assert audit.target_kind == "invitation" and audit.target_id == record.invitation_id.value
        expiry = stored.expires_at
        with pytest.raises(ConflictError):
            await writer.complete_activation(
                binding=binding,
                digest=token.digest(),
                organization_access_revision=facts.organization_access_revision,
                project_access_revisions=(),
            )
        await session.refresh(stored)
        assert stored.expires_at == expiry
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AccessAuditEventRow)
                .where(AccessAuditEventRow.correlation_id == binding.operation_id.value)
            )
            == 1
        )


def _activation_service(session: AsyncSession) -> InvitationActivationService:
    return InvitationActivationService(
        transaction_manager=SqlAlchemyTransactionManager(session),
        invitation_assignment_facts_reader=PostgresInvitationAssignmentFactsReader(session),
        invitation_activation_operation_store=PostgresInvitationWriter(session),
        invitation_fingerprint_service=InvitationFingerprintService(
            RequestFingerprintService(RequestFingerprintKey(b"F" * 32))
        ),
        invitation_admission_writer=PostgresHumanAdmissionWriter(session),
        invitation_assignment_service=_assignment_service(session),
    )


async def test_activation_already_admitted_noop_preserves_generation_revision_and_assignment_attribution(
    database: Database,
) -> None:
    seed = await seed_membership_project(database)
    record, token, _ = await _issue(database, seed=seed.actor)
    proof = InvitationBrowserProofDTO(
        identity=VerifiedHumanIdentityDTO(
            authority=seed.actor.binding.identity.authority,
            subject=IdentitySubject(str(UUID(int=200))),
        ),
        password_completed=True,
    )
    async with database.session() as session, session.begin():
        await session.execute(
            update(HumanCredentialVersionRow)
            .where(
                HumanCredentialVersionRow.installation_id
                == seed.actor.binding.installation_id.value,
                HumanCredentialVersionRow.authority == proof.identity.authority.value,
                HumanCredentialVersionRow.subject == proof.identity.subject.value,
            )
            .values(version=7)
        )
        link = await session.get(
            HumanIdentityLinkRow, (proof.identity.authority.value, proof.identity.subject.value)
        )
        assert link is not None
        linked_at = link.linked_at
    context = IdempotencyContextDTO(
        method=HttpMethod.POST,
        requested_route="/v1/invitations/activate",
        key=IdempotencyKey("existing-human-noop"),
    )
    async with database.session() as session:
        result = await _activation_service(session).activate(
            proof=proof, command=ActivateInvitationCommand(token=token), context=context
        )
    assert (
        result.principal_id == seed.bob_id
        and result.organization_access_revision == record.issued_access_revision
    )
    async with database.session() as session:
        link = await session.get(
            HumanIdentityLinkRow, (proof.identity.authority.value, proof.identity.subject.value)
        )
        version = await session.get(
            HumanCredentialVersionRow,
            (
                seed.actor.binding.installation_id.value,
                proof.identity.authority.value,
                proof.identity.subject.value,
            ),
        )
        assert (
            link is not None
            and link.linked_at == linked_at
            and version is not None
            and version.version == 7
        )
        admission = (
            await session.scalars(
                select(AccessAuditEventRow).where(
                    AccessAuditEventRow.correlation_id == result.operation.operation_id.value,
                    AccessAuditEventRow.event_type == "human_admission_unchanged",
                )
            )
        ).one()
        assert (
            admission.actor_principal_id == record.issuer_principal_id.value
            and admission.affected_principal_id == seed.bob_id.value
        )
        assert admission.before_values == {
            "access_revision": record.issued_access_revision,
            "admitted": True,
        }
        assert admission.after_values == admission.before_values
        assert (
            await session.scalar(
                select(OrganizationRow.access_revision).where(
                    OrganizationRow.id == record.organization_id.value
                )
            )
            == record.issued_access_revision
        )


@pytest.mark.parametrize(
    "failure", ["completion-audit", "after-completion", "cancellation-after-binding"]
)
async def test_activation_failure_rolls_back_all_admission_consumption_audit_and_original(
    database: Database, failure: str
) -> None:
    seed = await seed_project_creator(database)
    record, token, _ = await _issue(database, seed=seed)
    proof = replace(_unadmitted_invitation_proof(seed), password_completed=True)
    context = IdempotencyContextDTO(
        method=HttpMethod.POST,
        requested_route="/v1/invitations/activate",
        key=IdempotencyKey("rolled-back-activation"),
    )
    async with database.session() as session:
        audits_before = await session.scalar(select(func.count()).select_from(AccessAuditEventRow))
    original_bind = PostgresInvitationWriter.bind_activation_principal
    original_complete = PostgresInvitationWriter.complete_activation
    injected = RuntimeError("Controlled activation failure")

    def fail_completion_audit(session: Session, _context: object, _instances: object) -> None:
        if any(
            isinstance(row, AccessAuditEventRow)
            and row.target_kind == "invitation"
            and row.target_id == record.invitation_id.value
            for row in session.new
        ):
            raise injected

    async def cancel_after_binding(
        self: PostgresInvitationWriter,
        *,
        binding: InvitationActivationBindingDTO,
        principal: Principal,
    ) -> InvitationActivationBindingDTO:
        await original_bind(self, binding=binding, principal=principal)
        raise asyncio.CancelledError

    async def fail_after_completion(
        self: PostgresInvitationWriter,
        *,
        binding: InvitationActivationBindingDTO,
        digest: InvitationTokenDigest,
        organization_access_revision: int,
        project_access_revisions: tuple[InvitationProjectAccessRevisionDTO, ...],
    ) -> InvitationActivationResultDTO:
        await original_complete(
            self,
            binding=binding,
            digest=digest,
            organization_access_revision=organization_access_revision,
            project_access_revisions=project_access_revisions,
        )
        raise injected

    if failure == "completion-audit":
        event.listen(Session, "before_flush", fail_completion_audit)
    try:
        with ExitStack() as patches:
            if failure == "after-completion":
                patches.enter_context(
                    patch.object(
                        PostgresInvitationWriter, "complete_activation", fail_after_completion
                    )
                )
            elif failure == "cancellation-after-binding":
                patches.enter_context(
                    patch.object(
                        PostgresInvitationWriter, "bind_activation_principal", cancel_after_binding
                    )
                )
            async with database.session() as session:
                with pytest.raises(
                    asyncio.CancelledError
                    if failure == "cancellation-after-binding"
                    else RuntimeError
                ) as caught:
                    await _activation_service(session).activate(
                        proof=proof, command=ActivateInvitationCommand(token=token), context=context
                    )
                if failure != "cancellation-after-binding":
                    assert caught.value is injected
    finally:
        if failure == "completion-audit":
            event.remove(Session, "before_flush", fail_completion_audit)
    async with database.session() as session:
        assert await session.scalar(select(func.count()).select_from(PrincipalRow)) == 1
        assert (
            await session.get(
                HumanIdentityLinkRow, (proof.identity.authority.value, proof.identity.subject.value)
            )
            is None
        )
        assert (
            await session.get(
                HumanCredentialVersionRow,
                (
                    seed.binding.installation_id.value,
                    proof.identity.authority.value,
                    proof.identity.subject.value,
                ),
            )
            is None
        )
        assert await session.get(InvitationRow, record.invitation_id.value) is not None
        assert await PostgresInvitationFactsReader(session).read_by_digest(token.digest()) == record
        assert (
            await session.scalar(select(func.count()).select_from(InvitationActivationOperationRow))
            == 0
        )
        assert (
            await session.scalar(select(func.count()).select_from(AccessAuditEventRow))
            == audits_before
        )
        assert (
            await session.scalar(
                select(OrganizationRow.access_revision).where(
                    OrganizationRow.id == record.organization_id.value
                )
            )
            == record.issued_access_revision
        )


@pytest.mark.parametrize(
    "mismatch", ["ordinary-reservation", "subject", "fingerprint", "route", "principal"]
)
async def test_invitation_admission_requires_actual_exact_pending_activation(
    database: Database, mismatch: str
) -> None:
    seed = await seed_project_creator(database)
    record, token, _ = await _issue(database, seed=seed)
    proof = replace(_unadmitted_invitation_proof(seed), password_completed=True)
    context = IdempotencyContextDTO(
        method=HttpMethod.POST,
        requested_route="/v1/invitations/activate",
        key=IdempotencyKey("pending-admission-guard"),
    )
    fingerprint = InvitationFingerprintService(
        RequestFingerprintService(RequestFingerprintKey(b"F" * 32))
    ).for_activation(ActivateInvitationCommand(token=token), invitation_id=record.invitation_id)
    async with database.session() as session, session.begin():
        reader = PostgresInvitationAssignmentFactsReader(session)
        facts = await reader.lock_for_activation(identity=proof.identity, digest=token.digest())
        issuer = await reader.read_current_issuer(invitation=record)
        assert facts is not None and facts.principal is None and issuer is not None
        pending = await PostgresInvitationWriter(session).reserve_activation(
            installation_id=facts.credential_state.installation_id,
            identity=proof.identity,
            invitation=record,
            principal_id=None,
            context=context,
            fingerprint=fingerprint,
        )
        altered = (
            replace(pending, operation_id=record.issued_operation_id)
            if mismatch == "ordinary-reservation"
            else (
                replace(
                    pending,
                    identity=replace(proof.identity, subject=IdentitySubject(str(UUID(int=901)))),
                )
                if mismatch == "subject"
                else (
                    replace(pending, fingerprint=RequestFingerprint(b"X" * 32))
                    if mismatch == "fingerprint"
                    else (
                        replace(
                            pending,
                            context=replace(
                                context, requested_route="/v1/invitations/activate?other=true"
                            ),
                        )
                        if mismatch == "route"
                        else replace(pending, principal_id=record.issuer_principal_id)
                    )
                )
            )
        )
        principal = Principal(
            id=PrincipalId(uuid4()),
            organization_id=record.organization_id,
            kind=PrincipalKind.HUMAN,
            status=PrincipalStatus.ACTIVE,
        )
        with pytest.raises(RuntimeError if mismatch == "route" else ConflictError):
            await PostgresHumanAdmissionWriter(session).apply_invitation_admission(
                binding=altered, facts=facts, issuer=issuer, principal=principal
            )
        assert await session.scalar(select(func.count()).select_from(PrincipalRow)) == 1
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AccessAuditEventRow)
                .where(AccessAuditEventRow.correlation_id == pending.operation_id.value)
            )
            == 0
        )
        assert (
            await session.scalar(
                select(OrganizationRow.access_revision).where(
                    OrganizationRow.id == record.organization_id.value
                )
            )
            == record.issued_access_revision
        )


@pytest.mark.parametrize("currentness", ["other-principal", "suspended", "recovery"])
async def test_activation_binding_requires_the_current_exact_admissible_human(
    database: Database, currentness: str
) -> None:
    seed = await seed_membership_project(database)
    record, token, _ = await _issue(database, seed=seed.actor)
    proof = InvitationBrowserProofDTO(
        identity=VerifiedHumanIdentityDTO(
            authority=seed.actor.binding.identity.authority,
            subject=IdentitySubject(str(UUID(int=200))),
        ),
        password_completed=True,
    )
    context = IdempotencyContextDTO(
        method=HttpMethod.POST,
        requested_route="/v1/invitations/activate",
        key=IdempotencyKey("current-binding-guard"),
    )
    fingerprint = InvitationFingerprintService(
        RequestFingerprintService(RequestFingerprintKey(b"F" * 32))
    ).for_activation(ActivateInvitationCommand(token=token), invitation_id=record.invitation_id)
    async with database.session() as session, session.begin():
        facts = await PostgresInvitationAssignmentFactsReader(session).lock_for_activation(
            identity=proof.identity, digest=token.digest()
        )
        assert facts is not None and facts.principal is not None
        writer = PostgresInvitationWriter(session)
        binding = await writer.reserve_activation(
            installation_id=facts.credential_state.installation_id,
            identity=proof.identity,
            invitation=record,
            principal_id=facts.principal.id,
            context=context,
            fingerprint=fingerprint,
        )
        if currentness == "suspended":
            await session.execute(
                update(PrincipalRow)
                .where(PrincipalRow.id == seed.bob_id.value)
                .values(status=PrincipalStatus.SUSPENDED)
            )
        elif currentness == "recovery":
            session.add(
                IdentityRecoveryAdmissionRow(
                    operation_id=str(uuid4()),
                    installation_id=facts.credential_state.installation_id.value,
                    authority=proof.identity.authority.value,
                    subject=proof.identity.subject.value,
                    flow_id=uuid4(),
                    event_kind=IdentityRecoveryEventKind.RECOVERY,
                )
            )
            await session.flush()
        principal = (
            replace(facts.principal, id=record.issuer_principal_id)
            if currentness == "other-principal"
            else facts.principal
        )
        with pytest.raises(ConflictError):
            await writer.bind_activation_principal(binding=binding, principal=principal)
        saved = await session.get(InvitationActivationOperationRow, binding.operation_id.value)
        assert (
            saved is not None
            and saved.principal_id == seed.bob_id.value
            and saved.state is OperationReservationState.IN_PROGRESS
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AccessAuditEventRow)
                .where(AccessAuditEventRow.correlation_id == binding.operation_id.value)
            )
            == 0
        )


async def test_activation_completion_rechecks_database_expiry_without_consumption_or_outcome(
    database: Database,
) -> None:
    seed = await seed_membership_project(database)
    record, token, _ = await _issue(database, seed=seed.actor)
    proof = InvitationBrowserProofDTO(
        identity=VerifiedHumanIdentityDTO(
            authority=seed.actor.binding.identity.authority,
            subject=IdentitySubject(str(UUID(int=200))),
        ),
        password_completed=True,
    )
    context = IdempotencyContextDTO(
        method=HttpMethod.POST,
        requested_route="/v1/invitations/activate",
        key=IdempotencyKey("final-expiry-guard"),
    )
    fingerprint = InvitationFingerprintService(
        RequestFingerprintService(RequestFingerprintKey(b"F" * 32))
    ).for_activation(ActivateInvitationCommand(token=token), invitation_id=record.invitation_id)
    async with database.session() as session, session.begin():
        facts = await PostgresInvitationAssignmentFactsReader(session).lock_for_activation(
            identity=proof.identity, digest=token.digest()
        )
        assert facts is not None and facts.principal is not None
        writer = PostgresInvitationWriter(session)
        binding = await writer.reserve_activation(
            installation_id=facts.credential_state.installation_id,
            identity=proof.identity,
            invitation=record,
            principal_id=facts.principal.id,
            context=context,
            fingerprint=fingerprint,
        )
        await session.execute(
            update(InvitationRow)
            .where(InvitationRow.id == record.invitation_id.value)
            .values(expires_at=func.clock_timestamp())
        )
        with pytest.raises(ResourceNotFoundError):
            await writer.complete_activation(
                binding=binding,
                digest=token.digest(),
                organization_access_revision=facts.organization_access_revision,
                project_access_revisions=(),
            )
        saved = await session.get(InvitationActivationOperationRow, binding.operation_id.value)
        assert (
            saved is not None
            and saved.expires_at is None
            and saved.completed_at is None
            and saved.state is OperationReservationState.IN_PROGRESS
        )
        assert (
            await session.scalar(
                select(InvitationRow.consumed_at).where(
                    InvitationRow.id == record.invitation_id.value
                )
            )
            is None
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AccessAuditEventRow)
                .where(AccessAuditEventRow.correlation_id == binding.operation_id.value)
            )
            == 0
        )


def _assignment_service(session: AsyncSession) -> InvitationAssignmentService:
    audit_writer = PostgresAuditEventWriter(session)
    return InvitationAssignmentService(
        invitation_assignment_facts_reader=PostgresInvitationAssignmentFactsReader(session),
        invitation_project_membership_writer=PostgresProjectMembershipChangeWriter(session),
        invitation_group_relationship_writer=PostgresAccessGroupRelationshipWriter(session),
        invitation_organization_grant_writer=PostgresOrganizationActionGrantWriter(
            session, audit_writer
        ),
        invitation_access_group_grant_writer=PostgresAccessGroupActionGrantWriter(
            session, audit_writer
        ),
        invitation_application_grant_writer=PostgresApplicationAccountActionGrantWriter(
            session, audit_writer
        ),
        project_membership_repository=PostgresProjectMembershipRepository(
            session, PostgresAuditEventWriter(session)
        ),
    )


async def _assignment_invitation(
    database: Database,
    *,
    already_project_member: bool = True,
) -> tuple[
    MembershipProjectSeedDTO, AccessGroupId, PrincipalId, InvitationRecordDTO, InvitationToken
]:
    seed = await seed_membership_project(database)
    project = seed.project.project_id
    project_revision = seed.project.access_revision
    if already_project_member:
        membership = await change_membership(
            database, seed, revision=project_revision, key="assignment-project-member"
        )
        assert membership.changed
        project_revision = membership.access_revision

    group = (
        await create_group(database, seed.actor.access, project, revision=project_revision)
    ).group
    account = (
        await create_account(database, seed.actor.access, project, revision=group.access_revision)
    ).account
    assignments: tuple[InvitationAssignmentDTO, ...] = (
        InvitationProjectMembershipIntentDTO(project_id=project),
        InvitationGroupMembershipIntentDTO(project_id=project, access_group_id=group.group_id),
        InvitationGroupManagerIntentDTO(project_id=project, access_group_id=group.group_id),
        InvitationActionGrantIntentDTO(
            target=OrganizationGrantTargetDTO(organization_id=seed.actor.organization_id),
            action_id=ActionId("create-projects"),
            can_grant=False,
        ),
        InvitationActionGrantIntentDTO(
            target=ProjectGrantTargetDTO(project_id=project),
            action_id=ActionId("create-access-groups"),
            can_grant=True,
        ),
        InvitationActionGrantIntentDTO(
            target=AccessGroupGrantTargetDTO(project_id=project, access_group_id=group.group_id),
            action_id=ActionId("add-documents"),
            can_grant=True,
        ),
        InvitationActionGrantIntentDTO(
            target=ApplicationAccountGrantTargetDTO(
                project_id=project, application_principal_id=account.principal_id
            ),
            action_id=ActionId("issue-application-keys"),
            can_grant=True,
        ),
    )
    command = await _review(database, seed.actor, assignments, (project,))
    async with database.session() as session:
        issued = await _administration(session).issue(
            access=seed.actor.access, command=command, context=_context("all-assignment-seams")
        )
        assert issued.token is not None
        record = await PostgresInvitationFactsReader(session).read_by_digest(issued.token.digest())
        assert record is not None
    return seed, group.group_id, account.principal_id, record, issued.token


async def test_assignment_preflight_reads_all_actual_native_states(database: Database) -> None:
    seed, _, _, record, token = await _assignment_invitation(database)
    identity = VerifiedHumanIdentityDTO(
        authority=seed.actor.binding.identity.authority, subject=IdentitySubject(str(UUID(int=200)))
    )
    async with database.session() as session, session.begin():
        reader = PostgresInvitationAssignmentFactsReader(session)
        facts = await reader.lock_for_activation(identity=identity, digest=token.digest())
        assert facts is not None and facts.principal is not None
        states = await reader.read_assignment_states(invitation=record, recipient=facts.principal)
        assert states is not None and tuple(item.intent for item in states) == record.assignments
        assert len(states) == 7
        assert (
            isinstance(states[0].facts, ProjectMembershipChangeFactsDTO)
            and states[0].facts.recipient_is_project_member
        )
        assert (
            isinstance(states[1].facts, AccessGroupChangeFactsDTO)
            and not states[1].facts.relationships.member
        )
        assert (
            isinstance(states[3].facts, OrganizationGrantManagementFactsDTO)
            and states[3].facts.recipient is not None
        )
        assert states[3].facts.recipient.id == seed.bob_id
        assert (
            isinstance(states[5].facts, AccessGroupGrantManagementFactsDTO)
            and states[5].facts.assignment.can_grant is None
        )
        assert (
            isinstance(states[6].facts, ApplicationAccountGrantManagementFactsDTO)
            and states[6].facts.assignment.can_grant is None
        )
        assert (
            await session.scalar(select(func.count()).select_from(InvitationActivationOperationRow))
            == 0
        )


async def test_assignment_refresh_reads_current_exact_native_scope(database: Database) -> None:
    seed, _, _, record, token = await _assignment_invitation(database)
    identity = VerifiedHumanIdentityDTO(
        authority=seed.actor.binding.identity.authority, subject=IdentitySubject(str(UUID(int=200)))
    )
    async with database.session() as session, session.begin():
        reader = PostgresInvitationAssignmentFactsReader(session)
        facts = await reader.lock_for_activation(identity=identity, digest=token.digest())
        assert facts is not None and facts.principal is not None
        state = await reader.read_assignment_state(
            invitation_id=record.invitation_id,
            recipient=facts.principal,
            intent=record.assignments[3],
        )
        assert state is not None and state.intent == record.assignments[3]
        assert isinstance(state.facts, OrganizationGrantManagementFactsDTO)
        assert (
            state.facts.actor.id == record.issuer_principal_id
            and state.facts.recipient is not None
            and state.facts.recipient.id == seed.bob_id
        )
        assert (
            state.facts.organization_id == record.organization_id
            and state.facts.access_revision == facts.organization_access_revision
        )


async def test_invitation_membership_entry_uses_real_pending_binding_and_native_facts(
    database: Database,
) -> None:
    seed, _, _, record, token = await _assignment_invitation(database, already_project_member=False)
    identity = VerifiedHumanIdentityDTO(
        authority=seed.actor.binding.identity.authority, subject=IdentitySubject(str(UUID(int=200)))
    )
    context = IdempotencyContextDTO(
        method=HttpMethod.POST,
        requested_route="/v1/invitations/activate",
        key=IdempotencyKey("membership-entry"),
    )
    fingerprint = InvitationFingerprintService(
        RequestFingerprintService(RequestFingerprintKey(b"F" * 32))
    ).for_activation(ActivateInvitationCommand(token=token), invitation_id=record.invitation_id)
    async with database.session() as session, session.begin():
        activation = await PostgresInvitationAssignmentFactsReader(session).lock_for_activation(
            identity=identity, digest=token.digest()
        )
        assert activation is not None and activation.principal is not None
        binding = await PostgresInvitationWriter(session).reserve_activation(
            installation_id=activation.credential_state.installation_id,
            identity=identity,
            invitation=record,
            principal_id=seed.bob_id,
            context=context,
            fingerprint=fingerprint,
        )
        # Actual native fixture evidence is used only to prepare independent native facts, not fabricated issuer authentication.
        facts = await PostgresProjectMembershipChangeFactsReader(
            session
        ).lock_and_load_membership_state(
            access=seed.actor.access, project_id=seed.project.project_id, principal_id=seed.bob_id
        )
        assert facts is not None and not facts.recipient_is_project_member
        assert facts.recipient is not None and facts.recipient.id == seed.bob_id
        assert (
            facts.recipient_has_coherent_identity
            and not facts.recipient_has_pending_recovery
            and facts.recipient.status is PrincipalStatus.ACTIVE
        )
        after = await PostgresProjectMembershipChangeWriter(session).apply_invitation_membership(
            binding=binding, facts=facts, principal_id=seed.bob_id
        )
        assert after == facts.access_revision + 1
        assert (
            await session.scalar(
                select(ProjectMembershipRow.principal_id).where(
                    ProjectMembershipRow.project_id == seed.project.project_id.value,
                    ProjectMembershipRow.principal_id == seed.bob_id.value,
                )
            )
            == seed.bob_id.value
        )


@pytest.mark.parametrize(
    "kind", [AccessGroupChangeKind.ADD_MEMBER, AccessGroupChangeKind.APPOINT_MANAGER]
)
async def test_invitation_group_entry_uses_real_pending_binding_and_native_relationships(
    database: Database, kind: AccessGroupChangeKind
) -> None:
    seed, group, _, record, token = await _assignment_invitation(database)
    identity = VerifiedHumanIdentityDTO(
        authority=seed.actor.binding.identity.authority, subject=IdentitySubject(str(UUID(int=200)))
    )
    context = IdempotencyContextDTO(
        method=HttpMethod.POST,
        requested_route="/v1/invitations/activate",
        key=IdempotencyKey("group-entry"),
    )
    fingerprint = InvitationFingerprintService(
        RequestFingerprintService(RequestFingerprintKey(b"F" * 32))
    ).for_activation(ActivateInvitationCommand(token=token), invitation_id=record.invitation_id)
    async with database.session() as session, session.begin():
        activation = await PostgresInvitationAssignmentFactsReader(session).lock_for_activation(
            identity=identity, digest=token.digest()
        )
        assert activation is not None
        binding = await PostgresInvitationWriter(session).reserve_activation(
            installation_id=activation.credential_state.installation_id,
            identity=identity,
            invitation=record,
            principal_id=seed.bob_id,
            context=context,
            fingerprint=fingerprint,
        )
        revision = await session.scalar(
            select(ProjectRow.access_revision).where(ProjectRow.id == seed.project.project_id.value)
        )
        assert revision is not None
        command = ChangeAccessGroupRelationshipCommand(
            project_id=seed.project.project_id,
            group_id=group,
            principal_id=seed.bob_id,
            expected_access_revision=revision,
            change_kind=kind,
        )
        facts = await PostgresAccessGroupFactsReader(session).lock_for_change(
            access=seed.actor.access, command=command
        )
        assert facts is not None and not facts.relationships.member
        assert facts.recipient is not None and facts.recipient.id == seed.bob_id
        assert AccessGroupRelationshipPolicy.may_add_member(
            principal=facts.recipient,
            is_project_member=facts.recipient_is_project_member,
            has_coherent_identity=facts.recipient_has_coherent_identity,
            has_pending_recovery=facts.recipient_has_pending_recovery,
        )
        if kind is AccessGroupChangeKind.APPOINT_MANAGER:
            assert AccessGroupRelationshipPolicy.supports_manager_kind(facts.recipient.kind)
        desired = (
            AccessGroupRelationshipPolicy.add_member(facts.relationships)
            if kind is AccessGroupChangeKind.ADD_MEMBER
            else AccessGroupRelationshipPolicy.appoint_manager(facts.relationships)
        )
        after = await PostgresAccessGroupRelationshipWriter(session).apply_invitation_relationship(
            binding=binding, facts=facts, command=command, after=desired
        )
        assert after == revision + 1
        assert (
            await session.scalar(
                select(GroupMembershipRow.principal_id).where(
                    GroupMembershipRow.group_id == group.value,
                    GroupMembershipRow.principal_id == seed.bob_id.value,
                )
            )
            == seed.bob_id.value
        )
        manager = await session.scalar(
            select(GroupManagerRow.principal_id).where(
                GroupManagerRow.group_id == group.value,
                GroupManagerRow.principal_id == seed.bob_id.value,
            )
        )
        assert (manager == seed.bob_id.value) is (kind is AccessGroupChangeKind.APPOINT_MANAGER)


async def test_invitation_organization_grant_entry_uses_native_exact_transition(
    database: Database,
) -> None:
    seed, _, _, record, token = await _assignment_invitation(database)
    identity = VerifiedHumanIdentityDTO(
        authority=seed.actor.binding.identity.authority, subject=IdentitySubject(str(UUID(int=200)))
    )
    context = IdempotencyContextDTO(
        method=HttpMethod.POST,
        requested_route="/v1/invitations/activate",
        key=IdempotencyKey("organization-grant-entry"),
    )
    fingerprint = InvitationFingerprintService(
        RequestFingerprintService(RequestFingerprintKey(b"F" * 32))
    ).for_activation(ActivateInvitationCommand(token=token), invitation_id=record.invitation_id)
    async with database.session() as session, session.begin():
        activation = await PostgresInvitationAssignmentFactsReader(session).lock_for_activation(
            identity=identity, digest=token.digest()
        )
        assert activation is not None
        binding = await PostgresInvitationWriter(session).reserve_activation(
            installation_id=activation.credential_state.installation_id,
            identity=identity,
            invitation=record,
            principal_id=seed.bob_id,
            context=context,
            fingerprint=fingerprint,
        )
        facts = await PostgresOrganizationGrantManagementFactsReader(session).lock_for_management(
            access=seed.actor.access,
            organization_id=record.organization_id,
            recipient_principal_id=seed.bob_id,
            action_id=ActionId("create-projects"),
        )
        assert facts is not None and facts.assignment.can_grant is None
        assert facts.recipient is not None and facts.recipient.id == seed.bob_id
        assert (
            facts.recipient.kind is PrincipalKind.HUMAN
            and facts.recipient.status is PrincipalStatus.ACTIVE
            and facts.recipient_has_coherent_identity
            and not facts.recipient_has_pending_recovery
        )
        after = await PostgresOrganizationActionGrantWriter(
            session, PostgresAuditEventWriter(session)
        ).apply_invitation_grant(
            binding=binding,
            facts=facts,
            recipient_principal_id=seed.bob_id,
            after=facts.assignment.set_level(can_grant=False),
        )
        assert after == facts.access_revision + 1
        row = await session.get(
            OrganizationActionGrantRow,
            (record.organization_id.value, seed.bob_id.value, "create-projects"),
        )
        assert (
            row is not None
            and row.can_grant is False
            and row.assigned_by_principal_id == record.issuer_principal_id.value
        )


async def test_invitation_group_grant_entry_uses_native_exact_transition(
    database: Database,
) -> None:
    seed, group, _, record, token = await _assignment_invitation(database)
    identity = VerifiedHumanIdentityDTO(
        authority=seed.actor.binding.identity.authority, subject=IdentitySubject(str(UUID(int=200)))
    )
    context = IdempotencyContextDTO(
        method=HttpMethod.POST,
        requested_route="/v1/invitations/activate",
        key=IdempotencyKey("group-grant-entry"),
    )
    fingerprint = InvitationFingerprintService(
        RequestFingerprintService(RequestFingerprintKey(b"F" * 32))
    ).for_activation(ActivateInvitationCommand(token=token), invitation_id=record.invitation_id)
    async with database.session() as session, session.begin():
        activation = await PostgresInvitationAssignmentFactsReader(session).lock_for_activation(
            identity=identity, digest=token.digest()
        )
        assert activation is not None
        binding = await PostgresInvitationWriter(session).reserve_activation(
            installation_id=activation.credential_state.installation_id,
            identity=identity,
            invitation=record,
            principal_id=seed.bob_id,
            context=context,
            fingerprint=fingerprint,
        )
        facts = await PostgresAccessGroupGrantManagementFactsReader(session).lock_for_management(
            access=seed.actor.access,
            project_id=seed.project.project_id,
            group_id=group,
            recipient_principal_id=seed.bob_id,
            action_id=ActionId("add-documents"),
        )
        assert facts is not None and facts.assignment.can_grant is None
        assert facts.recipient is not None and facts.recipient.id == seed.bob_id
        assert (
            facts.recipient.kind is PrincipalKind.HUMAN
            and facts.recipient.status is PrincipalStatus.ACTIVE
            and facts.recipient_is_project_member
            and facts.recipient_has_coherent_identity
            and not facts.recipient_has_pending_recovery
        )
        after = await PostgresAccessGroupActionGrantWriter(
            session, PostgresAuditEventWriter(session)
        ).apply_invitation_grant(
            binding=binding,
            facts=facts,
            recipient_principal_id=seed.bob_id,
            after=facts.assignment.set_level(can_grant=True),
        )
        assert after == facts.access_revision + 1
        row = await session.get(
            GroupActionGrantRow,
            (seed.project.project_id.value, group.value, seed.bob_id.value, "add-documents"),
        )
        assert (
            row is not None
            and row.can_grant
            and row.assigned_by_principal_id == record.issuer_principal_id.value
        )


async def test_invitation_application_grant_entry_uses_native_exact_transition(
    database: Database,
) -> None:
    seed, _, application, record, token = await _assignment_invitation(database)
    identity = VerifiedHumanIdentityDTO(
        authority=seed.actor.binding.identity.authority, subject=IdentitySubject(str(UUID(int=200)))
    )
    context = IdempotencyContextDTO(
        method=HttpMethod.POST,
        requested_route="/v1/invitations/activate",
        key=IdempotencyKey("application-grant-entry"),
    )
    fingerprint = InvitationFingerprintService(
        RequestFingerprintService(RequestFingerprintKey(b"F" * 32))
    ).for_activation(ActivateInvitationCommand(token=token), invitation_id=record.invitation_id)
    async with database.session() as session, session.begin():
        activation = await PostgresInvitationAssignmentFactsReader(session).lock_for_activation(
            identity=identity, digest=token.digest()
        )
        assert activation is not None
        binding = await PostgresInvitationWriter(session).reserve_activation(
            installation_id=activation.credential_state.installation_id,
            identity=identity,
            invitation=record,
            principal_id=seed.bob_id,
            context=context,
            fingerprint=fingerprint,
        )
        facts = await PostgresApplicationAccountGrantManagementFactsReader(
            session
        ).lock_for_management(
            access=seed.actor.access,
            project_id=seed.project.project_id,
            application_principal_id=application,
            recipient_principal_id=seed.bob_id,
            action_id=ActionId("issue-application-keys"),
        )
        assert facts is not None and facts.assignment.can_grant is None
        assert facts.recipient is not None and facts.recipient.id == seed.bob_id
        assert (
            facts.recipient.kind is PrincipalKind.HUMAN
            and facts.recipient.status is PrincipalStatus.ACTIVE
            and facts.recipient_is_project_member
            and facts.recipient_has_coherent_identity
            and not facts.recipient_has_pending_recovery
        )
        after = await PostgresApplicationAccountActionGrantWriter(
            session, PostgresAuditEventWriter(session)
        ).apply_invitation_grant(
            binding=binding,
            facts=facts,
            recipient_principal_id=seed.bob_id,
            after=facts.assignment.set_level(can_grant=True),
        )
        assert after == facts.access_revision + 1
        row = await session.get(
            ApplicationActionGrantRow,
            (
                seed.project.project_id.value,
                application.value,
                seed.bob_id.value,
                "issue-application-keys",
            ),
        )
        assert (
            row is not None
            and row.can_grant
            and row.assigned_by_principal_id == record.issuer_principal_id.value
        )


@pytest.mark.parametrize(
    "entry", ["membership", "relationship", "organization", "group", "application"]
)
async def test_invitation_assignment_entries_reject_a_different_activation_recipient(
    database: Database, entry: str
) -> None:
    seed, group, application, record, token = await _assignment_invitation(database)
    identity = VerifiedHumanIdentityDTO(
        authority=seed.actor.binding.identity.authority, subject=IdentitySubject(str(UUID(int=200)))
    )
    context = IdempotencyContextDTO(
        method=HttpMethod.POST,
        requested_route="/v1/invitations/activate",
        key=IdempotencyKey("wrong-assignment-recipient"),
    )
    fingerprint = InvitationFingerprintService(
        RequestFingerprintService(RequestFingerprintKey(b"F" * 32))
    ).for_activation(ActivateInvitationCommand(token=token), invitation_id=record.invitation_id)
    async with database.session() as session, session.begin():
        activation = await PostgresInvitationAssignmentFactsReader(session).lock_for_activation(
            identity=identity, digest=token.digest()
        )
        assert activation is not None and activation.principal is not None
        binding = await PostgresInvitationWriter(session).reserve_activation(
            installation_id=activation.credential_state.installation_id,
            identity=identity,
            invitation=record,
            principal_id=seed.bob_id,
            context=context,
            fingerprint=fingerprint,
        )
        audit_count = await session.scalar(select(func.count()).select_from(AccessAuditEventRow))
        revision = await session.scalar(
            select(ProjectRow.access_revision).where(ProjectRow.id == seed.project.project_id.value)
        )
        assert revision is not None
        with pytest.raises(ConflictError):
            if entry == "membership":
                membership = await PostgresProjectMembershipChangeFactsReader(
                    session
                ).lock_and_load_membership_state(
                    access=seed.actor.access,
                    project_id=seed.project.project_id,
                    principal_id=seed.bob_id,
                )
                assert membership is not None and membership.recipient is not None
                await PostgresProjectMembershipChangeWriter(session).apply_invitation_membership(
                    binding=binding,
                    facts=membership,
                    principal_id=record.issuer_principal_id,
                )
            elif entry == "relationship":
                command = ChangeAccessGroupRelationshipCommand(
                    project_id=seed.project.project_id,
                    group_id=group,
                    principal_id=seed.bob_id,
                    expected_access_revision=revision,
                    change_kind=AccessGroupChangeKind.ADD_MEMBER,
                )
                relationship = await PostgresAccessGroupFactsReader(session).lock_for_change(
                    access=seed.actor.access, command=command
                )
                assert relationship is not None and relationship.recipient_is_project_member
                await PostgresAccessGroupRelationshipWriter(session).apply_invitation_relationship(
                    binding=binding,
                    facts=relationship,
                    command=replace(command, principal_id=record.issuer_principal_id),
                    after=AccessGroupRelationshipPolicy.add_member(relationship.relationships),
                )
            elif entry == "organization":
                organization = await PostgresOrganizationGrantManagementFactsReader(
                    session
                ).lock_for_management(
                    access=seed.actor.access,
                    organization_id=record.organization_id,
                    recipient_principal_id=seed.bob_id,
                    action_id=ActionId("create-projects"),
                )
                assert organization is not None and organization.recipient is not None
                await PostgresOrganizationActionGrantWriter(
                    session, PostgresAuditEventWriter(session)
                ).apply_invitation_grant(
                    binding=binding,
                    facts=organization,
                    recipient_principal_id=record.issuer_principal_id,
                    after=organization.assignment.set_level(can_grant=False),
                )
            elif entry == "group":
                group_grant = await PostgresAccessGroupGrantManagementFactsReader(
                    session
                ).lock_for_management(
                    access=seed.actor.access,
                    project_id=seed.project.project_id,
                    group_id=group,
                    recipient_principal_id=seed.bob_id,
                    action_id=ActionId("add-documents"),
                )
                assert group_grant is not None and group_grant.recipient_is_project_member
                await PostgresAccessGroupActionGrantWriter(
                    session, PostgresAuditEventWriter(session)
                ).apply_invitation_grant(
                    binding=binding,
                    facts=group_grant,
                    recipient_principal_id=record.issuer_principal_id,
                    after=group_grant.assignment.set_level(can_grant=True),
                )
            else:
                app_grant = await PostgresApplicationAccountGrantManagementFactsReader(
                    session
                ).lock_for_management(
                    access=seed.actor.access,
                    project_id=seed.project.project_id,
                    application_principal_id=application,
                    recipient_principal_id=seed.bob_id,
                    action_id=ActionId("issue-application-keys"),
                )
                assert app_grant is not None and app_grant.recipient_is_project_member
                await PostgresApplicationAccountActionGrantWriter(
                    session, PostgresAuditEventWriter(session)
                ).apply_invitation_grant(
                    binding=binding,
                    facts=app_grant,
                    recipient_principal_id=record.issuer_principal_id,
                    after=app_grant.assignment.set_level(can_grant=True),
                )
        assert (
            await session.scalar(select(func.count()).select_from(AccessAuditEventRow))
            == audit_count
        )
        assert (
            await session.scalar(
                select(ProjectRow.access_revision).where(
                    ProjectRow.id == seed.project.project_id.value
                )
            )
            == revision
        )
        assert await PostgresInvitationFactsReader(session).read_by_digest(token.digest()) == record


async def test_invitation_group_grant_rejects_an_actual_unpromised_target(
    database: Database,
) -> None:
    seed, promised_group, _, record, token = await _assignment_invitation(database)
    async with database.session() as session:
        revision = await session.scalar(
            select(ProjectRow.access_revision).where(ProjectRow.id == seed.project.project_id.value)
        )
    assert revision is not None
    other_group = (
        await create_group(
            database,
            seed.actor.access,
            seed.project.project_id,
            revision=revision,
            name="unpromised-group",
            key="create-unpromised-group",
        )
    ).group
    assert other_group.group_id != promised_group
    identity = VerifiedHumanIdentityDTO(
        authority=seed.actor.binding.identity.authority, subject=IdentitySubject(str(UUID(int=200)))
    )
    context = IdempotencyContextDTO(
        method=HttpMethod.POST,
        requested_route="/v1/invitations/activate",
        key=IdempotencyKey("unpromised-group"),
    )
    fingerprint = InvitationFingerprintService(
        RequestFingerprintService(RequestFingerprintKey(b"F" * 32))
    ).for_activation(ActivateInvitationCommand(token=token), invitation_id=record.invitation_id)
    async with database.session() as session, session.begin():
        activation = await PostgresInvitationAssignmentFactsReader(session).lock_for_activation(
            identity=identity, digest=token.digest()
        )
        assert activation is not None
        binding = await PostgresInvitationWriter(session).reserve_activation(
            installation_id=activation.credential_state.installation_id,
            identity=identity,
            invitation=record,
            principal_id=seed.bob_id,
            context=context,
            fingerprint=fingerprint,
        )
        facts = await PostgresAccessGroupGrantManagementFactsReader(session).lock_for_management(
            access=seed.actor.access,
            project_id=seed.project.project_id,
            group_id=other_group.group_id,
            recipient_principal_id=seed.bob_id,
            action_id=ActionId("add-documents"),
        )
        assert (
            facts is not None
            and facts.recipient_is_project_member
            and facts.assignment.can_grant is None
        )
        with pytest.raises(ConflictError):
            await PostgresAccessGroupActionGrantWriter(
                session, PostgresAuditEventWriter(session)
            ).apply_invitation_grant(
                binding=binding,
                facts=facts,
                recipient_principal_id=seed.bob_id,
                after=facts.assignment.set_level(can_grant=True),
            )
        assert (
            await session.get(
                GroupActionGrantRow,
                (
                    seed.project.project_id.value,
                    other_group.group_id.value,
                    seed.bob_id.value,
                    "add-documents",
                ),
            )
            is None
        )
        assert (
            await session.scalar(
                select(ProjectRow.access_revision).where(
                    ProjectRow.id == seed.project.project_id.value
                )
            )
            == other_group.access_revision
        )


async def test_invitation_organization_grant_rejects_an_unbound_pending_identity(
    database: Database,
) -> None:
    seed, _, _, record, token = await _assignment_invitation(database)
    identity = VerifiedHumanIdentityDTO(
        authority=seed.actor.binding.identity.authority, subject=IdentitySubject(str(UUID(int=999)))
    )
    context = IdempotencyContextDTO(
        method=HttpMethod.POST,
        requested_route="/v1/invitations/activate",
        key=IdempotencyKey("unbound-assignment"),
    )
    fingerprint = InvitationFingerprintService(
        RequestFingerprintService(RequestFingerprintKey(b"F" * 32))
    ).for_activation(ActivateInvitationCommand(token=token), invitation_id=record.invitation_id)
    async with database.session() as session, session.begin():
        activation = await PostgresInvitationAssignmentFactsReader(session).lock_for_activation(
            identity=identity, digest=token.digest()
        )
        assert activation is not None and activation.principal is None
        binding = await PostgresInvitationWriter(session).reserve_activation(
            installation_id=activation.credential_state.installation_id,
            identity=identity,
            invitation=record,
            principal_id=None,
            context=context,
            fingerprint=fingerprint,
        )
        facts = await PostgresOrganizationGrantManagementFactsReader(session).lock_for_management(
            access=seed.actor.access,
            organization_id=record.organization_id,
            recipient_principal_id=seed.bob_id,
            action_id=ActionId("create-projects"),
        )
        assert (
            facts is not None and facts.recipient is not None and facts.assignment.can_grant is None
        )
        with pytest.raises(ConflictError):
            await PostgresOrganizationActionGrantWriter(
                session, PostgresAuditEventWriter(session)
            ).apply_invitation_grant(
                binding=binding,
                facts=facts,
                recipient_principal_id=seed.bob_id,
                after=facts.assignment.set_level(can_grant=False),
            )
        assert (
            await session.get(
                OrganizationActionGrantRow,
                (record.organization_id.value, seed.bob_id.value, "create-projects"),
            )
            is None
        )
        assert (
            await session.scalar(
                select(OrganizationRow.access_revision).where(
                    OrganizationRow.id == record.organization_id.value
                )
            )
            == facts.access_revision
        )


async def test_assignment_refresh_work_is_independent_of_unrelated_retained_intents(
    database: Database,
) -> None:
    seed, _, _, full, token = await _assignment_invitation(database)
    intent = full.assignments[3]
    assert isinstance(intent, InvitationActionGrantIntentDTO)
    assert isinstance(intent.target, OrganizationGrantTargetDTO)
    reviewed = await _review(database, seed.actor, (intent,))
    async with database.session() as session:
        issued = await _administration(session).issue(
            access=seed.actor.access, command=reviewed, context=_context("single-effect-refresh")
        )
        assert issued.token is not None
        short = await PostgresInvitationFactsReader(session).read_by_digest(issued.token.digest())
        assert short is not None and short.assignments == (intent,)
    assert len(full.assignments) > len(short.assignments)

    identity = VerifiedHumanIdentityDTO(
        authority=seed.actor.binding.identity.authority, subject=IdentitySubject(str(UUID(int=200)))
    )
    statements: list[bool] = []

    def observe(state: ORMExecuteState) -> None:
        statements.append(state.is_select)

    async with database.session() as session, session.begin():
        reader = PostgresInvitationAssignmentFactsReader(session)
        activation = await reader.lock_for_activation(identity=identity, digest=token.digest())
        assert activation is not None and activation.principal is not None
        event.listen(session.sync_session, "do_orm_execute", observe)
        try:
            short_state = await reader.read_assignment_state(
                invitation_id=short.invitation_id, recipient=activation.principal, intent=intent
            )
            short_statements = tuple(statements)
            statements.clear()
            full_state = await reader.read_assignment_state(
                invitation_id=full.invitation_id, recipient=activation.principal, intent=intent
            )
            full_statements = tuple(statements)
        finally:
            event.remove(session.sync_session, "do_orm_execute", observe)

    assert short_state is not None and full_state is not None
    assert short_state == full_state
    assert short_statements and all(short_statements) and all(full_statements)
    assert len(full_statements) == len(short_statements)


async def _mixed_activation_counts(
    database: Database, seed: MembershipProjectSeedDTO
) -> dict[str, int]:
    """Observe all seven effect families and their transaction-owned outcomes."""
    counts: dict[str, int] = {}
    async with database.session() as session:
        for label, row in (
            ("principals", PrincipalRow),
            ("links", HumanIdentityLinkRow),
            ("versions", HumanCredentialVersionRow),
            ("recoveries", IdentityRecoveryAdmissionRow),
            ("memberships", ProjectMembershipRow),
            ("group_members", GroupMembershipRow),
            ("managers", GroupManagerRow),
            ("organization_grants", OrganizationActionGrantRow),
            ("project_grants", ProjectActionGrantRow),
            ("group_grants", GroupActionGrantRow),
            ("application_grants", ApplicationActionGrantRow),
            ("audits", AccessAuditEventRow),
            ("originals", InvitationActivationOperationRow),
        ):
            count = await session.scalar(select(func.count()).select_from(row))
            assert count is not None
            counts[label] = count
        organization_revision = await session.scalar(
            select(OrganizationRow.access_revision).where(
                OrganizationRow.id == seed.actor.organization_id.value
            )
        )
        project_revision = await session.scalar(
            select(ProjectRow.access_revision).where(ProjectRow.id == seed.project.project_id.value)
        )
        assert organization_revision is not None and project_revision is not None
        counts["organization_revision"] = organization_revision
        counts["project_revision"] = project_revision
    return counts


def _record_activation_pid(session: AsyncSession, ready: asyncio.Future[int]) -> None:
    def observe(
        _session: Session, _transaction: SessionTransaction, connection: Connection
    ) -> None:
        pid = connection.scalar(select(func.pg_backend_pid()))
        assert isinstance(pid, int)
        ready.set_result(pid)

    event.listen(session.sync_session, "after_begin", observe, once=True)


async def _wait_for_activation_block[Result](
    database: Database, ready: asyncio.Future[int], operation: asyncio.Task[Result], holder_pid: int
) -> None:
    async with asyncio.timeout(2):
        done, _ = await asyncio.wait((ready, operation), return_when=asyncio.FIRST_COMPLETED)
        if operation in done:
            await operation
            raise AssertionError("The operation ended before its database wait.")
        pid = ready.result()
        while True:
            if operation.done():
                await operation
                raise AssertionError("The operation ended before its database wait.")
            async with database.session() as observer:
                blockers = await observer.scalar(
                    select(func.pg_blocking_pids(pid, type_=ARRAY(Integer)))
                )
            if blockers is not None and holder_pid in blockers:
                return
            await asyncio.sleep(0.01)


@pytest.mark.parametrize("existing", [False, True])
async def test_mixed_activation_commits_all_seven_effects_and_replays_without_regrant(
    database: Database, existing: bool
) -> None:
    seed, group, application, record, token = await _assignment_invitation(database)
    proof = InvitationBrowserProofDTO(
        identity=VerifiedHumanIdentityDTO(
            authority=seed.actor.binding.identity.authority,
            subject=IdentitySubject(str(UUID(int=200 if existing else 900))),
        ),
        password_completed=True,
    )
    if existing:
        current = await _mixed_activation_counts(database, seed)
        async with open_organization_grant_change(
            database, RequestFingerprintService(RequestFingerprintKey(b"K" * 32))
        ) as service:
            await service.set_grant(
                access=seed.actor.access,
                command=SetOrganizationActionGrantCommand(
                    organization_id=record.organization_id,
                    recipient_principal_id=seed.bob_id,
                    action_id=ActionId("create-projects"),
                    can_grant=True,
                    expected_access_revision=current["organization_revision"],
                ),
                context=IdempotencyContextDTO(
                    method=HttpMethod.PUT,
                    requested_route=f"/v1/organizations/{record.organization_id.value}/grants/{seed.bob_id.value}/create-projects",
                    key=IdempotencyKey("before-mixed-organization"),
                ),
            )
        project_grant = await change_project_grant(
            database,
            seed,
            revision=current["project_revision"],
            key="before-mixed-project",
            can_grant=True,
            action_id=ActionId("create-access-groups"),
        )
        async with open_access_group_grant_change(
            database, RequestFingerprintService(RequestFingerprintKey(b"K" * 32))
        ) as service:
            await service.set_grant(
                access=seed.actor.access,
                command=SetAccessGroupActionGrantCommand(
                    project_id=seed.project.project_id,
                    group_id=group,
                    recipient_principal_id=seed.bob_id,
                    action_id=ActionId("add-documents"),
                    can_grant=False,
                    expected_access_revision=project_grant.access_revision,
                ),
                context=IdempotencyContextDTO(
                    method=HttpMethod.PUT,
                    requested_route=f"/v1/projects/{seed.project.project_id.value}/access-groups/{group.value}/grants/{seed.bob_id.value}/add-documents",
                    key=IdempotencyKey("before-mixed-group"),
                ),
            )
    before = await _mixed_activation_counts(database, seed)
    context = IdempotencyContextDTO(
        method=HttpMethod.POST,
        requested_route="/v1/invitations/activate",
        key=IdempotencyKey("mixed-activation"),
    )
    async with database.session() as session:
        result = await _activation_service(session).activate(
            proof=proof, command=ActivateInvitationCommand(token=token), context=context
        )
    assert (result.principal_id == seed.bob_id) is existing
    assert result.organization_access_revision == before["organization_revision"] + (
        1 if existing else 2
    )
    assert result.project_access_revisions == (
        InvitationProjectAccessRevisionDTO(
            project_id=seed.project.project_id,
            access_revision=before["project_revision"] + (4 if existing else 6),
        ),
    )
    assert result.operation.created
    recipient = result.principal_id.value
    async with database.session() as session:
        membership = await session.get(
            ProjectMembershipRow, (seed.project.project_id.value, recipient)
        )
        ordinary = await session.get(
            GroupMembershipRow, (seed.project.project_id.value, group.value, recipient)
        )
        manager = await session.get(
            GroupManagerRow, (seed.project.project_id.value, group.value, recipient)
        )
        organization = await session.get(
            OrganizationActionGrantRow, (record.organization_id.value, recipient, "create-projects")
        )
        project = await session.get(
            ProjectActionGrantRow,
            (seed.project.project_id.value, recipient, "create-access-groups"),
        )
        grouped = await session.get(
            GroupActionGrantRow,
            (seed.project.project_id.value, group.value, recipient, "add-documents"),
        )
        app = await session.get(
            ApplicationActionGrantRow,
            (seed.project.project_id.value, application.value, recipient, "issue-application-keys"),
        )
        assert membership is not None and ordinary is not None and manager is not None
        assert organization is not None and organization.can_grant is False
        assert project is not None and grouped is not None and app is not None
        assert project.can_grant and grouped.can_grant and app.can_grant
        assert all(
            row.assigned_by_principal_id == record.issuer_principal_id.value
            for row in (membership, ordinary, manager, organization, project, grouped, app)
        )
        audits = (
            await session.scalars(
                select(AccessAuditEventRow).where(
                    AccessAuditEventRow.correlation_id == result.operation.operation_id.value
                )
            )
        ).all()
        completion = [audit for audit in audits if audit.target_kind == "invitation"]
        assert len(completion) == 1 and completion[0].actor_principal_id == recipient
        assert len(audits) == (8 if existing else 9)
        assert all(
            audit.actor_principal_id == record.issuer_principal_id.value
            for audit in audits
            if audit.target_kind != "invitation"
        )
        original = await session.get(
            InvitationActivationOperationRow, result.operation.operation_id.value
        )
        consumed = await session.get(InvitationRow, record.invitation_id.value)
        assert (
            original is not None
            and original.completed_at is not None
            and consumed is not None
            and original.principal_id == recipient
        )
        assert (
            consumed.consumed_by_principal_id == recipient
            and consumed.consumed_at == original.completed_at
        )
        assert (
            original.expires_at
            == result.operation.expires_at
            == original.completed_at + timedelta(hours=24)
        )
    departed = await change_membership(
        database,
        seed,
        principal_id=result.principal_id,
        revision=result.project_access_revisions[0].access_revision,
        key="leave-after-mixed-activation",
        remove=True,
    )
    assert departed.changed
    after_departure = await _mixed_activation_counts(database, seed)
    async with database.session() as session:
        replay = await _activation_service(session).activate(
            proof=replace(proof, password_completed=None),
            command=ActivateInvitationCommand(token=token),
            context=context,
        )
    assert replay == replace(result, operation=replace(result.operation, created=False))
    assert await _mixed_activation_counts(database, seed) == after_departure
    async with database.session() as session:
        assert (
            await session.get(ProjectMembershipRow, (seed.project.project_id.value, recipient))
            is None
        )
        assert (
            await session.get(
                GroupMembershipRow, (seed.project.project_id.value, group.value, recipient)
            )
            is None
        )
        assert (
            await session.get(
                GroupManagerRow, (seed.project.project_id.value, group.value, recipient)
            )
            is None
        )
        assert (
            await session.get(
                ProjectActionGrantRow,
                (seed.project.project_id.value, recipient, "create-access-groups"),
            )
            is None
        )
        assert (
            await session.get(
                GroupActionGrantRow,
                (seed.project.project_id.value, group.value, recipient, "add-documents"),
            )
            is None
        )
        assert (
            await session.get(
                ApplicationActionGrantRow,
                (
                    seed.project.project_id.value,
                    application.value,
                    recipient,
                    "issue-application-keys",
                ),
            )
            is None
        )


@pytest.mark.parametrize("cancel", [False, True])
async def test_mixed_activation_late_failure_rolls_back_every_effect(
    database: Database, cancel: bool
) -> None:
    seed, _, _, record, token = await _assignment_invitation(database)
    proof = replace(_unadmitted_invitation_proof(seed.actor), password_completed=True)
    before = await _mixed_activation_counts(database, seed)
    original = PostgresApplicationAccountActionGrantWriter.apply_invitation_grant
    injected = RuntimeError("Controlled late assignment failure")

    async def fail_after_last_assignment(
        self: PostgresApplicationAccountActionGrantWriter,
        *,
        binding: InvitationActivationBindingDTO,
        facts: ApplicationAccountGrantManagementFactsDTO,
        recipient_principal_id: PrincipalId,
        after: ActionGrantState,
    ) -> int:
        await original(
            self,
            binding=binding,
            facts=facts,
            recipient_principal_id=recipient_principal_id,
            after=after,
        )
        if cancel:
            raise asyncio.CancelledError
        raise injected

    with patch.object(
        PostgresApplicationAccountActionGrantWriter,
        "apply_invitation_grant",
        fail_after_last_assignment,
    ):
        async with database.session() as session:
            with pytest.raises(asyncio.CancelledError if cancel else RuntimeError) as caught:
                await _activation_service(session).activate(
                    proof=proof,
                    command=ActivateInvitationCommand(token=token),
                    context=IdempotencyContextDTO(
                        method=HttpMethod.POST,
                        requested_route="/v1/invitations/activate",
                        key=IdempotencyKey("failed-mixed-activation"),
                    ),
                )
            if not cancel:
                assert caught.value is injected
    assert await _mixed_activation_counts(database, seed) == before
    async with database.session() as session:
        assert await PostgresInvitationFactsReader(session).read_by_digest(token.digest()) == record
        assert (
            await session.get(
                HumanIdentityLinkRow, (proof.identity.authority.value, proof.identity.subject.value)
            )
            is None
        )


async def test_concurrent_mixed_activation_consumes_once_for_one_verified_subject(
    database: Database,
) -> None:
    seed, _, _, record, token = await _assignment_invitation(database)
    proofs = [
        replace(
            _unadmitted_invitation_proof(seed.actor),
            identity=VerifiedHumanIdentityDTO(
                authority=seed.actor.binding.identity.authority,
                subject=IdentitySubject(str(UUID(int=subject))),
            ),
            password_completed=True,
        )
        for subject in (900, 901)
    ]
    pids: list[asyncio.Future[int]] = [asyncio.get_running_loop().create_future() for _ in proofs]

    async def activate(index: int) -> InvitationActivationResultDTO:
        async with database.session() as session:
            _record_activation_pid(session, pids[index])
            return await _activation_service(session).activate(
                proof=proofs[index],
                command=ActivateInvitationCommand(token=token),
                context=IdempotencyContextDTO(
                    method=HttpMethod.POST,
                    requested_route="/v1/invitations/activate",
                    key=IdempotencyKey(f"competing-mixed-{index}"),
                ),
            )

    tasks: list[asyncio.Task[InvitationActivationResultDTO]] = []
    work_error: BaseException | None = None
    observed_errors: tuple[BaseException, ...] = ()
    try:
        async with database.session() as holder, holder.begin():
            holder_pid = await holder.scalar(select(func.pg_backend_pid()))
            assert isinstance(holder_pid, int)
            await holder.scalar(
                select(OrganizationRow.id)
                .where(OrganizationRow.id == record.organization_id.value)
                .with_for_update()
            )
            tasks = [asyncio.create_task(activate(index)) for index in range(2)]
            last_observation = "worker0: unobserved | worker1: unobserved"
            try:
                async with asyncio.timeout(2):
                    while not all(ready.done() for ready in pids):
                        done, _ = await asyncio.wait(
                            (*tasks, *(ready for ready in pids if not ready.done())),
                            return_when=asyncio.FIRST_COMPLETED,
                        )
                        for task in tasks:
                            if task in done:
                                await task
                                raise AssertionError("A consumer ended before its held turn.")
                    worker0, worker1 = pids[0].result(), pids[1].result()
                    while True:
                        for task in tasks:
                            if task.done():
                                await task
                                raise AssertionError("A consumer ended before its held turn.")
                        async with database.session() as observer:
                            blockers0 = await observer.scalar(
                                select(func.pg_blocking_pids(worker0, type_=ARRAY(Integer)))
                            )
                            blockers1 = await observer.scalar(
                                select(func.pg_blocking_pids(worker1, type_=ARRAY(Integer)))
                            )
                        labels: list[str] = []
                        for label, blockers in (("worker0", blockers0), ("worker1", blockers1)):
                            labels.append(
                                f"{label}: unobserved"
                                if blockers is None
                                else f"{label}: holder={holder_pid in blockers}, worker0={worker0 in blockers}, "
                                f"worker1={worker1 in blockers}, other={any(pid not in (holder_pid, worker0, worker1) for pid in blockers)}"
                            )
                        last_observation = " | ".join(labels)
                        # Tuple-lock consumers can queue behind their known peer.
                        # Each accepted path must still reach the held original turn.
                        if blockers0 is not None and blockers1 is not None:
                            direct0, direct1 = holder_pid in blockers0, holder_pid in blockers1
                            known0 = all(pid in (holder_pid, worker1) for pid in blockers0)
                            known1 = all(pid in (holder_pid, worker0) for pid in blockers1)
                            through0 = direct0 or (worker1 in blockers0 and direct1)
                            through1 = direct1 or (worker0 in blockers1 and direct0)
                            if known0 and known1 and through0 and through1:
                                for task in tasks:
                                    if task.done():
                                        await task
                                        raise AssertionError(
                                            "A consumer ended before its held turn."
                                        )
                                break
                        await asyncio.sleep(0.01)
            except BaseException as error:
                error.add_note("Last bounded consumption wait: " + last_observation)
                raise
        async with asyncio.timeout(8):
            outcomes = await asyncio.gather(*tasks, return_exceptions=True)
        observed_errors = tuple(
            outcome for outcome in outcomes if isinstance(outcome, BaseException)
        )
        unexpected = [
            error for error in observed_errors if not isinstance(error, ResourceNotFoundError)
        ]
        if unexpected:
            raise BaseExceptionGroup("Competing activation failed unexpectedly", unexpected)
        winners = [
            outcome for outcome in outcomes if isinstance(outcome, InvitationActivationResultDTO)
        ]
        losers = [outcome for outcome in outcomes if isinstance(outcome, ResourceNotFoundError)]
        assert len(winners) == len(losers) == 1
        winner = winners[0]
        async with database.session() as session:
            stored = await session.get(InvitationRow, record.invitation_id.value)
            assert (
                stored is not None and stored.consumed_by_principal_id == winner.principal_id.value
            )
            assert (
                await session.scalar(
                    select(func.count()).select_from(InvitationActivationOperationRow)
                )
                == 1
            )
            links = (
                await session.scalars(
                    select(HumanIdentityLinkRow).where(
                        HumanIdentityLinkRow.authority == proofs[0].identity.authority.value,
                        HumanIdentityLinkRow.subject.in_(
                            [proof.identity.subject.value for proof in proofs]
                        ),
                    )
                )
            ).all()
            assert len(links) == 1 and links[0].principal_id == winner.principal_id.value
            assert (
                await session.get(
                    ProjectMembershipRow, (seed.project.project_id.value, winner.principal_id.value)
                )
                is not None
            )
    except BaseException as error:
        work_error = error
        raise
    finally:
        try:
            async with asyncio.timeout(3):
                for task in tasks:
                    if not task.done():
                        task.cancel()
                cleanup_outcomes = await asyncio.shield(
                    asyncio.gather(*tasks, return_exceptions=True)
                )
                if any(not task.done() for task in tasks):
                    raise RuntimeError("Competing activation cleanup is incomplete.")
            cleanup_errors = [
                outcome
                for outcome in cleanup_outcomes
                if isinstance(outcome, BaseException)
                and not isinstance(outcome, asyncio.CancelledError)
                and outcome is not work_error
                and not any(outcome is observed for observed in observed_errors)
            ]
            if cleanup_errors:
                raise BaseExceptionGroup("Competing activation task cleanup failed", cleanup_errors)
        except BaseException as cleanup_error:
            if work_error is not None and cleanup_error is not work_error:
                raise BaseExceptionGroup(
                    "Competing activation and cleanup failed", [work_error, cleanup_error]
                ) from None
            raise


async def test_recovery_committing_first_blocks_waiting_mixed_first_activation(
    database: Database,
) -> None:
    seed, _, _, record, token = await _assignment_invitation(database)
    proof = replace(_unadmitted_invitation_proof(seed.actor), password_completed=True)
    before = await _mixed_activation_counts(database, seed)
    pid_ready: asyncio.Future[int] = asyncio.get_running_loop().create_future()

    async def activate() -> InvitationActivationResultDTO:
        async with database.session() as session:
            _record_activation_pid(session, pid_ready)
            return await _activation_service(session).activate(
                proof=proof,
                command=ActivateInvitationCommand(token=token),
                context=IdempotencyContextDTO(
                    method=HttpMethod.POST,
                    requested_route="/v1/invitations/activate",
                    key=IdempotencyKey("recovery-first-mixed"),
                ),
            )

    task: asyncio.Task[InvitationActivationResultDTO] | None = None
    work_error: BaseException | None = None
    observed_errors: tuple[BaseException, ...] = ()
    try:
        async with database.session() as recovery, recovery.begin():
            holder_pid = await recovery.scalar(select(func.pg_backend_pid()))
            assert isinstance(holder_pid, int)
            await IdentityRecoveryAdmissionService(
                PostgresIdentityRecoveryAdmissionWriter(
                    recovery,
                    installation_id=seed.actor.binding.installation_id,
                    authority=proof.identity.authority,
                )
            ).admit(
                IdentityRecoveryEventDTO(
                    flow_id=IdentityRecoveryFlowId(uuid4()),
                    identity=proof.identity,
                    event_kind=IdentityRecoveryEventKind.RECOVERY,
                )
            )
            task = asyncio.create_task(activate())
            await _wait_for_activation_block(database, pid_ready, task, holder_pid)
        with pytest.raises(ConflictError) as denied:
            async with asyncio.timeout(8):
                await task
        observed_errors = (denied.value,)
        expected = {
            **before,
            "recoveries": before["recoveries"] + 1,
            "versions": before["versions"] + 1,
        }
        assert await _mixed_activation_counts(database, seed) == expected
        async with database.session() as session:
            assert (
                await PostgresInvitationFactsReader(session).read_by_digest(token.digest())
                == record
            )
            assert (
                await session.get(
                    HumanIdentityLinkRow,
                    (proof.identity.authority.value, proof.identity.subject.value),
                )
                is None
            )
    except BaseException as error:
        work_error = error
        raise
    finally:
        if task is not None:
            try:
                async with asyncio.timeout(3):
                    if not task.done():
                        task.cancel()
                    outcome = (await asyncio.shield(asyncio.gather(task, return_exceptions=True)))[
                        0
                    ]
                    if not task.done():
                        raise RuntimeError("Activation task cleanup is incomplete.")
                if (
                    isinstance(outcome, BaseException)
                    and not isinstance(outcome, asyncio.CancelledError)
                    and outcome is not work_error
                    and not any(outcome is observed for observed in observed_errors)
                ):
                    raise outcome
            except BaseException as cleanup_error:
                if work_error is not None and cleanup_error is not work_error:
                    raise BaseExceptionGroup(
                        "Activation observation and cleanup failed", [work_error, cleanup_error]
                    ) from None
                raise


async def test_mixed_first_activation_commits_before_waiting_recovery_observes_new_link(
    database: Database,
) -> None:
    seed, _, _, _, token = await _assignment_invitation(database)
    proof = replace(_unadmitted_invitation_proof(seed.actor), password_completed=True)
    context = IdempotencyContextDTO(
        method=HttpMethod.POST,
        requested_route="/v1/invitations/activate",
        key=IdempotencyKey("activation-before-recovery"),
    )
    completed: asyncio.Future[InvitationActivationResultDTO] = (
        asyncio.get_running_loop().create_future()
    )
    release = asyncio.Event()
    original_complete = PostgresInvitationWriter.complete_activation
    activation_pid: asyncio.Future[int] = asyncio.get_running_loop().create_future()

    async def pause_completed(
        self: PostgresInvitationWriter,
        *,
        binding: InvitationActivationBindingDTO,
        digest: InvitationTokenDigest,
        organization_access_revision: int,
        project_access_revisions: tuple[InvitationProjectAccessRevisionDTO, ...],
    ) -> InvitationActivationResultDTO:
        result = await original_complete(
            self,
            binding=binding,
            digest=digest,
            organization_access_revision=organization_access_revision,
            project_access_revisions=project_access_revisions,
        )
        completed.set_result(result)
        await release.wait()
        return result

    async def activate() -> InvitationActivationResultDTO:
        async with database.session() as session:
            _record_activation_pid(session, activation_pid)
            return await _activation_service(session).activate(
                proof=proof, command=ActivateInvitationCommand(token=token), context=context
            )

    pid_ready: asyncio.Future[int] = asyncio.get_running_loop().create_future()

    async def recover() -> None:
        async with database.session() as session, session.begin():
            _record_activation_pid(session, pid_ready)
            await IdentityRecoveryAdmissionService(
                PostgresIdentityRecoveryAdmissionWriter(
                    session,
                    installation_id=seed.actor.binding.installation_id,
                    authority=proof.identity.authority,
                )
            ).admit(
                IdentityRecoveryEventDTO(
                    flow_id=IdentityRecoveryFlowId(uuid4()),
                    identity=proof.identity,
                    event_kind=IdentityRecoveryEventKind.RECOVERY,
                )
            )

    activation_task: asyncio.Task[InvitationActivationResultDTO] | None = None
    recovery_task: asyncio.Task[None] | None = None
    work_error: BaseException | None = None
    try:
        with patch.object(PostgresInvitationWriter, "complete_activation", pause_completed):
            activation_task = asyncio.create_task(activate())
            done, _ = await asyncio.wait(
                [completed, activation_task], timeout=8, return_when=asyncio.FIRST_COMPLETED
            )
            assert done
            if completed not in done:
                await activation_task
                raise AssertionError("Activation ended before its completion observation.")
            result = completed.result()
            async with database.session() as observer:
                operation = await observer.get(
                    InvitationActivationOperationRow, result.operation.operation_id.value
                )
                assert operation is None
            recovery_task = asyncio.create_task(recover())
            assert activation_pid.done()
            await _wait_for_activation_block(
                database, pid_ready, recovery_task, activation_pid.result()
            )
            release.set()
            async with asyncio.timeout(8):
                assert await activation_task == result
                await recovery_task
        async with database.session() as session:
            link = await session.get(
                HumanIdentityLinkRow, (proof.identity.authority.value, proof.identity.subject.value)
            )
            version = await session.get(
                HumanCredentialVersionRow,
                (
                    seed.actor.binding.installation_id.value,
                    proof.identity.authority.value,
                    proof.identity.subject.value,
                ),
            )
            recovery = (
                await session.scalars(
                    select(IdentityRecoveryAdmissionRow).where(
                        IdentityRecoveryAdmissionRow.subject == proof.identity.subject.value,
                        IdentityRecoveryAdmissionRow.authority == proof.identity.authority.value,
                    )
                )
            ).one()
            assert link is not None and link.principal_id == result.principal_id.value
            assert version is not None and version.version == 2 and recovery.released_at is None
        async with database.session() as session:
            with pytest.raises(ConflictError):
                await _activation_service(session).activate(
                    proof=replace(proof, password_completed=None),
                    command=ActivateInvitationCommand(token=token),
                    context=context,
                )
    except BaseException as error:
        work_error = error
        raise
    finally:
        release.set()
        try:
            cleanup_outcomes: list[object] = []
            async with asyncio.timeout(3):
                for task in (activation_task, recovery_task):
                    if task is not None and not task.done():
                        task.cancel()
                if activation_task is not None:
                    cleanup_outcomes.extend(
                        await asyncio.shield(
                            asyncio.gather(activation_task, return_exceptions=True)
                        )
                    )
                if recovery_task is not None:
                    cleanup_outcomes.extend(
                        await asyncio.shield(asyncio.gather(recovery_task, return_exceptions=True))
                    )
                if any(
                    task is not None and not task.done()
                    for task in (activation_task, recovery_task)
                ):
                    raise RuntimeError("Activation and recovery cleanup is incomplete.")
            cleanup_errors = [
                outcome
                for outcome in cleanup_outcomes
                if isinstance(outcome, BaseException)
                and not isinstance(outcome, asyncio.CancelledError)
                and outcome is not work_error
            ]
            if cleanup_errors:
                raise BaseExceptionGroup(
                    "Activation and recovery task cleanup failed", cleanup_errors
                )
        except BaseException as cleanup_error:
            if work_error is not None and cleanup_error is not work_error:
                raise BaseExceptionGroup(
                    "Activation/recovery observation and cleanup failed",
                    [work_error, cleanup_error],
                ) from None
            raise


@pytest.mark.parametrize("cancel", [False, True])
async def test_mixed_activation_identity_wait_is_bounded_and_cancellable(
    database: Database, cancel: bool
) -> None:
    seed, _, _, record, token = await _assignment_invitation(database)
    proof = replace(_unadmitted_invitation_proof(seed.actor), password_completed=True)
    before = await _mixed_activation_counts(database, seed)
    pid_ready: asyncio.Future[int] = asyncio.get_running_loop().create_future()

    async def activate() -> InvitationActivationResultDTO:
        async with database.session() as session:
            _record_activation_pid(session, pid_ready)
            return await _activation_service(session).activate(
                proof=proof,
                command=ActivateInvitationCommand(token=token),
                context=IdempotencyContextDTO(
                    method=HttpMethod.POST,
                    requested_route="/v1/invitations/activate",
                    key=IdempotencyKey("bounded-mixed-activation"),
                ),
            )

    task: asyncio.Task[InvitationActivationResultDTO] | None = None
    work_error: BaseException | None = None
    observed_errors: tuple[BaseException, ...] = ()
    try:
        async with database.session() as holder, holder.begin():
            holder_pid = await holder.scalar(select(func.pg_backend_pid()))
            assert isinstance(holder_pid, int)
            await PostgresIdentityCoordinator(holder).acquire(
                installation_id=seed.actor.binding.installation_id, identity=proof.identity
            )
            task = asyncio.create_task(activate())
            await _wait_for_activation_block(database, pid_ready, task, holder_pid)
            if cancel:
                task.cancel()
            with pytest.raises(
                asyncio.CancelledError if cancel else DependencyUnavailableError
            ) as stopped:
                async with asyncio.timeout(8):
                    await task
            observed_errors = (stopped.value,)
        assert await _mixed_activation_counts(database, seed) == before
        async with database.session() as session:
            assert (
                await PostgresInvitationFactsReader(session).read_by_digest(token.digest())
                == record
            )
    except BaseException as error:
        work_error = error
        raise
    finally:
        if task is not None:
            try:
                async with asyncio.timeout(3):
                    if not task.done():
                        task.cancel()
                    outcome = (await asyncio.shield(asyncio.gather(task, return_exceptions=True)))[
                        0
                    ]
                    if not task.done():
                        raise RuntimeError("Activation task cleanup is incomplete.")
                if (
                    isinstance(outcome, BaseException)
                    and not isinstance(outcome, asyncio.CancelledError)
                    and outcome is not work_error
                    and not any(outcome is observed for observed in observed_errors)
                ):
                    raise outcome
            except BaseException as cleanup_error:
                if work_error is not None and cleanup_error is not work_error:
                    raise BaseExceptionGroup(
                        "Activation observation and cleanup failed", [work_error, cleanup_error]
                    ) from None
                raise


def _invitation_http_settings(
    postgres: DatabaseSettings, seed: ProjectCreationSeedDTO, *, admin: bool = True
) -> ApplicationSettings:
    """Configure controlled provider seams over the actual application and isolated database."""
    return get_settings().model_copy(
        update={
            "database": postgres,
            "kratos": KratosSettings(
                public_url=HttpUrl("http://kratos.test"),
                admin_url=HttpUrl("http://kratos-admin.test") if admin else None,
                authority=seed.binding.identity.authority,
            ),
            "hydra": None,
            "discovery": None,
            "csrf": CSRFSettings(trusted_origins=(HttpUrl("https://account.test"),)),
            "application_key_authentication": ApplicationKeyAuthenticationSettings(
                http_audience="https://api.test"
            ),
        }
    )


async def test_registered_invitation_mixed_activation_and_original_replay(
    database: Database, temporary_postgres_settings: DatabaseSettings
) -> None:
    """Register all four transports around real issuance and seven atomic native effects."""
    seed, group_id, account_id, template, _ = await _assignment_invitation(database)
    reviewed = await _review(database, seed.actor, template.assignments, (seed.project.project_id,))
    project_id = str(seed.project.project_id.value)
    assignments: list[dict[str, object]] = [
        {"kind": "project-membership", "projectId": project_id},
        {"kind": "group-membership", "projectId": project_id, "accessGroupId": str(group_id.value)},
        {"kind": "group-manager", "projectId": project_id, "accessGroupId": str(group_id.value)},
        {
            "kind": "action-grant",
            "target": {
                "kind": "organization",
                "organizationId": str(seed.actor.organization_id.value),
            },
            "actionId": "create-projects",
            "canGrant": False,
        },
        {
            "kind": "action-grant",
            "target": {"kind": "project", "projectId": project_id},
            "actionId": "create-access-groups",
            "canGrant": True,
        },
        {
            "kind": "action-grant",
            "target": {
                "kind": "access-group",
                "projectId": project_id,
                "accessGroupId": str(group_id.value),
            },
            "actionId": "add-documents",
            "canGrant": True,
        },
        {
            "kind": "action-grant",
            "target": {
                "kind": "application-account",
                "projectId": project_id,
                "applicationPrincipalId": str(account_id.value),
            },
            "actionId": "issue-application-keys",
            "canGrant": True,
        },
    ]
    body = {
        "organizationId": str(seed.actor.organization_id.value),
        "assignments": assignments,
        "expectedAccessRevision": reviewed.expected_access_revision,
        "expectedProjectAccessRevisions": [
            {"projectId": str(item.project_id.value), "accessRevision": item.access_revision}
            for item in reviewed.expected_project_access_revisions
        ],
        "expiresInSeconds": 3600,
    }
    headers = {
        "Origin": "https://account.test",
        "X-Inframeld-CSRF": "1",
        "Idempotency-Key": "registered-mixed-issue",
    }
    proof = InvitationBrowserProofDTO(
        VerifiedHumanIdentityDTO(
            seed.actor.binding.identity.authority, IdentitySubject(str(UUID(int=900)))
        ),
        True,
    )
    browser = AsyncMock(return_value=seed.actor.binding.identity)
    recipient_verifier = AsyncMock(return_value=proof)
    with (
        patch.object(KratosBrowserSessionVerifier, "verify", browser),
        patch.object(KratosInvitationSessionVerifier, "verify", recipient_verifier),
        TestClient(
            create_app(_invitation_http_settings(temporary_postgres_settings, seed.actor))
        ) as client,
    ):
        client.cookies.set("ory_kratos_session", "controlled-alice")
        first = client.post("/v1/invitations", json=body, headers=headers)
        assert first.status_code == 201
        safe_first = first.json()
        token = InvitationToken(safe_first.pop("invitationToken"))
        assert safe_first["secretAvailable"] is True and safe_first["assignments"] == assignments
        invitation_id = UUID(safe_first["invitationId"])
        replayed_issue = client.post("/v1/invitations", json=body, headers=headers)
        assert replayed_issue.status_code == 201
        assert replayed_issue.json() == {**safe_first, "secretAvailable": False}
        assert "invitationToken" not in replayed_issue.json()
        before = await _mixed_activation_counts(database, seed)
        async with database.session() as session:
            reservation_count = await session.scalar(
                select(func.count()).select_from(IdempotencyReservationRow)
            )
        client.cookies.set("ory_kratos_session", "controlled-new-bob")
        preview = client.post(
            "/v1/invitations/preview",
            json={"invitationToken": token.value},
            headers={key: value for key, value in headers.items() if key != "Idempotency-Key"},
        )
        assert preview.status_code == 200 and preview.json()["assignments"] == assignments
        assert {item["target"]["kind"] for item in preview.json()["scopes"]} == {
            "organization",
            "project",
            "access-group",
            "application-account",
        }
        assert len(preview.json()["scopes"]) == 4
        assert recipient_verifier.call_args.kwargs == {"observe_password_completion": False}
        assert await _mixed_activation_counts(database, seed) == before
        async with database.session() as session:
            assert (
                await session.scalar(select(func.count()).select_from(IdempotencyReservationRow))
                == reservation_count
            )
            assert (
                await session.get(
                    HumanIdentityLinkRow,
                    (proof.identity.authority.value, proof.identity.subject.value),
                )
                is None
            )
        activate_headers = {**headers, "Idempotency-Key": "registered-mixed-activate"}
        activated = client.post(
            "/v1/invitations/activate",
            json={"invitationToken": token.value},
            headers=activate_headers,
        )
        assert activated.status_code == 200
        original = activated.json()
        recipient = PrincipalId(UUID(original["principalId"]))
        assert original["invitationId"] == str(invitation_id)
        assert original["organizationAccessRevision"] == before["organization_revision"] + 2
        assert original["projectAccessRevisions"] == [
            {"projectId": project_id, "accessRevision": before["project_revision"] + 6}
        ]
        assert recipient_verifier.call_args.kwargs == {"observe_password_completion": True}
        after = await _mixed_activation_counts(database, seed)
        for label in (
            "principals",
            "links",
            "versions",
            "memberships",
            "group_members",
            "managers",
            "organization_grants",
            "project_grants",
            "group_grants",
            "application_grants",
            "originals",
        ):
            assert after[label] == before[label] + 1
        assert after["audits"] == before["audits"] + 9
        async with database.session() as session:
            membership = await session.get(
                ProjectMembershipRow, (seed.project.project_id.value, recipient.value)
            )
            ordinary = await session.get(
                GroupMembershipRow, (seed.project.project_id.value, group_id.value, recipient.value)
            )
            manager = await session.get(
                GroupManagerRow, (seed.project.project_id.value, group_id.value, recipient.value)
            )
            organization = await session.get(
                OrganizationActionGrantRow,
                (seed.actor.organization_id.value, recipient.value, "create-projects"),
            )
            project = await session.get(
                ProjectActionGrantRow,
                (seed.project.project_id.value, recipient.value, "create-access-groups"),
            )
            grouped = await session.get(
                GroupActionGrantRow,
                (seed.project.project_id.value, group_id.value, recipient.value, "add-documents"),
            )
            account = await session.get(
                ApplicationActionGrantRow,
                (
                    seed.project.project_id.value,
                    account_id.value,
                    recipient.value,
                    "issue-application-keys",
                ),
            )
            assert membership is not None and ordinary is not None and manager is not None
            assert organization is not None and organization.can_grant is False
            assert project is not None and grouped is not None and account is not None
            assert project.can_grant and grouped.can_grant and account.can_grant
            assert all(
                row.assigned_by_principal_id == seed.actor.access.actor_principal_id.value
                for row in (membership, ordinary, manager, organization, project, grouped, account)
            )
            stored = await session.get(InvitationActivationOperationRow, original["operationId"])
            consumed = await session.get(InvitationRow, invitation_id)
            assert stored is not None and stored.completed_at is not None and consumed is not None
            assert (
                consumed.consumed_by_principal_id == recipient.value
                and consumed.consumed_at == stored.completed_at
            )
            assert (
                stored.expires_at
                == stored.completed_at + timedelta(hours=24)
                == datetime.fromisoformat(original["idempotencyExpiresAt"])
            )
        # Use ordinary guarded producers to remove issuer authority and recipient membership.
        async with open_organization_grant_change(
            database, RequestFingerprintService(RequestFingerprintKey(b"K" * 32))
        ) as service:
            granted = await service.set_grant(
                access=seed.actor.access,
                command=SetOrganizationActionGrantCommand(
                    seed.actor.organization_id,
                    recipient,
                    ActionId("admit-users"),
                    True,
                    after["organization_revision"],
                ),
                context=IdempotencyContextDTO(
                    HttpMethod.PUT,
                    f"/v1/organizations/{seed.actor.organization_id.value}/grants/{recipient.value}/admit-users",
                    IdempotencyKey("registered-recipient-admission-delegation"),
                ),
            )
            removed = await service.remove_grant(
                access=seed.actor.access,
                command=RemoveOrganizationActionGrantCommand(
                    seed.actor.organization_id,
                    seed.actor.access.actor_principal_id,
                    ActionId("admit-users"),
                    granted.access_revision,
                ),
                context=IdempotencyContextDTO(
                    HttpMethod.DELETE,
                    f"/v1/organizations/{seed.actor.organization_id.value}/grants/{seed.actor.access.actor_principal_id.value}/admit-users",
                    IdempotencyKey("registered-issuer-authority-removed"),
                ),
            )
            assert removed.changed
        departed = await change_membership(
            database,
            seed,
            principal_id=recipient,
            revision=original["projectAccessRevisions"][0]["accessRevision"],
            key="registered-recipient-departure",
            remove=True,
        )
        assert departed.changed
        before_replay = await _mixed_activation_counts(database, seed)
        recipient_verifier.return_value = replace(proof, password_completed=None)
        replay = client.post(
            "/v1/invitations/activate",
            json={"invitationToken": token.value},
            headers=activate_headers,
        )
        assert replay.status_code == 200 and replay.json() == original
        assert await _mixed_activation_counts(database, seed) == before_replay
        for response in (first, replayed_issue, preview, activated, replay):
            assert response.headers["cache-control"] == "no-store"


async def test_registered_invitation_revocation_preserves_current_authority_and_original(
    database: Database, temporary_postgres_settings: DatabaseSettings
) -> None:
    """Authenticate real application evidence and retain current human revoke authority."""
    seed, _, account_id, _, _ = await _assignment_invitation(database)
    key = await store_application_key(
        database,
        principal_id=account_id,
        organization_id=seed.actor.organization_id,
        project_id=seed.project.project_id,
        issued_by=seed.actor.access.actor_principal_id,
    )
    headers = {
        "Origin": "https://account.test",
        "X-Inframeld-CSRF": "1",
        "Idempotency-Key": "registered-revocation-issue",
    }
    browser = AsyncMock(return_value=seed.actor.binding.identity)
    with (
        patch.object(KratosBrowserSessionVerifier, "verify", browser),
        TestClient(
            create_app(_invitation_http_settings(temporary_postgres_settings, seed.actor))
        ) as client,
    ):
        client.cookies.set("ory_kratos_session", "controlled-alice")
        issue_body = {
            "organizationId": str(seed.actor.organization_id.value),
            "assignments": [{"kind": "admission-only"}],
            "expectedAccessRevision": await _current_org_revision(database, seed.actor),
            "expectedProjectAccessRevisions": [],
        }
        issued = client.post("/v1/invitations", json=issue_body, headers=headers)
        assert issued.status_code == 201
        safe_issued = issued.json()
        safe_issued.pop("invitationToken")
        invitation_id = UUID(safe_issued["invitationId"])
        route = f"/v1/invitations/{invitation_id}/revoke"
        revision = safe_issued["accessRevision"]
        client.cookies.clear()
        app_headers = {
            "Authorization": "Bearer " + key.value,
            "Idempotency-Key": "application-must-not-administer",
        }
        authenticated = client.get("/v1/application-session", headers=app_headers)
        assert authenticated.status_code == 200
        provider_calls = browser.call_count
        before_app = await _mixed_activation_counts(database, seed)
        for target, payload in (
            ("/v1/invitations", issue_body),
            (route, {"expectedAccessRevision": revision}),
        ):
            denied_app = client.post(target, json=payload, headers=app_headers)
            assert denied_app.status_code == 403 and denied_app.json()["code"] == "access_denied"
            assert (
                denied_app.headers["cache-control"] == "no-store"
                and key.value not in denied_app.text
            )
        assert browser.call_count == provider_calls
        assert await _mixed_activation_counts(database, seed) == before_app
        client.cookies.set("ory_kratos_session", "controlled-alice")
        revoke_headers = {**headers, "Idempotency-Key": "registered-revoke-first"}
        first = client.post(
            route, json={"expectedAccessRevision": revision}, headers=revoke_headers
        )
        assert first.status_code == 200
        original = first.json()
        assert original["revoked"] is True and original["accessRevision"] == revision + 1
        replay = client.post(
            route, json={"expectedAccessRevision": revision}, headers=revoke_headers
        )
        assert replay.status_code == 200 and replay.json() == original
        async with database.session() as session:
            stored = await session.get(InvitationRow, invitation_id)
            assert stored is not None and stored.revoked_at is not None
            revoked_at = stored.revoked_at
        async with open_organization_grant_change(
            database, RequestFingerprintService(RequestFingerprintKey(b"K" * 32))
        ) as service:
            use_only = await service.set_grant(
                access=seed.actor.access,
                command=SetOrganizationActionGrantCommand(
                    seed.actor.organization_id,
                    seed.bob_id,
                    ActionId("admit-users"),
                    False,
                    original["accessRevision"],
                ),
                context=IdempotencyContextDTO(
                    HttpMethod.PUT,
                    f"/v1/organizations/{seed.actor.organization_id.value}/grants/{seed.bob_id.value}/admit-users",
                    IdempotencyKey("registered-bob-use-only"),
                ),
            )
        browser.return_value = VerifiedHumanIdentityDTO(
            seed.actor.binding.identity.authority, IdentitySubject(str(UUID(int=200)))
        )
        client.cookies.set("ory_kratos_session", "controlled-bob")
        denied = client.post(
            route,
            json={"expectedAccessRevision": use_only.access_revision},
            headers={**headers, "Idempotency-Key": "registered-bob-delegator"},
        )
        assert denied.status_code == 403
        async with open_organization_grant_change(
            database, RequestFingerprintService(RequestFingerprintKey(b"K" * 32))
        ) as service:
            delegated = await service.set_grant(
                access=seed.actor.access,
                command=SetOrganizationActionGrantCommand(
                    seed.actor.organization_id,
                    seed.bob_id,
                    ActionId("admit-users"),
                    True,
                    use_only.access_revision,
                ),
                context=IdempotencyContextDTO(
                    HttpMethod.PUT,
                    f"/v1/organizations/{seed.actor.organization_id.value}/grants/{seed.bob_id.value}/admit-users",
                    IdempotencyKey("registered-bob-use-and-grant"),
                ),
            )
        delegated_headers = {**headers, "Idempotency-Key": "registered-bob-delegator"}
        noop = client.post(
            route,
            json={"expectedAccessRevision": delegated.access_revision},
            headers=delegated_headers,
        )
        assert noop.status_code == 200
        noop_original = noop.json()
        assert (
            noop_original["revoked"] is True
            and noop_original["accessRevision"] == delegated.access_revision
        )
        assert noop_original["operationId"] != original["operationId"]
        noop_replay = client.post(
            route,
            json={"expectedAccessRevision": delegated.access_revision},
            headers=delegated_headers,
        )
        assert noop_replay.status_code == 200 and noop_replay.json() == noop_original
        async with database.session() as session:
            current = await session.get(InvitationRow, invitation_id)
            assert current is not None and current.revoked_at == revoked_at
            assert (
                await session.scalar(
                    select(OrganizationRow.access_revision).where(
                        OrganizationRow.id == seed.actor.organization_id.value
                    )
                )
                == delegated.access_revision
            )
            audits = (
                await session.scalars(
                    select(AccessAuditEventRow).where(
                        AccessAuditEventRow.event_type == "invitation_revoked",
                        AccessAuditEventRow.target_id == invitation_id,
                    )
                )
            ).all()
            assert len(audits) == 2
            by_operation = {audit.correlation_id: audit for audit in audits}
            assert (
                by_operation[original["operationId"]].actor_principal_id
                == seed.actor.access.actor_principal_id.value
            )
            assert (
                by_operation[noop_original["operationId"]].actor_principal_id == seed.bob_id.value
            )
            assert by_operation[original["operationId"]].before_values == {
                "access_revision": revision,
                "revoked": False,
            }
            assert by_operation[noop_original["operationId"]].before_values == {
                "access_revision": delegated.access_revision,
                "revoked": True,
            }
        async with open_organization_grant_change(
            database, RequestFingerprintService(RequestFingerprintKey(b"K" * 32))
        ) as service:
            await service.set_grant(
                access=seed.actor.access,
                command=SetOrganizationActionGrantCommand(
                    seed.actor.organization_id,
                    seed.bob_id,
                    ActionId("admit-users"),
                    False,
                    delegated.access_revision,
                ),
                context=IdempotencyContextDTO(
                    HttpMethod.PUT,
                    f"/v1/organizations/{seed.actor.organization_id.value}/grants/{seed.bob_id.value}/admit-users",
                    IdempotencyKey("registered-bob-authority-lost"),
                ),
            )
        before_denied_original = await _mixed_activation_counts(database, seed)
        denied_original = client.post(
            route,
            json={"expectedAccessRevision": delegated.access_revision},
            headers=delegated_headers,
        )
        assert denied_original.status_code == 403
        assert await _mixed_activation_counts(database, seed) == before_denied_original
        for response in (issued, first, replay, denied, noop, noop_replay, denied_original):
            assert response.headers["cache-control"] == "no-store"


async def test_registered_invitation_recipient_profiles_fail_without_partial_state(
    database: Database, temporary_postgres_settings: DatabaseSettings
) -> None:
    """Separate recipient cookie protection, fresh password availability and eligible replay."""
    seed, _, _, record, token = await _assignment_invitation(database)
    proof = InvitationBrowserProofDTO(
        VerifiedHumanIdentityDTO(
            seed.actor.binding.identity.authority, IdentitySubject(str(UUID(int=901)))
        ),
        None,
    )
    recipient_verifier = AsyncMock(return_value=proof)
    headers = {
        "Origin": "https://account.test",
        "X-Inframeld-CSRF": "1",
        "Idempotency-Key": "registered-profile-original",
    }
    before = await _mixed_activation_counts(database, seed)
    async with database.session() as session:
        before_reservations = await session.scalar(
            select(func.count()).select_from(IdempotencyReservationRow)
        )
    with (
        patch.object(KratosInvitationSessionVerifier, "verify", recipient_verifier),
        TestClient(
            create_app(_invitation_http_settings(temporary_postgres_settings, seed.actor))
        ) as client,
    ):
        client.cookies.set("ory_kratos_session", "controlled-new-recipient")
        csrf = client.post(
            "/v1/invitations/activate",
            json={"invitationToken": token.value},
            headers={"Idempotency-Key": "no-csrf"},
        )
        assert csrf.status_code == 403 and recipient_verifier.call_count == 0
        competing = client.post(
            "/v1/invitations/activate",
            json={"invitationToken": token.value},
            headers={**headers, "Authorization": "Bearer human-token"},
        )
        assert competing.status_code == 400 and recipient_verifier.call_count == 0
        client.cookies.clear()
        bearer = client.post(
            "/v1/invitations/activate",
            json={"invitationToken": token.value},
            headers={"Authorization": "Bearer human-token", "Idempotency-Key": "no-cookie"},
        )
        assert bearer.status_code == 401 and recipient_verifier.call_count == 0
        client.cookies.set("ory_kratos_session", "controlled-new-recipient")
        preview = client.post(
            "/v1/invitations/preview",
            json={"invitationToken": token.value},
            headers={k: v for k, v in headers.items() if k != "Idempotency-Key"},
        )
        assert preview.status_code == 200
        assert recipient_verifier.call_args.kwargs == {"observe_password_completion": False}
        unavailable = client.post(
            "/v1/invitations/activate", json={"invitationToken": token.value}, headers=headers
        )
        assert unavailable.status_code == 503
        assert recipient_verifier.call_args.kwargs == {"observe_password_completion": True}
        assert await _mixed_activation_counts(database, seed) == before
        async with database.session() as session:
            current = await session.get(InvitationRow, record.invitation_id.value)
            assert current is not None and current.consumed_at is None
            assert (
                await session.get(
                    HumanIdentityLinkRow,
                    (proof.identity.authority.value, proof.identity.subject.value),
                )
                is None
            )
            assert (
                await session.scalar(select(func.count()).select_from(IdempotencyReservationRow))
                == before_reservations
            )
        recipient_verifier.return_value = replace(proof, password_completed=True)
        activated = client.post(
            "/v1/invitations/activate", json={"invitationToken": token.value}, headers=headers
        )
        assert activated.status_code == 200
        original = activated.json()
        assert original["invitationId"] == str(record.invitation_id.value)
        before_replay = await _mixed_activation_counts(database, seed)
        recipient_verifier.return_value = proof
        replay = client.post(
            "/v1/invitations/activate", json={"invitationToken": token.value}, headers=headers
        )
        assert replay.status_code == 200 and replay.json() == original
        assert await _mixed_activation_counts(database, seed) == before_replay
        for response in (csrf, competing, bearer, preview, unavailable, activated, replay):
            assert response.headers["cache-control"] == "no-store"
            assert token.value not in response.text


@pytest.mark.parametrize("blocked", ["membership", "issuer", None])
async def test_model_connection_invitation_preserves_exact_preview_activation_and_replay(
    database: Database,
    blocked: str | None,
) -> None:
    membership = await seed_membership_project(database)
    seed, project = membership.actor, membership.project
    route = f"/v1/projects/{project.project_id.value}/model-connections"
    base_url = "https://models.example.test/v1"
    fingerprints = RequestFingerprintService(RequestFingerprintKey(b"F" * 32))
    async with open_model_connection_creation(
        database,
        fingerprints,
        ModelConnectionDestinationSettings(https_base_urls=frozenset({base_url})),
    ) as creator:
        connection = await creator.create(
            access=seed.access,
            command=CreateModelConnectionCommand(
                project.project_id,
                ResourceName("invited-connection"),
                SubmittedDisplayName("Invited connection"),
                ModelConnectionAccessDTO(
                    ModelConnectionProvider.OPENAI_COMPATIBLE,
                    base_url,
                    None,
                    ModelConnectionAuthentication.API_KEY,
                ),
            ),
            context=IdempotencyContextDTO(
                HttpMethod.POST, route, IdempotencyKey("create-invited-model")
            ),
        )
    connection_id = connection.connection.connection_id
    model_id = connection_id.value
    target = InvitationModelConnectionTargetDTO(model_id)
    action = ModelConnectionAction.USE.value
    intent = InvitationActionGrantIntentDTO(target, ActionId(action), False)
    assignments = (
        (intent,)
        if blocked == "membership"
        else (
            InvitationProjectMembershipIntentDTO(project.project_id),
            intent,
        )
    )
    issuer = seed.access
    if blocked is None:
        joined = await change_membership(
            database, membership, revision=connection.project_access_revision, key="join-issuer"
        )
        delegated = await change_project_grant(
            database,
            membership,
            revision=joined.access_revision,
            key="issuer-manage-members",
            action_id=ActionId("manage-project-members"),
            can_grant=True,
        )
        async with open_model_connection_grant_change(database, fingerprints) as changer:
            await changer.change(
                seed.access,
                ChangeModelConnectionGrantCommand(
                    connection_id,
                    membership.bob_id,
                    ModelConnectionAction.USE,
                    delegated.access_revision,
                    True,
                ),
                IdempotencyContextDTO(
                    HttpMethod.PUT,
                    f"/v1/model-connections/{model_id}/grants/{membership.bob_id.value}/{action}",
                    IdempotencyKey("issuer-model-delegation"),
                ),
            )
        async with open_organization_grant_change(database, fingerprints) as changer:
            await changer.set_grant(
                access=seed.access,
                command=SetOrganizationActionGrantCommand(
                    seed.organization_id,
                    membership.bob_id,
                    ActionId("admit-users"),
                    False,
                    await _current_org_revision(database, seed),
                ),
                context=IdempotencyContextDTO(
                    HttpMethod.PUT,
                    f"/v1/organizations/{seed.organization_id.value}/grants/{membership.bob_id.value}/admit-users",
                    IdempotencyKey("issuer-admit-users"),
                ),
            )
        issuer = membership.bob_access
    reviewed = await _review(database, seed, assignments, (project.project_id,))
    async with database.session() as session:
        issued = await _administration(session).issue(
            access=issuer,
            command=reviewed,
            context=_context("invite-for-model"),
        )
    assert issued.token is not None
    proof = _unadmitted_invitation_proof(seed)
    async with database.session() as session:
        preview = await _preview_service(session).preview(
            proof=proof,
            query=PreviewInvitationQuery(token=issued.token),
        )
        assert (
            await session.scalar(
                select(HumanIdentityLinkRow.principal_id).where(
                    HumanIdentityLinkRow.subject == proof.identity.subject.value,
                )
            )
            is None
        )
        assert (
            await session.scalar(select(func.count()).select_from(InvitationActivationOperationRow))
            == 0
        )
    assert preview.assignments == assignments
    assert {
        scope.target: scope.display_name for scope in preview.scopes if scope.target == target
    } == {
        target: "Invited connection",
    }
    assert any(
        scope.target == ProjectGrantTargetDTO(project.project_id) for scope in preview.scopes
    )

    grant = ModelConnectionActionGrantRow
    if blocked == "issuer":
        async with database.session() as session, session.begin():
            await session.execute(
                delete(grant).where(
                    grant.model_connection_id == model_id,
                    grant.recipient_principal_id == seed.access.actor_principal_id.value,
                    grant.action == action,
                )
            )
    context = IdempotencyContextDTO(
        HttpMethod.POST, "/v1/invitations/activate", IdempotencyKey("activate-model")
    )
    proof = replace(proof, password_completed=True)
    command = ActivateInvitationCommand(token=issued.token)
    if blocked is not None:
        async with open_invitation_activation(
            database, InvitationFingerprintService(fingerprints)
        ) as activation:
            with pytest.raises(ConflictError):
                await activation.activate(proof=proof, command=command, context=context)
        async with database.session() as session:
            assert (
                await session.scalar(
                    select(HumanIdentityLinkRow.principal_id).where(
                        HumanIdentityLinkRow.subject == proof.identity.subject.value,
                    )
                )
                is None
            )
            invite = await session.get(InvitationRow, issued.invitation_id.value)
            assert invite is not None and invite.consumed_at is None
            assert (
                await session.scalar(
                    select(func.count()).select_from(InvitationActivationOperationRow)
                )
                == 0
            )
        return

    async with open_invitation_activation(
        database, InvitationFingerprintService(fingerprints)
    ) as activation:
        result = await activation.activate(proof=proof, command=command, context=context)
    assert result.operation.created
    assert result.project_access_revisions == (
        InvitationProjectAccessRevisionDTO(
            project.project_id, reviewed.expected_project_access_revisions[0].access_revision + 2
        ),
    )
    key = (project.project_id.value, model_id, result.principal_id.value, action)
    async with database.session() as session:
        assignment = await session.get(grant, key)
        assert assignment is not None and assignment.can_grant is False
        assert assignment.assigned_by_principal_id == issuer.actor_principal_id.value

    departed = await change_membership(
        database,
        membership,
        revision=result.project_access_revisions[0].access_revision,
        key="issuer-departure",
        remove=True,
    )
    assert departed.changed
    async with open_model_connection_grant_change(database, fingerprints) as changer:
        removed = await changer.change(
            seed.access,
            ChangeModelConnectionGrantCommand(
                connection_id,
                result.principal_id,
                ModelConnectionAction.USE,
                departed.access_revision,
                None,
            ),
            IdempotencyContextDTO(
                HttpMethod.DELETE,
                f"/v1/model-connections/{model_id}/grants/{result.principal_id.value}/{action}",
                IdempotencyKey("remove-invited-model-grant"),
            ),
        )
    assert removed.changed
    async with database.session() as session, session.begin():
        now = await session.scalar(select(func.clock_timestamp(type_=DateTime(timezone=True))))
        assert now is not None
        await session.execute(
            update(InvitationRow)
            .where(InvitationRow.id == issued.invitation_id.value)
            .values(
                issued_at=now - timedelta(hours=2),
                expires_at=now - timedelta(hours=1),
            )
        )
        assert await session.scalar(
            select(InvitationRow.expires_at < func.clock_timestamp()).where(
                InvitationRow.id == issued.invitation_id.value
            )
        )
    async with open_invitation_activation(
        database, InvitationFingerprintService(fingerprints)
    ) as activation:
        replay = await activation.activate(
            proof=replace(proof, password_completed=None), command=command, context=context
        )
    assert replay == replace(result, operation=replace(result.operation, created=False))
    async with database.session() as session:
        assert await session.get(grant, key) is None
        assert (
            await session.get(
                ProjectMembershipRow, (project.project_id.value, membership.bob_id.value)
            )
            is None
        )
