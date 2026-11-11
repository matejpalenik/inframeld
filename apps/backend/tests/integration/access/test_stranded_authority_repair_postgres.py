"""Qualify private repair SQL after controlled, completed recipient verification.

Current Ory proof remains a separate installed-consumer qualification. Fixtures use
delivered group/account admission and real current human credential records.
"""

import asyncio
import os
from collections.abc import Awaitable
from dataclasses import replace
from datetime import datetime
from typing import override
from uuid import uuid4

import pytest
from sqlalchemy import delete, event, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from tests.support.access_group_scenarios import group_fingerprints
from tests.support.first_administrator_bootstrap_scenarios import (
    bootstrap_scenario,
    bootstrap_service,
)
from tests.support.project_metadata_scenarios import (
    seed_stranded_repair_target,
    stranded_repair_service,
)
from tests.support.spending_scenarios import wait_for_database_lock

from inframeld_backend.access.application.commands.delete_access_group_command import (
    DeleteAccessGroupCommand,
)
from inframeld_backend.access.application.commands.delete_application_account_command import (
    DeleteApplicationAccountCommand,
)
from inframeld_backend.access.application.commands.repair_stranded_authority_command import (
    RepairStrandedAuthorityCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.action_grantor_repair_responsibility_dto import (
    ActionGrantorRepairResponsibilityDTO,
)
from inframeld_backend.access.application.dtos.application_account_grant_target_dto import (
    ApplicationAccountGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.group_manager_repair_responsibility_dto import (
    GroupManagerRepairResponsibilityDTO,
)
from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
    HumanOAuthCredentialBindingDTO,
)
from inframeld_backend.access.application.dtos.organization_grant_target_dto import (
    OrganizationGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.project_grant_target_dto import ProjectGrantTargetDTO
from inframeld_backend.access.application.dtos.stranded_authority_repair_facts_dto import (
    StrandedAuthorityRepairFactsDTO,
)
from inframeld_backend.access.application.dtos.stranded_authority_repair_receipt_dto import (
    StrandedAuthorityRepairReceiptDTO,
)
from inframeld_backend.access.application.dtos.stranded_authority_repair_result_dto import (
    StrandedAuthorityRepairResultDTO,
)
from inframeld_backend.access.application.dtos.stranded_authority_repaired_audit_event_dto import (
    StrandedAuthorityRepairedAuditEventDTO,
)
from inframeld_backend.access.application.enums.stranded_authority_maintenance_error_code import (
    StrandedAuthorityMaintenanceErrorCode as Code,
)
from inframeld_backend.access.application.errors.stranded_authority_maintenance_error import (
    StrandedAuthorityMaintenanceError,
)
from inframeld_backend.access.application.services.application_account_deletion_fingerprint_service import (
    ApplicationAccountDeletionFingerprintService,
)
from inframeld_backend.access.application.services.principal_access_evaluation_service import (
    PrincipalAccessEvaluationService,
)
from inframeld_backend.access.application.services.stranded_authority_fingerprint_service import (
    StrandedAuthorityFingerprintService,
)
from inframeld_backend.access.application.value_objects.human_access_token_credential import (
    HumanAccessTokenCredential,
)
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.policies.human_authentication_policy import (
    HumanAuthenticationPolicy,
)
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.infrastructure.readers.postgres_stranded_authority_repair_facts_reader import (
    PostgresStrandedAuthorityRepairFactsReader,
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
from inframeld_backend.access.infrastructure.rows.host_maintenance_receipt_row import (
    HostMaintenanceReceiptRow,
)
from inframeld_backend.access.infrastructure.rows.human_credential_version_row import (
    HumanCredentialVersionRow,
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
from inframeld_backend.access.infrastructure.rows.project_metadata_repair_receipt_row import (
    ProjectMetadataRepairReceiptRow,
)
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.access.infrastructure.rows.stranded_authority_repair_receipt_row import (
    StrandedAuthorityRepairReceiptRow,
)
from inframeld_backend.access.infrastructure.writers.postgres_project_metadata_audit_writer import (
    PostgresProjectMetadataAuditWriter,
)
from inframeld_backend.access.infrastructure.writers.postgres_stranded_authority_audit_writer import (
    PostgresStrandedAuthorityAuditWriter,
)
from inframeld_backend.access.infrastructure.writers.postgres_stranded_authority_repair_writer import (
    PostgresStrandedAuthorityRepairWriter,
)
from inframeld_backend.bootstrap.access_group_composition import open_access_group_deletion
from inframeld_backend.bootstrap.application_account_composition import (
    open_application_account_deletion,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.deletion_status_retention_profile import (
    DeletionStatusRetentionProfile,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.application.value_objects.request_fingerprint_key import (
    RequestFingerprintKey,
)
from inframeld_backend.shared.application.value_objects.request_id import RequestId
from inframeld_backend.shared.infrastructure.resources.database import Database

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
        reason="Requires isolated PostgreSQL integration services",
    ),
]


@pytest.mark.parametrize(
    "kind", ["organization", "project", "group-manager", "group-action", "application-account"]
)
async def test_current_facts_observe_exact_existing_access_responsibility(
    database: Database, kind: str
) -> None:
    access, request, holder = await seed_stranded_repair_target(database, kind)
    async with database.session() as session, session.begin():
        facts = await PostgresStrandedAuthorityRepairFactsReader(session).read(
            access=access, command=request
        )
        assert facts is not None
        assert facts.responsibility == request.responsibility
        assert facts.recipient.id == access.actor_principal_id
        assert facts.target_exists and facts.access_revision == request.expected_access_revision
        assert facts.eligible_grantor_exists is holder
        assert facts.observed_at.tzinfo is not None
        assert facts.oauth_credential_facts.current_version is not None


async def test_absent_original_is_observed_in_the_common_host_namespace(database: Database) -> None:
    _, request, _ = await seed_stranded_repair_target(database, "project")
    async with database.session() as session, session.begin():
        assert (
            await PostgresStrandedAuthorityRepairFactsReader(session).receipt(
                installation_id=request.expected_installation_id, operation_id=request.operation_id
            )
            is None
        )


async def _authorized_group_original(
    session: AsyncSession, access: AccessContextDTO, request: RepairStrandedAuthorityCommand
) -> tuple[StrandedAuthorityRepairFactsDTO, StrandedAuthorityRepairReceiptDTO]:
    responsibility = request.responsibility
    assert isinstance(responsibility, GroupManagerRepairResponsibilityDTO)
    observed = await PostgresStrandedAuthorityRepairFactsReader(session).read(
        access=access, command=request
    )
    assert observed is not None and observed.is_project_member
    group = await session.get(AccessGroupRow, responsibility.access_group_id.value)
    assert group is not None and group.project_id == responsibility.project_id.value
    eligibility = PrincipalAccessEvaluationService.evaluate(
        access=access,
        principal=observed.recipient,
        has_pending_recovery=observed.has_pending_recovery,
        oauth_credential_facts=observed.oauth_credential_facts,
    )
    assert HumanAuthenticationPolicy.may_authenticate(eligibility)
    assert (
        await session.scalar(
            select(func.count())
            .select_from(GroupManagerRow)
            .where(GroupManagerRow.group_id == responsibility.access_group_id.value)
        )
        == 0
    )
    assert observed.target_exists and observed.target_accepts_assignment
    facts = replace(observed, eligible_grantor_exists=False)
    result = StrandedAuthorityRepairResultDTO(
        request.operation_id,
        request.expected_installation_id,
        observed.recipient.organization_id,
        responsibility,
        observed.recipient.id,
        observed.access_revision + 1,
    )
    fingerprint = StrandedAuthorityFingerprintService(
        RequestFingerprintService(RequestFingerprintKey(b"K" * 32))
    )
    binding = access.authentication_evidence
    from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
        HumanOAuthCredentialBindingDTO,
    )

    assert isinstance(binding, HumanOAuthCredentialBindingDTO)
    original = StrandedAuthorityRepairReceiptDTO(
        fingerprint.for_repair(request, binding.identity),
        binding.identity,
        request.expected_identity_id,
        request.operator_label,
        request.reason,
        facts.access_revision,
        facts.observed_at,
        result,
    )
    return facts, original


async def test_writer_commits_member_and_manager_revision_audit_and_safe_original(
    database: Database,
) -> None:
    access, request, _ = await seed_stranded_repair_target(database, "group-manager")
    async with database.session() as session, session.begin():
        facts, original = await _authorized_group_original(session, access, request)
        writer = PostgresStrandedAuthorityRepairWriter(
            session,
            PostgresStrandedAuthorityAuditWriter(
                session, PostgresProjectMetadataAuditWriter(session)
            ),
        )
        assert await writer.record(original)
        await writer.assign(facts=facts, receipt=original)
    responsibility = request.responsibility
    assert isinstance(responsibility, GroupManagerRepairResponsibilityDTO)
    key = (
        responsibility.project_id.value,
        responsibility.access_group_id.value,
        access.actor_principal_id.value,
    )
    async with database.session() as session:
        assert await session.get(GroupMembershipRow, key) is not None
        assert await session.get(GroupManagerRow, key) is not None
        assert (
            await session.scalar(
                select(ProjectRow.access_revision).where(
                    ProjectRow.id == responsibility.project_id.value
                )
            )
            == request.expected_access_revision + 1
        )
        parent = await session.get(
            HostMaintenanceReceiptRow,
            (request.expected_installation_id.value, request.operation_id.value),
        )
        child = await session.get(
            StrandedAuthorityRepairReceiptRow,
            (request.expected_installation_id.value, request.operation_id.value),
        )
        assert (
            parent is not None
            and parent.mode == "repair-stranded-authority"
            and parent.outcome == "repaired"
        )
        assert child is not None and child.access_group_id == responsibility.access_group_id.value
        assert child.recipient_id == access.actor_principal_id.value
        assert child.after_revision == child.before_revision + 1
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AccessAuditEventRow)
                .where(AccessAuditEventRow.event_type == "stranded_authority_repaired")
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(GroupActionGrantRow)
                .where(GroupActionGrantRow.group_id == responsibility.access_group_id.value)
            )
            == 0
        )


async def test_operator_audit_preserves_exact_responsibility_and_safe_attribution(
    database: Database,
) -> None:
    access, request, _ = await seed_stranded_repair_target(database, "group-manager")
    async with database.session() as session, session.begin():
        facts, original = await _authorized_group_original(session, access, request)
        event = StrandedAuthorityRepairedAuditEventDTO(
            original.result.organization_id,
            original.result.recipient_id,
            request.responsibility,
            request.operation_id,
            request.operator_label,
            request.reason,
            facts.access_revision,
            original.result.access_revision,
        )
        await PostgresStrandedAuthorityAuditWriter(
            session, PostgresProjectMetadataAuditWriter(session)
        ).repaired(event)
    async with database.session() as session:
        row = (
            await session.scalars(
                select(AccessAuditEventRow).where(
                    AccessAuditEventRow.correlation_id == request.operation_id.value
                )
            )
        ).one()
        assert row.actor_kind == "operator" and row.actor_reference == request.operator_label
        assert (
            row.actor_principal_id is None
            and row.affected_principal_id == access.actor_principal_id.value
        )
        assert row.reason == request.reason and row.event_type == "stranded_authority_repaired"
        assert row.before_values == {"access_revision": facts.access_revision}
        assert row.after_values == {
            "access_revision": facts.access_revision + 1,
            "member": True,
            "manager": True,
        }


@pytest.mark.parametrize(
    "kind", ["organization", "project", "group-manager", "application-account"]
)
async def test_repair_replays_original_after_exact_assignment_removal_without_regrant(
    database: Database, kind: str
) -> None:
    access, request, _ = await seed_stranded_repair_target(database, kind)
    async with database.session() as session:
        original = await stranded_repair_service(session).repair(access=access, command=request)
    responsibility = request.responsibility
    async with database.session() as session, session.begin():
        if isinstance(responsibility, GroupManagerRepairResponsibilityDTO):
            await session.execute(
                delete(GroupManagerRow).where(
                    GroupManagerRow.project_id == responsibility.project_id.value,
                    GroupManagerRow.group_id == responsibility.access_group_id.value,
                    GroupManagerRow.principal_id == access.actor_principal_id.value,
                )
            )
            await session.execute(
                delete(GroupMembershipRow).where(
                    GroupMembershipRow.project_id == responsibility.project_id.value,
                    GroupMembershipRow.group_id == responsibility.access_group_id.value,
                    GroupMembershipRow.principal_id == access.actor_principal_id.value,
                )
            )
            project = responsibility.project_id
        else:
            target, action = responsibility.target, responsibility.action_id.value
            if isinstance(target, OrganizationGrantTargetDTO):
                await session.execute(
                    delete(OrganizationActionGrantRow).where(
                        OrganizationActionGrantRow.organization_id == target.organization_id.value,
                        OrganizationActionGrantRow.recipient_principal_id
                        == access.actor_principal_id.value,
                        OrganizationActionGrantRow.action == action,
                    )
                )
                await session.execute(
                    update(OrganizationRow)
                    .where(OrganizationRow.id == target.organization_id.value)
                    .values(access_revision=OrganizationRow.access_revision + 1)
                )
                project = None
            elif isinstance(target, ProjectGrantTargetDTO):
                await session.execute(
                    delete(ProjectActionGrantRow).where(
                        ProjectActionGrantRow.project_id == target.project_id.value,
                        ProjectActionGrantRow.recipient_principal_id
                        == access.actor_principal_id.value,
                        ProjectActionGrantRow.action == action,
                    )
                )
                project = target.project_id
            else:
                assert isinstance(target, ApplicationAccountGrantTargetDTO)
                await session.execute(
                    delete(ApplicationActionGrantRow).where(
                        ApplicationActionGrantRow.project_id == target.project_id.value,
                        ApplicationActionGrantRow.application_principal_id
                        == target.application_principal_id.value,
                        ApplicationActionGrantRow.recipient_principal_id
                        == access.actor_principal_id.value,
                        ApplicationActionGrantRow.action == action,
                    )
                )
                project = target.project_id
        if project is not None:
            await session.execute(
                update(ProjectRow)
                .where(ProjectRow.id == project.value)
                .values(access_revision=ProjectRow.access_revision + 1)
            )
    async with database.session() as session:
        replay = await stranded_repair_service(session).repair(
            access=access,
            command=replace(
                request, identity_proof=HumanAccessTokenCredential("fresh-same-human-proof")
            ),
        )
    assert replay == original
    async with database.session() as session, session.begin():
        facts = await PostgresStrandedAuthorityRepairFactsReader(session).read(
            access=access, command=request
        )
        assert facts is not None and facts.eligible_grantor_exists is False
        assert facts.access_revision == original.access_revision + 1
        assert (
            await session.scalar(select(func.count()).select_from(HostMaintenanceReceiptRow)) == 1
        )
        assert (
            await session.scalar(
                select(func.count()).select_from(StrandedAuthorityRepairReceiptRow)
            )
            == 1
        )
    async with database.session() as session:
        with pytest.raises(StrandedAuthorityMaintenanceError) as failure:
            await stranded_repair_service(session).repair(
                access=access, command=replace(request, reason="Different reviewed intent")
            )
        assert failure.value.code is Code.KEY_REUSED


async def test_retirement_preserves_repair_original_and_blocks_fresh_assignment(
    database: Database,
) -> None:
    access, request, _ = await seed_stranded_repair_target(database, "application-account")
    responsibility = request.responsibility
    assert isinstance(responsibility, ActionGrantorRepairResponsibilityDTO)
    target = responsibility.target
    assert isinstance(target, ApplicationAccountGrantTargetDTO)
    project_id = target.project_id.value
    principal_id = target.application_principal_id.value
    async with database.session() as session:
        original = await stranded_repair_service(session).repair(access=access, command=request)

    fingerprints = ApplicationAccountDeletionFingerprintService(
        RequestFingerprintService(RequestFingerprintKey(b"r" * 32))
    )
    async with open_application_account_deletion(database, fingerprints) as retirement:
        retired = await retirement.delete(
            access=access,
            command=DeleteApplicationAccountCommand(
                target.project_id, target.application_principal_id, original.access_revision
            ),
            context=IdempotencyContextDTO(
                HttpMethod.DELETE,
                f"/v1/projects/{project_id}/application-accounts/{principal_id}",
                IdempotencyKey("retire-repaired-application"),
            ),
        )
    assert retired.original.access_revision == original.access_revision + 1

    refreshed = replace(
        request, identity_proof=HumanAccessTokenCredential("fresh-same-human-proof")
    )
    async with database.session() as session:
        replay = await stranded_repair_service(session).repair(access=access, command=refreshed)
    assert replay == original

    fresh = replace(
        refreshed,
        operation_id=OperationId("repair-after-retirement"),
        expected_access_revision=retired.original.access_revision,
    )
    async with database.session() as session:
        with pytest.raises(StrandedAuthorityMaintenanceError) as failure:
            await stranded_repair_service(session).repair(access=access, command=fresh)
        assert failure.value.code is Code.NOT_STRANDED

    async with database.session() as session, session.begin():
        account = await session.get(ApplicationAccountRow, principal_id)
        assert account is not None and account.project_id == project_id
        principal = await session.get(PrincipalRow, principal_id)
        assert principal is not None and principal.status is PrincipalStatus.RETIRED
        project = await session.get(ProjectRow, project_id)
        assert project is not None and project.access_revision == retired.original.access_revision
        assert await session.get(ProjectMembershipRow, (project_id, principal_id)) is None
        assert (
            await session.scalar(
                select(ApplicationActionGrantRow.application_principal_id).where(
                    ApplicationActionGrantRow.project_id == project_id,
                    ApplicationActionGrantRow.application_principal_id == principal_id,
                )
            )
            is None
        )
        reader = PostgresStrandedAuthorityRepairFactsReader(session)
        retained = await reader.receipt(
            installation_id=request.expected_installation_id, operation_id=request.operation_id
        )
        assert retained is not None and retained.result == original
        assert (
            await reader.receipt(
                installation_id=fresh.expected_installation_id, operation_id=fresh.operation_id
            )
            is None
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AccessAuditEventRow)
                .where(
                    AccessAuditEventRow.project_id == project_id,
                    AccessAuditEventRow.target_id == principal_id,
                    AccessAuditEventRow.event_type == "stranded_authority_repaired",
                )
            )
            == 1
        )


async def test_current_group_manager_prevents_document_action_repair_without_explicit_grant(
    database: Database,
) -> None:
    access, request, _ = await seed_stranded_repair_target(database, "group-action")
    async with database.session() as session:
        with pytest.raises(StrandedAuthorityMaintenanceError) as failure:
            await stranded_repair_service(session).repair(access=access, command=request)
        assert failure.value.code is Code.NOT_STRANDED
    async with database.session() as session:
        assert (
            await session.scalar(select(func.count()).select_from(HostMaintenanceReceiptRow)) == 0
        )


async def test_audit_failure_rolls_back_all_broader_repair_effects(database: Database) -> None:
    class FailingAudit(PostgresStrandedAuthorityAuditWriter):
        @override
        async def repaired(self, event: StrandedAuthorityRepairedAuditEventDTO) -> None:
            await super().repaired(event)
            raise RuntimeError("Controlled repair audit failure")

    access, request, _ = await seed_stranded_repair_target(database, "group-manager")
    async with database.session() as session:
        with pytest.raises(RuntimeError, match="Controlled repair audit failure"):
            await stranded_repair_service(
                session, FailingAudit(session, PostgresProjectMetadataAuditWriter(session))
            ).repair(access=access, command=request)
    responsibility = request.responsibility
    assert isinstance(responsibility, GroupManagerRepairResponsibilityDTO)
    async with database.session() as session:
        assert (
            await session.scalar(
                select(ProjectRow.access_revision).where(
                    ProjectRow.id == responsibility.project_id.value
                )
            )
            == request.expected_access_revision
        )
        assert (
            await session.scalar(select(func.count()).select_from(HostMaintenanceReceiptRow)) == 0
        )
        assert (
            await session.scalar(
                select(func.count()).select_from(StrandedAuthorityRepairReceiptRow)
            )
            == 0
        )
        assert await session.scalar(select(func.count()).select_from(GroupManagerRow)) == 0
        assert await session.scalar(select(func.count()).select_from(GroupMembershipRow)) == 0
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AccessAuditEventRow)
                .where(AccessAuditEventRow.event_type == "stranded_authority_repaired")
            )
            == 0
        )


async def test_lost_application_ack_after_real_commit_recovers_one_original(
    database: Database,
) -> None:
    """Lose application acknowledgment after COMMIT, without claiming a physical wire fault."""
    access, request, _ = await seed_stranded_repair_target(database, "group-manager")
    async with database.session() as session:

        def lose_ack(_session: Session) -> None:
            raise RuntimeError("Controlled lost COMMIT acknowledgment")

        event.listen(session.sync_session, "after_commit", lose_ack)
        try:
            with pytest.raises(RuntimeError, match="lost COMMIT acknowledgment"):
                await stranded_repair_service(session).repair(access=access, command=request)
        finally:
            event.remove(session.sync_session, "after_commit", lose_ack)
    async with database.session() as session:
        recovered = await stranded_repair_service(session).repair(access=access, command=request)
    assert recovered.access_revision == request.expected_access_revision + 1
    async with database.session() as session:
        assert (
            await session.scalar(select(func.count()).select_from(HostMaintenanceReceiptRow)) == 1
        )
        assert (
            await session.scalar(
                select(func.count()).select_from(StrandedAuthorityRepairReceiptRow)
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AccessAuditEventRow)
                .where(AccessAuditEventRow.event_type == "stranded_authority_repaired")
            )
            == 1
        )


@pytest.mark.parametrize("loss", ["credential", "suspension", "membership"])
async def test_current_eligibility_precedes_completed_broader_original(
    database: Database, loss: str
) -> None:
    access, request, _ = await seed_stranded_repair_target(database, "group-manager")
    async with database.session() as session:
        original = await stranded_repair_service(session).repair(access=access, command=request)
    responsibility = request.responsibility
    assert isinstance(responsibility, GroupManagerRepairResponsibilityDTO)
    async with database.session() as session, session.begin():
        if loss == "credential":
            await session.execute(
                update(HumanCredentialVersionRow).values(
                    version=HumanCredentialVersionRow.version + 1
                )
            )
        elif loss == "suspension":
            await session.execute(
                update(PrincipalRow)
                .where(PrincipalRow.id == access.actor_principal_id.value)
                .values(status=PrincipalStatus.SUSPENDED)
            )
        else:
            await session.execute(
                delete(GroupManagerRow).where(
                    GroupManagerRow.principal_id == access.actor_principal_id.value
                )
            )
            await session.execute(
                delete(GroupMembershipRow).where(
                    GroupMembershipRow.principal_id == access.actor_principal_id.value
                )
            )
            await session.execute(
                delete(ProjectActionGrantRow).where(
                    ProjectActionGrantRow.recipient_principal_id == access.actor_principal_id.value
                )
            )
            await session.execute(
                delete(ProjectMembershipRow).where(
                    ProjectMembershipRow.principal_id == access.actor_principal_id.value
                )
            )
    async with database.session() as session:
        with pytest.raises(StrandedAuthorityMaintenanceError) as failure:
            await stranded_repair_service(session).repair(access=access, command=request)
        assert failure.value.code is (
            Code.INVALID_IDENTITY_PROOF if loss == "credential" else Code.IDENTITY_INELIGIBLE
        )
    async with database.session() as session:
        child = await session.get(
            StrandedAuthorityRepairReceiptRow,
            (request.expected_installation_id.value, request.operation_id.value),
        )
        assert child is not None and child.after_revision == original.access_revision


async def test_broader_reader_preserves_bootstrap_mode_namespace(database: Database) -> None:
    scenario = await bootstrap_scenario(database)
    async with database.session() as session:
        await bootstrap_service(session, scenario.binding).bootstrap(scenario.command)
    async with database.session() as session, session.begin():
        with pytest.raises(StrandedAuthorityMaintenanceError) as failure:
            await PostgresStrandedAuthorityRepairFactsReader(session).receipt(
                installation_id=scenario.binding.installation_id,
                operation_id=scenario.command.operation_id,
            )
        assert failure.value.code is Code.KEY_REUSED


@pytest.mark.parametrize("corruption", ["missing", "competing"])
async def test_original_decoder_rejects_missing_or_competing_payloads(
    database: Database, corruption: str
) -> None:
    access, request, _ = await seed_stranded_repair_target(database, "group-manager")
    async with database.session() as session:
        await stranded_repair_service(session).repair(access=access, command=request)
    async with database.session() as session, session.begin():
        child = await session.get(
            StrandedAuthorityRepairReceiptRow,
            (request.expected_installation_id.value, request.operation_id.value),
        )
        assert child is not None and child.project_id is not None
        if corruption == "missing":
            await session.delete(child)
        else:
            session.add(
                ProjectMetadataRepairReceiptRow(
                    installation_id=child.installation_id,
                    operator_request_id=child.operator_request_id,
                    organization_id=child.organization_id,
                    project_id=child.project_id,
                    recipient_id=child.recipient_id,
                    expected_identity_id=child.expected_identity_id,
                    request_fingerprint=child.request_fingerprint,
                    before_revision=child.before_revision,
                    after_revision=child.after_revision,
                )
            )
    async with database.session() as session, session.begin():
        with pytest.raises(RuntimeError, match="single valid typed result"):
            await PostgresStrandedAuthorityRepairFactsReader(session).receipt(
                installation_id=request.expected_installation_id, operation_id=request.operation_id
            )


async def test_group_deletion_retains_historical_repair_without_restoring_target(
    database: Database,
) -> None:
    access, request, _ = await seed_stranded_repair_target(database, "group-manager")
    async with database.session() as session:
        original = await stranded_repair_service(session).repair(access=access, command=request)
    responsibility = request.responsibility
    assert isinstance(responsibility, GroupManagerRepairResponsibilityDTO)
    async with open_access_group_deletion(
        database, group_fingerprints(), DeletionStatusRetentionProfile(30)
    ) as service:
        await service.delete(
            access=access,
            command=DeleteAccessGroupCommand(
                responsibility.project_id, responsibility.access_group_id, original.access_revision
            ),
            context=IdempotencyContextDTO(
                HttpMethod.DELETE,
                f"/v1/projects/{responsibility.project_id.value}/access-groups/{responsibility.access_group_id.value}",
                IdempotencyKey("delete-repaired-group"),
            ),
            request_id=RequestId(uuid4()),
        )
    async with database.session() as session, session.begin():
        retained = await PostgresStrandedAuthorityRepairFactsReader(session).receipt(
            installation_id=request.expected_installation_id, operation_id=request.operation_id
        )
        assert retained is not None and retained.result == original
        assert await session.get(AccessGroupRow, responsibility.access_group_id.value) is None
    async with database.session() as session:
        with pytest.raises(StrandedAuthorityMaintenanceError) as failure:
            await stranded_repair_service(session).repair(access=access, command=request)
        assert failure.value.code is Code.IDENTITY_INELIGIBLE


async def test_new_metadata_repair_preserves_legacy_row_audit_and_original_recovery(
    database: Database,
) -> None:
    access, request, _ = await seed_stranded_repair_target(database, "project")
    responsibility = request.responsibility
    assert isinstance(responsibility, ActionGrantorRepairResponsibilityDTO) and isinstance(
        responsibility.target, ProjectGrantTargetDTO
    )
    request = replace(
        request,
        responsibility=ActionGrantorRepairResponsibilityDTO(
            responsibility.target, ActionId("edit-project-metadata")
        ),
    )
    async with database.session() as session:
        original = await stranded_repair_service(session).repair(access=access, command=request)
    async with database.session() as session:
        legacy = await stranded_repair_service(session).repair(access=access, command=request)
    assert legacy.access_revision == original.access_revision
    async with database.session() as session:
        assert (
            await session.get(
                ProjectMetadataRepairReceiptRow,
                (request.expected_installation_id.value, request.operation_id.value),
            )
            is not None
        )
        assert (
            await session.scalar(
                select(func.count()).select_from(StrandedAuthorityRepairReceiptRow)
            )
            == 0
        )
        audits = (
            await session.scalars(
                select(AccessAuditEventRow).where(
                    AccessAuditEventRow.event_type == "project_metadata_authority_repaired"
                )
            )
        ).all()
        assert len(audits) == 1
        assert audits[0].after_values == {
            "access_revision": original.access_revision,
            "can_grant": True,
        }


@pytest.mark.parametrize("same_original", [False, True], ids=["distinct-requests", "same-original"])
async def test_competing_host_repairs_hold_real_turns_and_commit_one_assignment(
    database: Database, same_original: bool
) -> None:
    access, request, _ = await seed_stranded_repair_target(database, "group-manager")

    async def repair(key: str) -> StrandedAuthorityRepairResultDTO:
        async with database.session() as session:
            return await stranded_repair_service(session).repair(
                access=access, command=replace(request, operation_id=OperationId(key))
            )

    async with database.session() as holder:
        await holder.begin()
        await holder.scalar(select(OrganizationRow.id).with_for_update())
        tasks = [
            asyncio.create_task(repair("race-one")),
            asyncio.create_task(repair("race-one" if same_original else "race-two")),
        ]
        consumed: list[BaseException] = []
        work_error: BaseException | None = None
        try:
            await wait_for_database_lock(database, tasks[0], minimum=2)
            await holder.commit()
            async with asyncio.timeout(3):
                results = await asyncio.shield(asyncio.gather(*tasks, return_exceptions=True))
            successes = [r for r in results if isinstance(r, StrandedAuthorityRepairResultDTO)]
            failures = [r for r in results if isinstance(r, StrandedAuthorityMaintenanceError)]
            if same_original:
                assert len(successes) == 2 and successes[0] == successes[1]
            else:
                assert len(successes) == 1 and len(failures) == 1
                assert failures[0].code in {Code.STALE_REVISION, Code.NOT_STRANDED}
            consumed.extend(failures)
        except BaseException as error:
            work_error = error
            raise
        finally:
            rollback = asyncio.create_task(holder.rollback())
            owned = [*tasks, rollback]
            cleanup_errors: list[BaseException] = []
            try:
                async with asyncio.timeout(3):
                    for task in tasks:
                        if not task.done():
                            task.cancel()
                    pending_results: list[Awaitable[StrandedAuthorityRepairResultDTO | None]] = [
                        *tasks,
                        rollback,
                    ]
                    await asyncio.shield(asyncio.gather(*pending_results, return_exceptions=True))
            except BaseException as error:
                cleanup_errors.append(error)
            finally:
                for pending in owned:
                    if not pending.done():
                        pending.cancel()
                        continue
                    try:
                        pending.result()
                    except BaseException as error:
                        if (
                            not (
                                isinstance(error, asyncio.CancelledError)
                                and pending is not rollback
                            )
                            and error is not work_error
                            and not any(error is observed for observed in consumed)
                            and not any(error is observed for observed in cleanup_errors)
                        ):
                            cleanup_errors.append(error)
            if cleanup_errors:
                raise BaseExceptionGroup(
                    "Host-repair work and task cleanup failed",
                    ([work_error] if work_error is not None else []) + cleanup_errors,
                ) from None
    async with database.session() as session:
        assert (
            await session.scalar(select(func.count()).select_from(HostMaintenanceReceiptRow)) == 1
        )
        assert (
            await session.scalar(
                select(func.count()).select_from(StrandedAuthorityRepairReceiptRow)
            )
            == 1
        )
        assert await session.scalar(select(func.count()).select_from(GroupManagerRow)) == 1


async def test_current_version_and_utc_are_observed_after_identity_turn_wait(
    database: Database,
) -> None:
    access, request, _ = await seed_stranded_repair_target(database, "group-manager")
    binding = access.authentication_evidence
    assert isinstance(binding, HumanOAuthCredentialBindingDTO)

    async def observe() -> StrandedAuthorityRepairFactsDTO | None:
        async with database.session() as session, session.begin():
            return await PostgresStrandedAuthorityRepairFactsReader(session).read(
                access=access, command=request
            )

    async with database.session() as holder:
        await holder.begin()
        await PostgresIdentityCoordinator(holder).acquire(
            installation_id=binding.installation_id, identity=binding.identity
        )
        task = asyncio.create_task(observe())
        work_error: BaseException | None = None
        try:
            await wait_for_database_lock(database, task)
            await holder.execute(
                update(HumanCredentialVersionRow)
                .where(
                    HumanCredentialVersionRow.installation_id == binding.installation_id.value,
                    HumanCredentialVersionRow.authority == binding.identity.authority.value,
                    HumanCredentialVersionRow.subject == binding.identity.subject.value,
                )
                .values(version=binding.version.value + 1)
            )
            changed_at = await holder.scalar(
                select(func.clock_timestamp(type_=ProjectRow.created_at.type))
            )
            assert isinstance(changed_at, datetime)
            await holder.commit()
            async with asyncio.timeout(3):
                facts = await asyncio.shield(task)
            assert facts is not None and facts.oauth_credential_facts.current_version is not None
            assert facts.oauth_credential_facts.current_version.value == binding.version.value + 1
            assert facts.observed_at >= changed_at and facts.observed_at.tzinfo is not None
        except BaseException as error:
            work_error = error
            raise
        finally:
            rollback = asyncio.create_task(holder.rollback())
            owned = [task, rollback]
            cleanup_errors: list[BaseException] = []
            try:
                async with asyncio.timeout(3):
                    if not task.done():
                        task.cancel()
                    await asyncio.shield(asyncio.gather(*owned, return_exceptions=True))
            except BaseException as error:
                cleanup_errors.append(error)
            finally:
                for pending in owned:
                    if not pending.done():
                        pending.cancel()
                        continue
                    try:
                        pending.result()
                    except BaseException as error:
                        if (
                            not (
                                isinstance(error, asyncio.CancelledError)
                                and pending is not rollback
                            )
                            and error is not work_error
                            and not any(error is observed for observed in cleanup_errors)
                        ):
                            cleanup_errors.append(error)
            if cleanup_errors:
                raise BaseExceptionGroup(
                    "Observation and task cleanup failed",
                    ([work_error] if work_error is not None else []) + cleanup_errors,
                ) from None
    async with database.session() as session:
        with pytest.raises(StrandedAuthorityMaintenanceError) as failure:
            await stranded_repair_service(session).repair(access=access, command=request)
        assert failure.value.code is Code.INVALID_IDENTITY_PROOF


@pytest.mark.parametrize("isolation", ["REPEATABLE READ", "SERIALIZABLE"])
async def test_repair_refuses_noncurrent_transaction_isolation(
    database: Database, isolation: str
) -> None:
    access, request, _ = await seed_stranded_repair_target(database, "project")
    async with database.session() as session:
        await session.connection(execution_options={"isolation_level": isolation})
        with pytest.raises(RuntimeError, match="READ COMMITTED"):
            await PostgresStrandedAuthorityRepairFactsReader(session).read(
                access=access, command=request
            )
        await session.rollback()


async def test_repair_reader_requires_caller_transaction(database: Database) -> None:
    access, request, _ = await seed_stranded_repair_target(database, "project")
    async with database.session() as session:
        with pytest.raises(RuntimeError, match="transaction"):
            await PostgresStrandedAuthorityRepairFactsReader(session).read(
                access=access, command=request
            )
