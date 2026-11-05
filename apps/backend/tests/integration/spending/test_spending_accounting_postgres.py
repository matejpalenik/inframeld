"""Qualify internal accounting against real PostgreSQL and admitted job ownership."""

import asyncio
import os
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select, update
from tests.support.spending_scenarios import (
    call_context,
    finish_fixture_job,
    money,
    observation,
    price_basis,
    reserve,
    seed_human_work,
    seed_spending_scenario,
)

from inframeld_backend.bootstrap.spending_accounting_composition import open_spending_accounting
from inframeld_backend.shared.application.dtos.spending_accounting_result_dto import (
    SpendingAccountingResultDTO,
)
from inframeld_backend.shared.application.dtos.spending_call_context_dto import (
    SpendingCallContextDTO,
)
from inframeld_backend.shared.application.dtos.spending_call_record_dto import SpendingCallRecordDTO
from inframeld_backend.shared.application.enums.spending_call_state import SpendingCallState
from inframeld_backend.shared.application.enums.spending_observation_kind import (
    SpendingObservationKind,
)
from inframeld_backend.shared.application.errors.application_errors import ConflictError
from inframeld_backend.shared.application.errors.spending_errors import (
    IncompleteSpendingFactsError,
    SpendingLimitExceededError,
)
from inframeld_backend.shared.application.value_objects.spending_period import SpendingPeriod
from inframeld_backend.shared.domain.policies.spending_allowance_policy import (
    SpendingAllowancePolicy,
)
from inframeld_backend.shared.domain.policy_inputs.spending_allowance_policy_input import (
    SpendingAllowancePolicyInput,
)
from inframeld_backend.shared.domain.value_objects.usd_amount import UsdAmount
from inframeld_backend.shared.infrastructure.readers.postgres_spending_ledger_reader import (
    PostgresSpendingLedgerReader,
)
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.rows.model_call_accounting_row import (
    ModelCallAccountingRow,
)
from inframeld_backend.shared.infrastructure.rows.project_spending_policy_row import (
    ProjectSpendingPolicyRow,
)
from inframeld_backend.shared.infrastructure.rows.spending_operation_row import SpendingOperationRow
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


async def _reserve_prepared_record(
    database: Database, call: SpendingCallContextDTO, amount: UsdAmount
) -> SpendingCallRecordDTO:
    """Exercise the SQL coordination mechanism with prepared original attribution.

    These port-level races qualify transaction locking and upsert behavior. They
    make no service-admission or dispatch claim. Service scenarios use actual
    current authorization and globally serial job ownership separately.
    """
    async with database.session() as session, session.begin():
        reader, writer = (
            PostgresSpendingLedgerReader(session),
            PostgresSpendingLedgerWriter(session),
        )
        await writer.ensure_project_account(
            organization_id=call.authority.organization_id, project_id=call.authority.project_id
        )
        policy = await reader.lock_project_policy(
            organization_id=call.authority.organization_id, project_id=call.authority.project_id
        )
        await writer.ensure_operation(call=call, operation_limit=None)
        period = SpendingPeriod.from_instant(policy.observed_at)
        totals = await reader.project_totals(
            organization_id=call.authority.organization_id,
            project_id=call.authority.project_id,
            period=period,
        )
        zero = money("0")
        if not SpendingAllowancePolicy.can_reserve(
            SpendingAllowancePolicyInput(
                project_limit=policy.monthly_limit,
                project_settled=totals.settled,
                project_held=totals.held,
                operation_limit=None,
                operation_settled=zero,
                operation_held=zero,
                reservation_amount=amount,
            )
        ):
            raise SpendingLimitExceededError()
        record = SpendingCallRecordDTO(
            call_id=call.call_id,
            operation_id=call.operation_id,
            authority=call.authority,
            job_id=call.attempt.job_id,
            meaning_fingerprint=call.meaning_fingerprint,
            period=period,
            operation_limit=None,
            basis=None,
            reserved_amount=amount,
            hold_amount=amount,
            settled_amount=None,
            state=SpendingCallState.RESERVED,
            revision=0,
            reservation_policy_revision=policy.revision,
        )
        await writer.insert_call(record)
        return record


async def test_reader_writer_coordinate_the_final_allowance_across_transactions(
    database: Database,
) -> None:
    older = await seed_spending_scenario(database)
    await finish_fixture_job(database, older)
    newer = await seed_human_work(database, older, "newer-operation")

    async def attempt(old: bool) -> SpendingCallRecordDTO | SpendingLimitExceededError:
        try:
            return await _reserve_prepared_record(
                database, call_context(older if old else newer), money("0.7")
            )
        except SpendingLimitExceededError as error:
            return error

    async with asyncio.timeout(12), asyncio.TaskGroup() as tasks:
        first = tasks.create_task(attempt(True))
        second = tasks.create_task(attempt(False))
    results = [first.result(), second.result()]
    assert sum(isinstance(result, SpendingCallRecordDTO) for result in results) == 1
    assert sum(isinstance(result, SpendingLimitExceededError) for result in results) == 1
    async with database.session() as session:
        assert await session.scalar(select(func.count()).select_from(ModelCallAccountingRow)) == 1
        totals = await PostgresSpendingLedgerReader(session).project_totals(
            organization_id=older.organization_id,
            project_id=older.project_id,
            period=SpendingPeriod.from_instant(datetime.now(UTC)),
        )
        assert totals.held == money("0.7") and totals.settled == money("0")


async def test_reader_writer_coordinate_first_root_for_distinct_original_operations(
    database: Database,
) -> None:
    older = await seed_spending_scenario(database, create_account=False)
    await finish_fixture_job(database, older)
    newer = await seed_human_work(database, older, "newer-operation")
    async with asyncio.timeout(12), asyncio.TaskGroup() as tasks:
        first = tasks.create_task(
            _reserve_prepared_record(database, call_context(older), money("0.1"))
        )
        second = tasks.create_task(
            _reserve_prepared_record(database, call_context(newer), money("0.1"))
        )
    assert first.result().call_id != second.result().call_id
    async with database.session() as session:
        assert await session.scalar(select(func.count()).select_from(ProjectSpendingPolicyRow)) == 1
        assert await session.scalar(select(func.count()).select_from(SpendingOperationRow)) == 2
        assert await session.scalar(select(func.count()).select_from(ModelCallAccountingRow)) == 2


async def test_call_replay_preserves_subquantum_rates_and_rejects_changed_meaning(
    database: Database,
) -> None:
    scenario = await seed_spending_scenario(database)
    call = call_context(scenario)
    basis = price_basis("0.000000000000001", "1000")
    first = await reserve(database, call, basis=basis, operation_limit=money("1"))
    replay = await reserve(database, call, basis=basis, operation_limit=money("1"))
    assert first.record.reserved_amount == money("0.000000000001")
    assert replay.recovered and replay.record == first.record
    assert replay.record.basis == basis
    with pytest.raises(ConflictError):
        await reserve(database, call, basis=price_basis("0.2"), operation_limit=money("1"))


async def test_concurrent_duplicate_charge_is_one_honest_overage_after_reopening(
    database: Database,
) -> None:
    scenario = await seed_spending_scenario(database)
    call = call_context(scenario)
    await reserve(database, call, basis=price_basis(), operation_limit=money("0.1"))
    evidence = observation(call, charge="0.15")

    async def settle() -> SpendingAccountingResultDTO:
        async with open_spending_accounting(database) as service:
            return await service.record_observation(
                call=call, observation=evidence, expected_call_revision=0
            )

    async with asyncio.timeout(12), asyncio.TaskGroup() as tasks:
        first = tasks.create_task(settle())
        second = tasks.create_task(settle())
    assert first.result().record == second.result().record
    assert sorted([first.result().recovered, second.result().recovered]) == [False, True]
    async with database.session() as session:
        record = await PostgresSpendingLedgerReader(session).find_call(
            organization_id=scenario.organization_id,
            project_id=scenario.project_id,
            call_id=call.call_id,
        )
        assert record is not None and record.state is SpendingCallState.SETTLED
        assert record.settled_amount == money("0.15") and record.hold_amount == money("0")
    with pytest.raises(SpendingLimitExceededError):
        await reserve(
            database, call_context(scenario, 2), basis=price_basis(), operation_limit=money("0.1")
        )


async def test_operation_limit_spans_captured_project_months_and_preserves_late_attribution(
    database: Database,
) -> None:
    scenario = await seed_spending_scenario(database)
    call = call_context(scenario)
    await reserve(database, call, basis=price_basis("0.6"), operation_limit=money("1"))
    # Place this controlled historical call in an earlier month without changing
    # the host clock or the operation's original identity and cumulative limit.
    async with database.session() as session, session.begin():
        await session.execute(
            update(ModelCallAccountingRow)
            .where(ModelCallAccountingRow.call_id == call.call_id.value)
            .values(period_year=2000, period_month=1)
        )
    async with open_spending_accounting(database) as service:
        settled = await service.record_observation(
            call=call, observation=observation(call, charge="0.6"), expected_call_revision=0
        )
    assert settled.record.period == SpendingPeriod(2000, 1)
    with pytest.raises(SpendingLimitExceededError):
        await reserve(
            database,
            call_context(scenario, 2),
            basis=price_basis("0.6"),
            operation_limit=money("1"),
        )
    with pytest.raises(ConflictError):
        await reserve(
            database, call_context(scenario, 2), basis=price_basis(), operation_limit=None
        )


async def test_capped_unknown_pricing_and_missing_usage_never_release_an_unproven_hold(
    database: Database,
) -> None:
    scenario = await seed_spending_scenario(database)
    call = call_context(scenario)
    with pytest.raises(IncompleteSpendingFactsError):
        await reserve(database, call, basis=None)
    first = await reserve(database, call, basis=price_basis())
    async with open_spending_accounting(database) as service:
        unresolved = await service.record_observation(
            call=call,
            observation=observation(call, kind=SpendingObservationKind.UNCERTAIN, charge=None),
            expected_call_revision=0,
        )
    assert unresolved.record.hold_amount == first.record.hold_amount
    assert unresolved.record.state is SpendingCallState.UNRESOLVED
    async with open_spending_accounting(database) as service:
        with pytest.raises(ConflictError):
            await service.approve_accounting(
                call=call, expected_call_revision=unresolved.record.revision
            )
