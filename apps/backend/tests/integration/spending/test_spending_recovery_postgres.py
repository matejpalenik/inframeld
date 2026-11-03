"""Prove pending evidence, original receipts and rollback after real session reopen."""

import asyncio
import os
from dataclasses import replace
from decimal import Decimal
from typing import override

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from tests.support.spending_scenarios import (
    accounting_service,
    call_context,
    finish_fixture_job,
    money,
    observation,
    price_basis,
    reserve,
    seed_human_work,
    seed_spending_scenario,
    wait_for_database_lock,
)

from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.bootstrap.spending_accounting_composition import open_spending_accounting
from inframeld_backend.shared.application.dtos.product_job_binding_dto import ProductJobBindingDTO
from inframeld_backend.shared.application.dtos.spending_accounting_result_dto import (
    SpendingAccountingResultDTO,
)
from inframeld_backend.shared.application.dtos.spending_call_record_dto import SpendingCallRecordDTO
from inframeld_backend.shared.application.dtos.spending_evidence_resolution_dto import (
    SpendingEvidenceResolutionDTO,
)
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ConflictError,
    StaleRevisionError,
)
from inframeld_backend.shared.application.errors.spending_errors import IncompleteSpendingFactsError
from inframeld_backend.shared.infrastructure.readers.postgres_spending_ledger_reader import (
    PostgresSpendingLedgerReader,
)
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.rows.durable_job_row import DurableJobRow
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)
from inframeld_backend.shared.infrastructure.rows.model_call_accounting_evidence_row import (
    ModelCallAccountingEvidenceRow,
)
from inframeld_backend.shared.infrastructure.rows.model_call_accounting_row import (
    ModelCallAccountingRow,
)
from inframeld_backend.shared.infrastructure.rows.project_spending_policy_row import (
    ProjectSpendingPolicyRow,
)
from inframeld_backend.shared.infrastructure.writers.postgres_spending_ledger_writer import (
    PostgresSpendingLedgerWriter,
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
        reason="Requires PostgreSQL integration services",
    ),
]


async def test_stale_fence_commits_pending_evidence_without_changing_financial_facts(
    database: Database,
) -> None:
    scenario = await seed_spending_scenario(database)
    call = call_context(scenario)
    original = await reserve(database, call, basis=price_basis())
    await finish_fixture_job(database, scenario, pending_effect=f"call:{call.call_id.value}")
    evidence = observation(call, kind="not_billed", charge=None)
    async with open_spending_accounting(database) as service:
        pending = await service.record_observation(
            call=call, observation=evidence, expected_call_revision=0
        )
    assert pending.pending and pending.record == replace(original.record, revision=1)
    async with database.session() as session:
        reader = PostgresSpendingLedgerReader(session)
        record = await reader.find_call(
            organization_id=scenario.organization_id,
            project_id=scenario.project_id,
            call_id=call.call_id,
        )
        assert record == pending.record
        stored = await reader.observation(record=pending.record, evidence_id=evidence.evidence_id)
        assert stored == (evidence, None, True)
    async with open_spending_accounting(database) as service:
        corrected = await service.reconcile(
            access=scenario.access,
            project_id=scenario.project_id,
            call_id=call.call_id,
            pending_evidence_id=evidence.evidence_id,
            authoritative_evidence_id=evidence.evidence_id,
            expected_call_revision=pending.record.revision,
        )
    assert corrected.record.hold_amount == money("0") and corrected.record.settled_amount == money(
        "0"
    )
    async with database.session() as session:
        row = await session.get(
            ModelCallAccountingEvidenceRow, (call.call_id.value, evidence.evidence_id)
        )
        assert row is not None and row.was_pending and row.applied_state is None
        assert (
            row.resolved_by_evidence_id == evidence.evidence_id
            and row.resolution_revision == corrected.record.revision
        )


async def test_current_authority_loss_rejects_pending_retention(database: Database) -> None:
    scenario = await seed_spending_scenario(database)
    call = call_context(scenario)
    await reserve(database, call, basis=price_basis())
    await finish_fixture_job(database, scenario, pending_effect=f"call:{call.call_id.value}")
    async with database.session() as session, session.begin():
        await session.execute(
            update(PrincipalRow)
            .where(PrincipalRow.id == scenario.access.actor_principal_id.value)
            .values(status=PrincipalStatus.SUSPENDED)
        )
    async with open_spending_accounting(database) as service:
        with pytest.raises(AccessDeniedError):
            await service.record_observation(
                call=call, observation=observation(call), expected_call_revision=0
            )
    async with database.session() as session:
        assert (
            await session.scalar(select(func.count()).select_from(ModelCallAccountingEvidenceRow))
            == 0
        )
        record = await session.get(ModelCallAccountingRow, call.call_id.value)
        assert record is not None and record.hold_amount == Decimal("0.1") and record.revision == 0


async def test_resolution_and_financial_receipts_remain_independent_after_later_correction(
    database: Database,
) -> None:
    scenario = await seed_spending_scenario(database)
    call = call_context(scenario)
    await reserve(database, call, basis=price_basis())
    await finish_fixture_job(database, scenario, pending_effect=f"call:{call.call_id.value}")
    uncertain = observation(call, kind="uncertain", charge=None)
    proof = observation(call, number=2, charge="0.15")
    async with open_spending_accounting(database) as service:
        pending = await service.record_observation(
            call=call, observation=uncertain, expected_call_revision=0
        )
        proof_pending = await service.record_observation(
            call=call, observation=proof, expected_call_revision=pending.record.revision
        )
        first = await service.reconcile(
            access=scenario.access,
            project_id=scenario.project_id,
            call_id=call.call_id,
            pending_evidence_id=uncertain.evidence_id,
            authoritative_evidence_id=proof.evidence_id,
            expected_call_revision=proof_pending.record.revision,
        )
    async with database.session() as session:
        reader = PostgresSpendingLedgerReader(session)
        totals = await reader.project_totals(
            organization_id=scenario.organization_id,
            project_id=scenario.project_id,
            period=first.record.period,
        )
        assert totals.settled == money("0.15") and totals.unquantified_holds == 1
        retained_proof = await reader.observation(
            record=first.record, evidence_id=proof.evidence_id
        )
        assert retained_proof == (proof, first.record, True)
    async with open_spending_accounting(database) as service:
        own = await service.reconcile(
            access=scenario.access,
            project_id=scenario.project_id,
            call_id=call.call_id,
            pending_evidence_id=proof.evidence_id,
            authoritative_evidence_id=proof.evidence_id,
            expected_call_revision=first.record.revision,
        )
        later_evidence = observation(call, number=3, charge="0.2")
        later = await service.record_observation(
            call=call, observation=later_evidence, expected_call_revision=own.record.revision
        )
        corrected = await service.reconcile(
            access=scenario.access,
            project_id=scenario.project_id,
            call_id=call.call_id,
            pending_evidence_id=later_evidence.evidence_id,
            authoritative_evidence_id=later_evidence.evidence_id,
            expected_call_revision=later.record.revision,
        )
    async with open_spending_accounting(database) as service:
        replay = await service.reconcile(
            access=scenario.access,
            project_id=scenario.project_id,
            call_id=call.call_id,
            pending_evidence_id=uncertain.evidence_id,
            authoritative_evidence_id=proof.evidence_id,
            expected_call_revision=proof_pending.record.revision,
        )
        duplicate = await service.record_observation(
            call=call, observation=proof, expected_call_revision=0
        )
    assert replay.recovered and replay.record == first.record
    assert duplicate.recovered and not duplicate.pending and duplicate.record == first.record
    async with database.session() as session:
        record = await PostgresSpendingLedgerReader(session).find_call(
            organization_id=scenario.organization_id,
            project_id=scenario.project_id,
            call_id=call.call_id,
        )
        assert (
            record is not None
            and record == corrected.record
            and record.settled_amount == money("0.2")
        )


class FailingResolutionWriter(PostgresSpendingLedgerWriter):
    def __init__(self, session: AsyncSession, failure_at: str) -> None:
        super().__init__(session)
        self._failure_at = failure_at

    @override
    async def record_resolution(
        self, *, record: SpendingCallRecordDTO, resolution: SpendingEvidenceResolutionDTO
    ) -> None:
        await super().record_resolution(record=record, resolution=resolution)
        if self._failure_at == "resolution":
            raise RuntimeError("Controlled resolution failure")

    @override
    async def save_correction_audit(
        self,
        *,
        actor_id: PrincipalId,
        resolution: SpendingEvidenceResolutionDTO,
        previous_revision: int,
    ) -> None:
        await super().save_correction_audit(
            actor_id=actor_id, resolution=resolution, previous_revision=previous_revision
        )
        if self._failure_at == "audit":
            raise RuntimeError("Controlled resolution failure")


@pytest.mark.parametrize("failure_at", ["resolution", "audit"])
async def test_financial_application_provenance_and_audit_roll_back_together(
    database: Database, failure_at: str
) -> None:
    scenario = await seed_spending_scenario(database)
    call = call_context(scenario)
    await reserve(database, call, basis=price_basis())
    await finish_fixture_job(database, scenario, pending_effect=f"call:{call.call_id.value}")
    evidence = observation(call, charge="0.15")
    async with open_spending_accounting(database) as service:
        pending = await service.record_observation(
            call=call, observation=evidence, expected_call_revision=0
        )
    async with database.session() as session:
        service = accounting_service(session, FailingResolutionWriter(session, failure_at))
        with pytest.raises(RuntimeError, match="Controlled resolution failure"):
            await service.reconcile(
                access=scenario.access,
                project_id=scenario.project_id,
                call_id=call.call_id,
                pending_evidence_id=evidence.evidence_id,
                authoritative_evidence_id=evidence.evidence_id,
                expected_call_revision=pending.record.revision,
            )
    async with database.session() as session:
        reader = PostgresSpendingLedgerReader(session)
        record = await reader.find_call(
            organization_id=scenario.organization_id,
            project_id=scenario.project_id,
            call_id=call.call_id,
        )
        assert record == pending.record
        assert (
            await reader.resolution(record=pending.record, pending_evidence_id=evidence.evidence_id)
            is None
        )
        assert await reader.observation(
            record=pending.record, evidence_id=evidence.evidence_id
        ) == (evidence, None, True)
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AccessAuditEventRow)
                .where(AccessAuditEventRow.event_type == "spending_evidence_resolved")
            )
            == 0
        )


async def test_changed_evidence_identity_and_stale_resolution_cannot_replace_a_receipt(
    database: Database,
) -> None:
    scenario = await seed_spending_scenario(database)
    call = call_context(scenario)
    await reserve(database, call, basis=price_basis())
    evidence = observation(call)
    async with open_spending_accounting(database) as service:
        settled = await service.record_observation(
            call=call, observation=evidence, expected_call_revision=0
        )
        with pytest.raises(ConflictError):
            await service.record_observation(
                call=call,
                observation=replace(evidence, charge=Decimal("0.3")),
                expected_call_revision=settled.record.revision,
            )
        later = observation(call, number=2, charge="0.2")
        pending = await service.record_observation(
            call=call, observation=later, expected_call_revision=settled.record.revision
        )
        with pytest.raises(StaleRevisionError):
            await service.reconcile(
                access=scenario.access,
                project_id=scenario.project_id,
                call_id=call.call_id,
                pending_evidence_id=later.evidence_id,
                authoritative_evidence_id=later.evidence_id,
                expected_call_revision=settled.record.revision,
            )
    async with database.session() as session:
        assert (
            await PostgresSpendingLedgerReader(session).find_call(
                organization_id=scenario.organization_id,
                project_id=scenario.project_id,
                call_id=call.call_id,
            )
            == pending.record
        )


@pytest.mark.parametrize("transition", ["reservation", "approval"])
@pytest.mark.parametrize("order", ["pending-first", "current-first"])
async def test_older_stale_evidence_and_newer_current_work_share_accounting_lock(
    database: Database, transition: str, order: str
) -> None:
    human = await seed_spending_scenario(database)
    await finish_fixture_job(database, human)
    older = await seed_human_work(database, human, "older-job")
    old_call = call_context(older)
    await reserve(database, old_call, basis=price_basis())
    await finish_fixture_job(database, older, pending_effect=f"call:{old_call.call_id.value}")
    async with database.session() as session:
        stopped = await session.get(DurableJobRow, older.attempt.job_id.value)
        assert stopped is not None and stopped.status == "recovery_required"
        assert stopped.fence is None and stopped.pending_effect is not None
        original = older.attempt.binding
        assert isinstance(original, ProductJobBindingDTO)
        replay = await session.get(IdempotencyReservationRow, original.operation_id.value)
        assert replay is not None and replay.expires_at is None
    newer = await seed_human_work(database, human, "newer-job")
    new_call = call_context(newer)
    if transition == "approval":
        await reserve(database, new_call, basis=price_basis())
    evidence = observation(old_call, kind="uncertain", charge=None)

    async def retain() -> SpendingAccountingResultDTO:
        async with open_spending_accounting(database) as service:
            return await service.record_observation(
                call=old_call, observation=evidence, expected_call_revision=0
            )

    async def start_new() -> SpendingAccountingResultDTO:
        if transition == "reservation":
            return await reserve(database, new_call, basis=price_basis())
        async with open_spending_accounting(database) as service:
            return await service.approve_accounting(call=new_call, expected_call_revision=0)

    pending_task: asyncio.Task[SpendingAccountingResultDTO] | None = None
    new_task: asyncio.Task[SpendingAccountingResultDTO] | None = None
    committed: SpendingAccountingResultDTO | None = None
    async with asyncio.timeout(12), database.session() as holder:
        try:
            async with holder.begin():
                await holder.scalar(
                    select(ProjectSpendingPolicyRow.project_id)
                    .where(ProjectSpendingPolicyRow.project_id == human.project_id.value)
                    .with_for_update()
                )
                if order == "pending-first":
                    pending_task = asyncio.create_task(retain())
                    await wait_for_database_lock(database, pending_task)
                    new_task = asyncio.create_task(start_new())
                    await wait_for_database_lock(database, new_task, minimum=2)
                else:
                    new_task = asyncio.create_task(start_new())
                    await wait_for_database_lock(database, new_task)
                    pending_task = asyncio.create_task(retain())
                    await wait_for_database_lock(database, pending_task, minimum=2)
            pending = await pending_task
            assert pending.pending
            if order == "pending-first":
                with pytest.raises(IncompleteSpendingFactsError):
                    await new_task
            else:
                committed = await new_task
                with pytest.raises(IncompleteSpendingFactsError):
                    await reserve(database, call_context(newer, 3), basis=price_basis())
        finally:
            owned = [task for task in (pending_task, new_task) if task is not None]
            for task in owned:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*owned, return_exceptions=True)
    async with database.session() as session:
        reader = PostgresSpendingLedgerReader(session)
        retained = await reader.find_call(
            organization_id=older.organization_id,
            project_id=older.project_id,
            call_id=old_call.call_id,
        )
        assert (
            retained is not None and retained.hold_amount == money("0.1") and retained.revision == 1
        )
        current = await reader.find_call(
            organization_id=newer.organization_id,
            project_id=newer.project_id,
            call_id=new_call.call_id,
        )
        if order == "current-first":
            assert committed is not None and current == committed.record
        elif transition == "reservation":
            assert current is None
        else:
            assert (
                current is not None
                and current.hold_amount == money("0.1")
                and current.revision == 0
            )
