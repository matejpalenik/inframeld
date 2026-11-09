"""Qualify first admission and one-time claim effects in real PostgreSQL.

Provider verification is controlled here. The native companion owns actual Ory proof.
"""

import asyncio
import os
from dataclasses import replace
from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy import ARRAY, Integer, String, column, delete, event, func, select, table, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from tests.support.first_administrator_bootstrap_scenarios import (
    FirstAdministratorScenarioDTO,
    bootstrap_scenario,
    bootstrap_service,
)

from inframeld_backend.access.application.dtos.first_administrator_bootstrap_facts_dto import (
    FirstAdministratorBootstrapFactsDTO,
)
from inframeld_backend.access.application.dtos.first_administrator_bootstrap_receipt_dto import (
    FirstAdministratorBootstrapReceiptDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_event_dto import (
    IdentityRecoveryEventDTO,
)
from inframeld_backend.access.application.enums.first_administrator_bootstrap_error_code import (
    FirstAdministratorBootstrapErrorCode as Code,
)
from inframeld_backend.access.application.enums.identity_recovery_event_kind import (
    IdentityRecoveryEventKind,
)
from inframeld_backend.access.application.errors.first_administrator_bootstrap_error import (
    FirstAdministratorBootstrapError,
)
from inframeld_backend.access.application.errors.recovery_maintenance_error import (
    RecoveryMaintenanceError,
)
from inframeld_backend.access.application.errors.stranded_authority_maintenance_error import (
    StrandedAuthorityMaintenanceError,
)
from inframeld_backend.access.domain.enums.identity_recovery_cleanup_state import (
    IdentityRecoveryCleanupState,
)
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.access.domain.value_objects.identity_recovery_flow_id import (
    IdentityRecoveryFlowId,
)
from inframeld_backend.access.infrastructure.readers.postgres_human_credential_state_reader import (
    PostgresHumanCredentialStateReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_identity_recovery_cleanup_resume_facts_reader import (
    PostgresIdentityRecoveryCleanupResumeFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_stranded_authority_repair_facts_reader import (
    PostgresStrandedAuthorityRepairFactsReader,
)
from inframeld_backend.access.infrastructure.resources.postgres_identity_coordinator import (
    PostgresIdentityCoordinator,
)
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.access.infrastructure.rows.first_administrator_bootstrap_receipt_row import (
    FirstAdministratorBootstrapReceiptRow,
)
from inframeld_backend.access.infrastructure.rows.host_maintenance_receipt_row import (
    HostMaintenanceReceiptRow,
)
from inframeld_backend.access.infrastructure.rows.human_credential_version_row import (
    HumanCredentialVersionRow,
)
from inframeld_backend.access.infrastructure.rows.human_identity_link_row import (
    HumanIdentityLinkRow,
)
from inframeld_backend.access.infrastructure.rows.identity_recovery_admission_row import (
    IdentityRecoveryAdmissionRow,
)
from inframeld_backend.access.infrastructure.rows.organization_action_grant_row import (
    OrganizationActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.access.infrastructure.writers.postgres_first_administrator_bootstrap_writer import (
    PostgresFirstAdministratorBootstrapWriter,
)
from inframeld_backend.access.infrastructure.writers.postgres_human_credential_state_initializer import (
    PostgresHumanCredentialStateInitializer,
)
from inframeld_backend.access.infrastructure.writers.postgres_identity_recovery_admission_writer import (
    PostgresIdentityRecoveryAdmissionWriter,
)
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.rows.artifact_storage_capacity_row import (
    ArtifactStorageCapacityRow,
)

pytestmark = pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
    reason="Requires PostgreSQL integration services",
)


async def _wait_for_blocked[Result](database: Database, task: asyncio.Task[Result]) -> None:
    """Require a real database lock wait before changing the preceding transaction."""
    pid, name = column("pid", Integer), column("datname", String)
    activity = table("pg_stat_activity", pid, name)
    async with asyncio.timeout(10):
        while not task.done():
            async with database.session() as observer:
                blocked = await observer.scalar(
                    select(pid)
                    .select_from(activity)
                    .where(
                        name == func.current_database(type_=String()),
                        func.cardinality(
                            func.pg_blocking_pids(pid, type_=ARRAY(Integer)), type_=Integer
                        )
                        > 0,
                    )
                )
            if blocked is not None:
                return
            await asyncio.sleep(0.01)
    task.result()
    raise AssertionError("The competing operation bypassed database coordination.")


async def _recover(session: AsyncSession, scenario: FirstAdministratorScenarioDTO) -> None:
    binding = scenario.binding
    await PostgresIdentityRecoveryAdmissionWriter(
        session, installation_id=binding.installation_id, authority=binding.identity.authority
    ).reserve(
        IdentityRecoveryEventDTO(
            IdentityRecoveryFlowId(uuid4()), binding.identity, IdentityRecoveryEventKind.RECOVERY
        )
    )


@pytest.mark.asyncio
async def test_pristine_claim_commits_exact_identity_four_grants_and_operator_audit(
    database: Database,
) -> None:
    scenario = await bootstrap_scenario(database)
    async with database.session() as session:
        result = await bootstrap_service(session, scenario.binding).bootstrap(scenario.command)

    async with database.session() as session:
        organization = await session.get(OrganizationRow, result.organization_id.value)
        principal = await session.get(PrincipalRow, result.recipient_id.value)
        link = await session.get(
            HumanIdentityLinkRow,
            (scenario.binding.identity.authority.value, scenario.binding.identity.subject.value),
        )
        assert (
            organization is not None
            and organization.name == "Inframeld"
            and organization.access_revision == 1
        )
        assert principal is not None and principal.organization_id == result.organization_id.value
        assert link is not None and link.principal_id == result.recipient_id.value
        assert await session.scalar(select(func.count()).select_from(PrincipalRow)) == 1
        assert await session.scalar(select(func.count()).select_from(ProjectRow)) == 0
        grants = (
            (
                await session.execute(
                    select(OrganizationActionGrantRow.action, OrganizationActionGrantRow.can_grant)
                )
            )
            .tuples()
            .all()
        )
        assert set(grants) == {
            ("admit-users", True),
            ("suspend-users", True),
            ("restore-users", True),
            ("create-projects", True),
        }
        audit = await session.scalar(select(AccessAuditEventRow))
        assert audit is not None and audit.actor_kind == "operator"
        assert (
            audit.actor_principal_id is None
            and audit.actor_reference == scenario.command.operator_label
        )
        assert audit.affected_principal_id == result.recipient_id.value
        assert audit.correlation_id == scenario.command.operation_id.value
        receipt = await session.get(
            FirstAdministratorBootstrapReceiptRow, result.installation_id.value
        )
        assert receipt is not None and receipt.organization_name == "Inframeld"
        assert receipt.operator_request_id == scenario.command.operation_id.value
        version = await session.get(
            HumanCredentialVersionRow,
            (
                scenario.binding.installation_id.value,
                scenario.binding.identity.authority.value,
                scenario.binding.identity.subject.value,
            ),
        )
        assert version is not None and version.version == scenario.binding.version.value


@pytest.mark.asyncio
async def test_different_humans_compete_for_one_installation_without_duplicate_admission(
    database: Database,
) -> None:
    first = await bootstrap_scenario(database, operation="first-human")
    second = await bootstrap_scenario(database, operation="second-human")

    async def claim(which: int) -> object:
        scenario = (first, second)[which]
        async with database.session() as session:
            return await bootstrap_service(session, scenario.binding).bootstrap(scenario.command)

    results = await asyncio.gather(claim(0), claim(1), return_exceptions=True)
    failures = [value for value in results if isinstance(value, FirstAdministratorBootstrapError)]
    assert len(failures) == 1 and failures[0].code is Code.ALREADY_BOOTSTRAPPED
    assert sum(not isinstance(value, BaseException) for value in results) == 1
    async with database.session() as session:
        assert await session.scalar(select(func.count()).select_from(OrganizationRow)) == 1
        assert await session.scalar(select(func.count()).select_from(PrincipalRow)) == 1
        assert await session.scalar(select(func.count()).select_from(HumanIdentityLinkRow)) == 1
        assert (
            await session.scalar(select(func.count()).select_from(OrganizationActionGrantRow)) == 4
        )
        assert (
            await session.scalar(
                select(func.count()).select_from(FirstAdministratorBootstrapReceiptRow)
            )
            == 1
        )


@pytest.mark.asyncio
async def test_required_audit_failure_rolls_back_every_claim_record(database: Database) -> None:
    scenario = await bootstrap_scenario(database)

    def reject_audit(session: Session, _context: object, _instances: object) -> None:
        if any(isinstance(row, AccessAuditEventRow) for row in session.new):
            raise RuntimeError("Controlled required audit failure")

    async with database.session() as session:
        event.listen(session.sync_session, "before_flush", reject_audit)
        try:
            with pytest.raises(RuntimeError, match="Controlled required audit failure"):
                await bootstrap_service(session, scenario.binding).bootstrap(scenario.command)
        finally:
            event.remove(session.sync_session, "before_flush", reject_audit)
    async with database.session() as session:
        for row in (
            OrganizationRow,
            PrincipalRow,
            HumanIdentityLinkRow,
            OrganizationActionGrantRow,
            HostMaintenanceReceiptRow,
            FirstAdministratorBootstrapReceiptRow,
            AccessAuditEventRow,
        ):
            assert await session.scalar(select(func.count()).select_from(row)) == 0


@pytest.mark.asyncio
async def test_original_receipt_does_not_restore_removed_grants_or_organization_revision(
    database: Database,
) -> None:
    scenario = await bootstrap_scenario(database)
    async with database.session() as session:
        original = await bootstrap_service(session, scenario.binding).bootstrap(scenario.command)
    async with database.session() as session, session.begin():
        await session.execute(delete(OrganizationActionGrantRow))
        await session.execute(update(OrganizationRow).values(access_revision=9))
    async with database.session() as session:
        replay = await bootstrap_service(session, scenario.binding).bootstrap(
            replace(
                scenario.command,
                identity_proof=type(scenario.command.identity_proof)("fresh-proof"),
            )
        )
    assert replay == original
    async with database.session() as session:
        assert await session.scalar(select(OrganizationRow.access_revision)) == 9
        assert (
            await session.scalar(select(func.count()).select_from(OrganizationActionGrantRow)) == 0
        )
        assert await session.scalar(select(func.count()).select_from(AccessAuditEventRow)) == 1


@pytest.mark.asyncio
async def test_existing_unclaimed_organization_is_not_guessed_or_backfilled(
    database: Database,
) -> None:
    scenario = await bootstrap_scenario(database)
    async with database.session() as session, session.begin():
        session.add(OrganizationRow(id=uuid4(), name="Legacy organization"))
    async with database.session() as session:
        with pytest.raises(FirstAdministratorBootstrapError) as error:
            await bootstrap_service(session, scenario.binding).bootstrap(scenario.command)
        assert error.value.code is Code.DEPENDENCY_UNAVAILABLE
    async with database.session() as session:
        assert await session.scalar(select(OrganizationRow.name)) == "Legacy organization"
        assert await session.scalar(select(func.count()).select_from(PrincipalRow)) == 0
        assert (
            await session.scalar(select(func.count()).select_from(HostMaintenanceReceiptRow)) == 0
        )


@pytest.mark.asyncio
async def test_retained_business_root_without_organization_is_not_a_fresh_installation(
    database: Database,
) -> None:
    scenario = await bootstrap_scenario(database)
    async with database.session() as session, session.begin():
        session.add(
            ArtifactStorageCapacityRow(installation_id=scenario.binding.installation_id.value)
        )
    async with database.session() as session:
        with pytest.raises(FirstAdministratorBootstrapError) as error:
            await bootstrap_service(session, scenario.binding).bootstrap(scenario.command)
        assert error.value.code is Code.DEPENDENCY_UNAVAILABLE
    async with database.session() as session:
        assert await session.scalar(select(func.count()).select_from(OrganizationRow)) == 0
        assert (
            await session.scalar(select(func.count()).select_from(HostMaintenanceReceiptRow)) == 0
        )


@pytest.mark.asyncio
async def test_simultaneous_same_identity_and_request_returns_one_original_result(
    database: Database,
) -> None:
    scenario = await bootstrap_scenario(database)

    async def claim() -> object:
        async with database.session() as session:
            return await bootstrap_service(session, scenario.binding).bootstrap(scenario.command)

    first, replay = await asyncio.gather(claim(), claim())
    assert first == replay
    async with database.session() as session:
        assert await session.scalar(select(func.count()).select_from(AccessAuditEventRow)) == 1
        assert (
            await session.scalar(select(func.count()).select_from(OrganizationActionGrantRow)) == 4
        )


@pytest.mark.asyncio
async def test_recovery_committing_first_is_reread_without_reinitializing_generation(
    database: Database,
) -> None:
    scenario = await bootstrap_scenario(database)

    async def claim() -> None:
        async with database.session() as session:
            await bootstrap_service(session, scenario.binding).bootstrap(scenario.command)

    async with asyncio.timeout(30), database.session() as holder:
        task = None
        try:
            async with holder.begin():
                await _recover(holder, scenario)
                task = asyncio.create_task(claim())
                await _wait_for_blocked(database, task)
            with pytest.raises(FirstAdministratorBootstrapError) as error:
                await task
            assert error.value.code is Code.INVALID_IDENTITY_PROOF
        finally:
            if task is not None:
                if not task.done():
                    task.cancel()
                await asyncio.gather(task, return_exceptions=True)
    state = await PostgresHumanCredentialStateReader(database).read(scenario.binding.identity)
    assert state.version is not None and state.version.value == 2 and state.has_pending_recovery
    async with database.session() as session:
        assert await session.scalar(select(func.count()).select_from(OrganizationRow)) == 0
        assert (
            await session.scalar(
                select(func.count()).select_from(FirstAdministratorBootstrapReceiptRow)
            )
            == 0
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("participant", ["recovery", "initializer"])
async def test_claim_holds_identity_until_commit_before_other_participants(
    database: Database, participant: str
) -> None:
    scenario = await bootstrap_scenario(database)
    entered, release = asyncio.Event(), asyncio.Event()
    write = PostgresFirstAdministratorBootstrapWriter.bootstrap

    async def hold_claim(
        writer: PostgresFirstAdministratorBootstrapWriter,
        *,
        facts: FirstAdministratorBootstrapFactsDTO,
        receipt: FirstAdministratorBootstrapReceiptDTO,
    ) -> bool:
        result = await write(writer, facts=facts, receipt=receipt)
        entered.set()
        await release.wait()
        return result

    async def claim() -> None:
        async with database.session() as session:
            await bootstrap_service(session, scenario.binding).bootstrap(scenario.command)

    async def compete() -> None:
        if participant == "initializer":
            state = await PostgresHumanCredentialStateInitializer(database).initialize(
                scenario.binding.identity
            )
            assert state.version == scenario.binding.version and not state.has_pending_recovery
        else:
            async with database.session() as session, session.begin():
                await _recover(session, scenario)

    with patch.object(PostgresFirstAdministratorBootstrapWriter, "bootstrap", new=hold_claim):
        async with asyncio.timeout(30), asyncio.TaskGroup() as tasks:
            claiming = tasks.create_task(claim())
            await entered.wait()
            competing = tasks.create_task(compete())
            await _wait_for_blocked(database, competing)
            release.set()
            await claiming
            await competing
    async with database.session() as session:
        assert await session.scalar(select(func.count()).select_from(PrincipalRow)) == 1
        assert await session.scalar(select(func.count()).select_from(AccessAuditEventRow)) == 1
    state = await PostgresHumanCredentialStateReader(database).read(scenario.binding.identity)
    assert state.version is not None
    assert state.version.value == (2 if participant == "recovery" else 1)
    assert state.has_pending_recovery is (participant == "recovery")


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel", [False, True])
async def test_interrupted_claim_wait_rolls_back_and_leaves_the_turn_usable(
    database: Database, cancel: bool
) -> None:
    scenario = await bootstrap_scenario(database)

    async def claim() -> None:
        async with database.session() as session:
            await bootstrap_service(session, scenario.binding).bootstrap(scenario.command)

    async with asyncio.timeout(30), database.session() as holder:
        async with holder.begin():
            await PostgresIdentityCoordinator(holder).acquire(
                installation_id=scenario.binding.installation_id, identity=scenario.binding.identity
            )
            task = asyncio.create_task(claim())
            try:
                await _wait_for_blocked(database, task)
                if cancel:
                    task.cancel()
                    with pytest.raises(asyncio.CancelledError):
                        await task
                else:
                    with pytest.raises(FirstAdministratorBootstrapError) as error:
                        await task
                    assert error.value.code is Code.DEPENDENCY_UNAVAILABLE
                async with database.session() as observer:
                    assert (
                        await observer.scalar(select(func.count()).select_from(OrganizationRow))
                        == 0
                    )
                    assert (
                        await observer.scalar(
                            select(func.count()).select_from(HostMaintenanceReceiptRow)
                        )
                        == 0
                    )
            finally:
                if not task.done():
                    task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        await claim()


@pytest.mark.asyncio
async def test_released_pre_admission_recovery_history_with_current_generation_can_claim(
    database: Database,
) -> None:
    scenario = await bootstrap_scenario(database)
    async with database.session() as session, session.begin():
        await _recover(session, scenario)
        await session.execute(
            update(IdentityRecoveryAdmissionRow).values(
                released_at=datetime.now(UTC),
                kratos_cleanup_state=IdentityRecoveryCleanupState.CONFIRMED,
                hydra_cleanup_state=IdentityRecoveryCleanupState.CONFIRMED,
            )
        )
    current = replace(scenario.binding, version=HumanCredentialVersion(2))
    async with database.session() as session:
        result = await bootstrap_service(session, current).bootstrap(scenario.command)
    assert result.access_revision == 1
    state = await PostgresHumanCredentialStateReader(database).read(current.identity)
    assert state.version == current.version and not state.has_pending_recovery


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["suspended", "pending-recovery", "missing-generation-history"])
async def test_original_claim_never_bypasses_current_identity_eligibility(
    database: Database, change: str
) -> None:
    scenario = await bootstrap_scenario(database)
    async with database.session() as session:
        await bootstrap_service(session, scenario.binding).bootstrap(scenario.command)
    binding = scenario.binding
    async with database.session() as session, session.begin():
        if change == "suspended":
            await session.execute(update(PrincipalRow).values(status=PrincipalStatus.SUSPENDED))
        else:
            await _recover(session, scenario)
            binding = replace(binding, version=HumanCredentialVersion(2))
            if change == "missing-generation-history":
                await session.execute(delete(HumanCredentialVersionRow))
    async with database.session() as session:
        with pytest.raises(FirstAdministratorBootstrapError) as error:
            await bootstrap_service(session, binding).bootstrap(scenario.command)
        assert error.value.code is (
            Code.INVALID_IDENTITY_PROOF
            if change == "missing-generation-history"
            else Code.IDENTITY_INELIGIBLE
        )
    if change == "missing-generation-history":
        with pytest.raises(DependencyUnavailableError):
            await PostgresHumanCredentialStateInitializer(database).initialize(binding.identity)
    async with database.session() as session:
        assert await session.scalar(select(func.count()).select_from(AccessAuditEventRow)) == 1
        assert (
            await session.scalar(select(func.count()).select_from(OrganizationActionGrantRow)) == 4
        )
        if change == "missing-generation-history":
            assert (
                await session.scalar(select(func.count()).select_from(HumanCredentialVersionRow))
                == 0
            )


@pytest.mark.asyncio
async def test_other_maintenance_modes_cannot_reinterpret_bootstrap_operation(
    database: Database,
) -> None:
    scenario = await bootstrap_scenario(database)
    async with database.session() as session:
        await bootstrap_service(session, scenario.binding).bootstrap(scenario.command)
    async with database.session() as session, session.begin():
        with pytest.raises(RecoveryMaintenanceError) as recovery:
            await PostgresIdentityRecoveryCleanupResumeFactsReader(session).receipt(
                installation_id=scenario.binding.installation_id,
                operation_id=scenario.command.operation_id,
            )
        assert recovery.value.code.value == "idempotency_key_reused"
        with pytest.raises(StrandedAuthorityMaintenanceError) as metadata:
            await PostgresStrandedAuthorityRepairFactsReader(session).receipt(
                installation_id=scenario.binding.installation_id,
                operation_id=scenario.command.operation_id,
            )
        assert metadata.value.code.value == "idempotency_key_reused"


@pytest.mark.asyncio
async def test_bootstrap_cannot_reinterpret_an_existing_metadata_operation(
    database: Database,
) -> None:
    scenario = await bootstrap_scenario(database)
    async with database.session() as session, session.begin():
        session.add(
            HostMaintenanceReceiptRow(
                installation_id=scenario.binding.installation_id.value,
                operator_request_id=scenario.command.operation_id.value,
                authority=scenario.binding.identity.authority.value,
                subject=scenario.binding.identity.subject.value,
                mode="repair-stranded-authority",
                recovery_operation_id=None,
                operator_label="Original operator",
                reason="Original reason",
                authorized_at=datetime.now(UTC),
                outcome="repaired",
                released=None,
                run_id=None,
                deadline=None,
            )
        )
    async with database.session() as session:
        with pytest.raises(FirstAdministratorBootstrapError) as error:
            await bootstrap_service(session, scenario.binding).bootstrap(scenario.command)
        assert error.value.code is Code.KEY_REUSED
    async with database.session() as session:
        assert await session.scalar(select(func.count()).select_from(OrganizationRow)) == 0
        assert (
            await session.scalar(select(HostMaintenanceReceiptRow.mode))
            == "repair-stranded-authority"
        )
