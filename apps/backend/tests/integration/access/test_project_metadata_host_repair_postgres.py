"""Verify restricted repair against real persistence after simulated completed authentication.

Native Ory proof is qualified separately. These tests exercise the post-verification boundary.
"""

import asyncio
import os
from dataclasses import replace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, func, select, update
from tests.support.project_metadata_scenarios import (
    seed_metadata_repair_recipient,
    stranded_repair_service,
)

from inframeld_backend.access.application.commands.repair_stranded_authority_command import (
    RepairStrandedAuthorityCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.action_grantor_repair_responsibility_dto import (
    ActionGrantorRepairResponsibilityDTO,
)
from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
    HumanOAuthCredentialBindingDTO,
)
from inframeld_backend.access.application.dtos.project_grant_target_dto import ProjectGrantTargetDTO
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.enums.stranded_authority_maintenance_error_code import (
    StrandedAuthorityMaintenanceErrorCode as Code,
)
from inframeld_backend.access.application.errors.stranded_authority_maintenance_error import (
    StrandedAuthorityMaintenanceError,
)
from inframeld_backend.access.application.value_objects.human_access_token_credential import (
    HumanAccessTokenCredential,
)
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.access.infrastructure.rows.host_maintenance_receipt_row import (
    HostMaintenanceReceiptRow,
)
from inframeld_backend.access.infrastructure.rows.human_credential_version_row import (
    HumanCredentialVersionRow,
)
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.project_metadata_repair_receipt_row import (
    ProjectMetadataRepairReceiptRow,
)
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.access.infrastructure.writers.postgres_stranded_authority_audit_writer import (
    PostgresStrandedAuthorityAuditWriter,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.infrastructure.resources.database import Database

pytestmark = pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
    reason="Requires PostgreSQL integration services",
)


def command(
    binding: HumanOAuthCredentialBindingDTO,
    project_id: ProjectId,
    operation: str = "operator-original",
) -> RepairStrandedAuthorityCommand:
    return RepairStrandedAuthorityCommand(
        expected_installation_id=binding.installation_id,
        operation_id=OperationId(operation),
        responsibility=ActionGrantorRepairResponsibilityDTO(
            ProjectGrantTargetDTO(project_id), ActionId("edit-project-metadata")
        ),
        expected_access_revision=0,
        expected_identity_id=UUID(binding.identity.subject.value),
        operator_label="Host operator",
        reason="Repair exact metadata responsibility",
        identity_proof=HumanAccessTokenCredential("opaque-unit-boundary-proof"),
    )


def identity() -> VerifiedHumanIdentityDTO:
    return VerifiedHumanIdentityDTO(IdentityAuthority("kratos:test"), IdentitySubject(str(uuid4())))


@pytest.mark.asyncio
async def test_first_grant_receipt_and_operator_audit_commit_without_unrelated_authority(
    database: Database,
) -> None:
    seed, binding = await seed_metadata_repair_recipient(database, identity())
    request = command(binding, seed.project_id)
    async with database.session() as session:
        result = await stranded_repair_service(session).repair(
            access=AccessContextDTO(seed.principal_id, binding), command=request
        )
    assert result.access_revision == 1 and result.recipient_id == seed.principal_id
    async with database.session() as session:
        grants = (
            await session.scalars(
                select(ProjectActionGrantRow).where(
                    ProjectActionGrantRow.project_id == seed.project_id.value
                )
            )
        ).all()
        assert (
            len(grants) == 1 and grants[0].action == "edit-project-metadata" and grants[0].can_grant
        )
        assert grants[0].assigned_by_principal_id is None
        row = await session.get(ProjectRow, seed.project_id.value)
        assert row is not None and (
            row.access_revision,
            row.metadata_revision,
            row.resource_name,
        ) == (1, 0, None)
        parent = await session.get(
            HostMaintenanceReceiptRow, (binding.installation_id.value, request.operation_id.value)
        )
        child = await session.get(
            ProjectMetadataRepairReceiptRow,
            (binding.installation_id.value, request.operation_id.value),
        )
        assert parent is not None and child is not None
        assert (
            parent.recovery_operation_id
            is parent.released
            is parent.run_id
            is parent.deadline
            is None
        )
        audit = (
            await session.scalars(
                select(AccessAuditEventRow).where(
                    AccessAuditEventRow.event_type == "project_metadata_authority_repaired"
                )
            )
        ).one()
        assert audit.actor_kind == "operator" and audit.actor_principal_id is None
        assert (
            audit.actor_reference == "Host operator"
            and audit.affected_principal_id == seed.principal_id.value
        )


@pytest.mark.asyncio
async def test_refreshed_proof_replays_original_receipt_after_grant_removal_without_regrant(
    database: Database,
) -> None:
    seed, binding = await seed_metadata_repair_recipient(database, identity())
    request = command(binding, seed.project_id)
    access = AccessContextDTO(seed.principal_id, binding)
    async with database.session() as session:
        first = await stranded_repair_service(session).repair(access=access, command=request)
    async with database.session() as session, session.begin():
        await session.execute(
            delete(ProjectActionGrantRow).where(
                ProjectActionGrantRow.project_id == seed.project_id.value
            )
        )
        await session.execute(
            update(ProjectRow)
            .where(ProjectRow.id == seed.project_id.value)
            .values(access_revision=ProjectRow.access_revision + 1)
        )
    async with database.session() as session:
        replay = await stranded_repair_service(session).repair(
            access=access,
            command=replace(
                request, identity_proof=HumanAccessTokenCredential("replaced-transient-proof")
            ),
        )
    assert replay == first
    async with database.session() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ProjectActionGrantRow)
                .where(ProjectActionGrantRow.project_id == seed.project_id.value)
            )
            == 0
        )
        assert (
            await session.scalar(select(func.count()).select_from(HostMaintenanceReceiptRow)) == 1
        )
    async with database.session() as session:
        with pytest.raises(StrandedAuthorityMaintenanceError) as failure:
            await stranded_repair_service(session).repair(
                access=access, command=replace(request, reason="Changed reviewed meaning")
            )
        assert failure.value.code is Code.KEY_REUSED


@pytest.mark.asyncio
async def test_concurrent_repairs_assign_once_and_do_not_create_a_second_receipt(
    database: Database,
) -> None:
    seed, binding = await seed_metadata_repair_recipient(database, identity())

    async def repair(key: str):
        async with database.session() as session:
            return await stranded_repair_service(session).repair(
                access=AccessContextDTO(seed.principal_id, binding),
                command=command(binding, seed.project_id, key),
            )

    results = await asyncio.gather(repair("first"), repair("second"), return_exceptions=True)
    assert sum(not isinstance(result, BaseException) for result in results) == 1
    conflicts = [
        result for result in results if isinstance(result, StrandedAuthorityMaintenanceError)
    ]
    assert len(conflicts) == 1 and conflicts[0].code in {Code.STALE_REVISION, Code.NOT_STRANDED}
    async with database.session() as session:
        assert (
            await session.scalar(select(func.count()).select_from(HostMaintenanceReceiptRow)) == 1
        )
        assert await session.scalar(select(func.count()).select_from(ProjectActionGrantRow)) == 1


@pytest.mark.asyncio
async def test_locally_stale_generation_is_rejected_before_new_or_replayed_authority(
    database: Database,
) -> None:
    seed, binding = await seed_metadata_repair_recipient(database, identity())
    async with database.session() as session, session.begin():
        await session.execute(
            update(HumanCredentialVersionRow)
            .where(
                HumanCredentialVersionRow.installation_id == binding.installation_id.value,
                HumanCredentialVersionRow.authority == binding.identity.authority.value,
                HumanCredentialVersionRow.subject == binding.identity.subject.value,
            )
            .values(version=binding.version.value + 1)
        )
    async with database.session() as session:
        with pytest.raises(StrandedAuthorityMaintenanceError) as failure:
            await stranded_repair_service(session).repair(
                access=AccessContextDTO(seed.principal_id, binding),
                command=command(binding, seed.project_id),
            )
        assert failure.value.code is Code.INVALID_IDENTITY_PROOF
    async with database.session() as session:
        assert (
            await session.scalar(select(func.count()).select_from(HostMaintenanceReceiptRow)) == 0
        )


@pytest.mark.asyncio
async def test_audit_failure_rolls_back_repair_grant_revision_and_both_receipts(
    database: Database,
) -> None:
    from typing import override

    from inframeld_backend.access.application.dtos.project_metadata_authority_repaired_audit_event_dto import (
        ProjectMetadataAuthorityRepairedAuditEventDTO,
    )
    from inframeld_backend.access.infrastructure.writers.postgres_project_metadata_audit_writer import (
        PostgresProjectMetadataAuditWriter,
    )

    class MockFailingAudit(PostgresProjectMetadataAuditWriter):
        @override
        async def repaired(self, event: ProjectMetadataAuthorityRepairedAuditEventDTO) -> None:
            await super().repaired(event)
            raise RuntimeError("Audit storage failed before commit.")

    seed, binding = await seed_metadata_repair_recipient(database, identity())
    async with database.session() as session:
        with pytest.raises(RuntimeError, match="Audit storage failed"):
            await stranded_repair_service(
                session, PostgresStrandedAuthorityAuditWriter(session, MockFailingAudit(session))
            ).repair(
                access=AccessContextDTO(seed.principal_id, binding),
                command=command(binding, seed.project_id),
            )
    async with database.session() as session:
        project = await session.get(ProjectRow, seed.project_id.value)
        assert project is not None and project.access_revision == 0
        for table in (
            ProjectActionGrantRow,
            HostMaintenanceReceiptRow,
            ProjectMetadataRepairReceiptRow,
            AccessAuditEventRow,
        ):
            assert await session.scalar(select(func.count()).select_from(table)) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("linked", [True, False])
async def test_existing_grantor_or_unknown_identity_cannot_prove_exact_responsibility_stranded(
    database: Database,
    linked: bool,
) -> None:
    from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
    from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
    from inframeld_backend.access.infrastructure.rows.human_identity_link_row import (
        HumanIdentityLinkRow,
    )
    from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
    from inframeld_backend.access.infrastructure.rows.project_membership_row import (
        ProjectMembershipRow,
    )

    seed, binding = await seed_metadata_repair_recipient(database, identity())
    grantor_id, grantor_identity = uuid4(), identity()
    async with database.session() as session, session.begin():
        session.add(
            PrincipalRow(
                id=grantor_id,
                organization_id=seed.organization_id.value,
                kind=PrincipalKind.HUMAN,
                status=PrincipalStatus.ACTIVE,
                display_name="Peer grantor",
            )
        )
        await session.flush()
        if linked:
            session.add(
                HumanIdentityLinkRow(
                    authority=grantor_identity.authority.value,
                    subject=grantor_identity.subject.value,
                    organization_id=seed.organization_id.value,
                    principal_id=grantor_id,
                    principal_kind=PrincipalKind.HUMAN,
                )
            )
        session.add(
            ProjectMembershipRow(
                project_id=seed.project_id.value,
                principal_id=grantor_id,
                organization_id=seed.organization_id.value,
                principal_kind=PrincipalKind.HUMAN,
            )
        )
        await session.flush()
        session.add(
            ProjectActionGrantRow(
                project_id=seed.project_id.value,
                recipient_principal_id=grantor_id,
                recipient_kind=PrincipalKind.HUMAN,
                action="edit-project-metadata",
                can_grant=True,
            )
        )
    async with database.session() as session:
        with pytest.raises(StrandedAuthorityMaintenanceError) as failure:
            await stranded_repair_service(session).repair(
                access=AccessContextDTO(seed.principal_id, binding),
                command=command(binding, seed.project_id),
            )
        assert failure.value.code is (Code.NOT_STRANDED if linked else Code.DEPENDENCY_UNAVAILABLE)
    async with database.session() as session:
        assert (
            await session.scalar(select(func.count()).select_from(HostMaintenanceReceiptRow)) == 0
        )
        assert await session.scalar(select(func.count()).select_from(ProjectActionGrantRow)) == 1


@pytest.mark.asyncio
async def test_recovery_reader_rejects_actual_repair_receipt_before_recovery_decoding(
    database: Database,
) -> None:
    from inframeld_backend.access.application.enums.recovery_maintenance_error_code import (
        RecoveryMaintenanceErrorCode,
    )
    from inframeld_backend.access.application.errors.recovery_maintenance_error import (
        RecoveryMaintenanceError,
    )
    from inframeld_backend.access.infrastructure.readers.postgres_identity_recovery_cleanup_resume_facts_reader import (
        PostgresIdentityRecoveryCleanupResumeFactsReader,
    )

    seed, binding = await seed_metadata_repair_recipient(database, identity())
    request = command(binding, seed.project_id)
    async with database.session() as session:
        await stranded_repair_service(session).repair(
            access=AccessContextDTO(seed.principal_id, binding),
            command=request,
        )
    async with database.session() as session, session.begin():
        with pytest.raises(RecoveryMaintenanceError) as failure:
            await PostgresIdentityRecoveryCleanupResumeFactsReader(session).receipt(
                installation_id=binding.installation_id,
                operation_id=request.operation_id,
            )
        assert failure.value.code is RecoveryMaintenanceErrorCode.KEY_REUSED


@pytest.mark.asyncio
async def test_repair_waits_for_identity_turn_then_rejects_newly_stale_generation(
    database: Database,
) -> None:
    from sqlalchemy import Integer
    from sqlalchemy.dialects.postgresql import ARRAY

    from inframeld_backend.access.infrastructure.resources.postgres_identity_coordinator import (
        PostgresIdentityCoordinator,
    )

    seed, binding = await seed_metadata_repair_recipient(database, identity())
    pid_ready: asyncio.Future[int] = asyncio.get_running_loop().create_future()

    from typing import override

    from inframeld_backend.access.application.dtos.stranded_authority_repair_facts_dto import (
        StrandedAuthorityRepairFactsDTO,
    )
    from inframeld_backend.access.infrastructure.readers.postgres_stranded_authority_repair_facts_reader import (
        PostgresStrandedAuthorityRepairFactsReader,
    )

    class MockObservedFacts(PostgresStrandedAuthorityRepairFactsReader):
        @override
        async def read(
            self, *, access: AccessContextDTO, command: RepairStrandedAuthorityCommand
        ) -> StrandedAuthorityRepairFactsDTO | None:
            pid = await self._session.scalar(select(func.pg_backend_pid().cast(Integer)))
            assert pid is not None
            pid_ready.set_result(pid)
            return await super().read(access=access, command=command)

    async def repair() -> None:
        async with database.session() as session:
            with pytest.raises(StrandedAuthorityMaintenanceError) as failure:
                await stranded_repair_service(session, facts=MockObservedFacts(session)).repair(
                    access=AccessContextDTO(seed.principal_id, binding),
                    command=command(binding, seed.project_id),
                )
            assert failure.value.code is Code.INVALID_IDENTITY_PROOF

    async with asyncio.timeout(30), asyncio.TaskGroup() as tasks:
        async with database.session() as session, session.begin():
            await PostgresIdentityCoordinator(session).acquire(
                installation_id=binding.installation_id,
                identity=binding.identity,
            )
            task = tasks.create_task(repair())
            pid = await pid_ready
            async with asyncio.timeout(10):
                while True:
                    async with database.session() as observer:
                        blockers = await observer.scalar(
                            select(func.pg_blocking_pids(pid).cast(ARRAY(Integer)))
                        )
                    if blockers:
                        break
                    await asyncio.sleep(0.01)
            await session.execute(
                update(HumanCredentialVersionRow)
                .where(
                    HumanCredentialVersionRow.installation_id == binding.installation_id.value,
                    HumanCredentialVersionRow.authority == binding.identity.authority.value,
                    HumanCredentialVersionRow.subject == binding.identity.subject.value,
                )
                .values(version=binding.version.value + 1)
            )
        await task
    async with database.session() as session:
        assert (
            await session.scalar(select(func.count()).select_from(HostMaintenanceReceiptRow)) == 0
        )
