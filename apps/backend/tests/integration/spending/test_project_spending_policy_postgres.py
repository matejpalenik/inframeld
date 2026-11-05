"""Qualify human-only policy coordination, original replay and coherent projections."""

import asyncio
import os
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from typing import override

import pytest
from sqlalchemy import delete, func, select, update
from tests.support.spending_scenarios import (
    call_context,
    change_limit,
    fingerprints,
    finish_fixture_job,
    money,
    observation,
    policy_service,
    price_basis,
    reserve,
    seed_human_work,
    seed_other_budget_human,
    seed_spending_scenario,
    wait_for_database_lock,
)

from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.bootstrap.spending_accounting_composition import (
    open_project_spending_policy,
    open_spending_accounting,
)
from inframeld_backend.shared.application.commands.change_project_spending_policy_command import (
    ChangeProjectSpendingPolicyCommand,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import (
    IdempotencyContextDTO,
)
from inframeld_backend.shared.application.dtos.project_spending_policy_dto import (
    ProjectSpendingPolicyDTO,
)
from inframeld_backend.shared.application.dtos.project_spending_policy_result_dto import (
    ProjectSpendingPolicyResultDTO,
)
from inframeld_backend.shared.application.dtos.spending_accounting_result_dto import (
    SpendingAccountingResultDTO,
)
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.enums.spending_call_state import SpendingCallState
from inframeld_backend.shared.application.enums.spending_observation_kind import (
    SpendingObservationKind,
)
from inframeld_backend.shared.application.errors.application_errors import (
    ResourceNotFoundError,
    StaleRevisionError,
)
from inframeld_backend.shared.application.errors.spending_errors import (
    IncompleteSpendingFactsError,
    SpendingLimitExceededError,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.application.value_objects.spending_period import SpendingPeriod
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)
from inframeld_backend.shared.infrastructure.rows.model_call_accounting_row import (
    ModelCallAccountingRow,
)
from inframeld_backend.shared.infrastructure.rows.project_spending_policy_operation_result_row import (
    ProjectSpendingPolicyOperationResultRow,
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


async def test_simultaneous_initial_policy_edits_have_one_winner_and_one_stale_review(
    database: Database,
) -> None:
    scenario = await seed_spending_scenario(database, create_account=False)

    other_access = await seed_other_budget_human(database, scenario)

    async def edit(key: str) -> ProjectSpendingPolicyResultDTO | StaleRevisionError:
        try:
            return await change_limit(
                database,
                scenario if key == "first" else replace(scenario, access=other_access),
                money("2"),
                key=key,
            )
        except StaleRevisionError as error:
            return error

    async with asyncio.timeout(12), asyncio.TaskGroup() as tasks:
        first = tasks.create_task(edit("first"))
        second = tasks.create_task(edit("second"))
    assert (
        sum(
            isinstance(result, ProjectSpendingPolicyResultDTO)
            for result in [first.result(), second.result()]
        )
        == 1
    )
    assert (
        sum(isinstance(result, StaleRevisionError) for result in [first.result(), second.result()])
        == 1
    )
    async with database.session() as session:
        assert await session.scalar(select(func.count()).select_from(ProjectSpendingPolicyRow)) == 1
        assert (
            await session.scalar(
                select(func.count()).select_from(ProjectSpendingPolicyOperationResultRow)
            )
            == 1
        )


async def test_policy_edit_and_replay_preserve_holds_and_the_original_result(
    database: Database,
) -> None:
    scenario = await seed_spending_scenario(database)
    call = call_context(scenario)
    original = await reserve(database, call, basis=price_basis(), operation_limit=money("1"))
    first = await change_limit(database, scenario, money("2"))
    await change_limit(database, scenario, None, revision=1, key="remove-limit")
    replay = await change_limit(database, scenario, money("2"))
    assert replay.policy == first.policy and not replay.completion.created
    async with database.session() as session:
        row = await session.get(ModelCallAccountingRow, call.call_id.value)
        assert original.record.hold_amount is not None
        assert row is not None and row.hold_amount == original.record.hold_amount.value
        current = await session.get(ProjectSpendingPolicyRow, scenario.project_id.value)
        assert current is not None and current.monthly_limit is None and current.revision == 2
    async with database.session() as session, session.begin():
        await session.execute(
            update(PrincipalRow)
            .where(PrincipalRow.id == scenario.access.actor_principal_id.value)
            .values(status=PrincipalStatus.SUSPENDED)
        )
    with pytest.raises(ResourceNotFoundError):
        await change_limit(database, scenario, money("2"))


async def test_unknown_original_obligation_survives_a_new_cap_in_its_captured_month(
    database: Database,
) -> None:
    scenario = await seed_spending_scenario(database, monthly_limit=None)
    call = call_context(scenario)
    original = await reserve(database, call, basis=None)
    async with open_spending_accounting(database) as service:
        unresolved = await service.record_observation(
            call=call,
            observation=observation(call, kind=SpendingObservationKind.UNCERTAIN, charge=None),
            expected_call_revision=0,
        )
    await change_limit(database, scenario, money("2"))
    with pytest.raises(IncompleteSpendingFactsError):
        await reserve(database, call_context(scenario, 2), basis=price_basis())
    assert unresolved.record.period == original.record.period
    async with database.session() as session, session.begin():
        await session.execute(
            update(ModelCallAccountingRow)
            .where(ModelCallAccountingRow.call_id == call.call_id.value)
            .values(period_year=2000, period_month=1)
        )
    new = await reserve(database, call_context(scenario, 2), basis=price_basis())
    assert new.record.period != SpendingPeriod(2000, 1)
    async with database.session() as session:
        historical = await session.get(ModelCallAccountingRow, call.call_id.value)
        assert (
            historical is not None
            and historical.hold_amount is None
            and historical.period_year == 2000
        )


async def test_lower_policy_before_approval_denies_without_erasing_a_hold(
    database: Database,
) -> None:
    scenario = await seed_spending_scenario(database)
    call = call_context(scenario)
    await reserve(database, call, basis=price_basis("0.7"))
    await change_limit(database, scenario, money("0.5"))
    async with open_spending_accounting(database) as service:
        with pytest.raises(SpendingLimitExceededError):
            await service.approve_accounting(call=call, expected_call_revision=0)
    async with open_project_spending_policy(database, fingerprints()) as policy:
        projection = await policy.inspect(
            access=scenario.access,
            project_id=scenario.project_id,
            period=SpendingPeriod.from_instant(datetime.now(UTC)),
        )
    assert projection.remaining == money("-0.2") and projection.totals.held == money("0.7")


async def test_projection_observes_coherent_policy_and_financial_states_across_commit(
    database: Database,
) -> None:
    scenario = await seed_spending_scenario(database)
    call = call_context(scenario)
    reserved = await reserve(database, call, basis=price_basis())
    async with database.session() as holder, holder.begin():
        await holder.execute(
            update(ProjectSpendingPolicyRow)
            .where(ProjectSpendingPolicyRow.project_id == scenario.project_id.value)
            .values(monthly_limit=Decimal("2"), revision=1)
        )
        await holder.execute(
            update(ModelCallAccountingRow)
            .where(ModelCallAccountingRow.call_id == call.call_id.value)
            .values(
                state="settled",
                hold_amount=Decimal("0"),
                settled_amount=Decimal("0.08"),
                revision=1,
            )
        )
        async with open_project_spending_policy(database, fingerprints()) as policy:
            old = await policy.inspect(
                access=scenario.access,
                project_id=scenario.project_id,
                period=reserved.record.period,
            )
        assert (
            old.policy.revision,
            old.policy.monthly_limit,
            old.totals.settled,
            old.totals.held,
        ) == (0, money("1"), money("0"), money("0.1"))
    async with open_project_spending_policy(database, fingerprints()) as policy:
        current = await policy.inspect(
            access=scenario.access, project_id=scenario.project_id, period=reserved.record.period
        )
    assert (
        current.policy.revision,
        current.policy.monthly_limit,
        current.totals.settled,
        current.totals.held,
    ) == (1, money("2"), money("0.08"), money("0"))


class FailingPolicyReceiptWriter(PostgresSpendingLedgerWriter):
    @override
    async def save_policy_result(
        self,
        *,
        policy: ProjectSpendingPolicyDTO,
        actor_id: PrincipalId,
        operation_id: OperationId,
        changed: bool,
    ) -> None:
        await super().save_policy_result(
            policy=policy, actor_id=actor_id, operation_id=operation_id, changed=changed
        )
        raise RuntimeError("Controlled policy receipt failure")


async def test_required_receipt_failure_rolls_back_policy_audit_and_replay(
    database: Database,
) -> None:
    scenario = await seed_spending_scenario(database)
    async with database.session() as session:
        service = policy_service(session, FailingPolicyReceiptWriter(session))
        with pytest.raises(RuntimeError, match="Controlled policy receipt failure"):
            await service.change_limit(
                access=scenario.access,
                command=ChangeProjectSpendingPolicyCommand(scenario.project_id, 0, money("2")),
                context=IdempotencyContextDTO(
                    HttpMethod.PATCH,
                    "/internal/projects/{project_id}/spending-policy",
                    IdempotencyKey("failed-policy"),
                ),
            )
    async with database.session() as session:
        policy = await session.get(ProjectSpendingPolicyRow, scenario.project_id.value)
        assert policy is not None and policy.monthly_limit == Decimal("1") and policy.revision == 0
        assert (
            await session.scalar(
                select(func.count()).select_from(ProjectSpendingPolicyOperationResultRow)
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(IdempotencyReservationRow)
                .where(IdempotencyReservationRow.request_key == "failed-policy")
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AccessAuditEventRow)
                .where(AccessAuditEventRow.event_type == "project_spending_policy_changed")
            )
            == 0
        )


async def test_expiring_policy_replay_cannot_delete_financial_history_or_holds(
    database: Database,
) -> None:
    scenario = await seed_spending_scenario(database)
    call = call_context(scenario)
    original = await reserve(database, call, basis=price_basis())
    changed = await change_limit(database, scenario, money("2"))
    async with database.session() as session, session.begin():
        await session.execute(
            delete(IdempotencyReservationRow).where(
                IdempotencyReservationRow.operation_id == changed.completion.operation_id.value
            )
        )
    async with database.session() as session:
        assert (
            await session.get(
                ProjectSpendingPolicyOperationResultRow, changed.completion.operation_id.value
            )
            is None
        )
        row = await session.get(ModelCallAccountingRow, call.call_id.value)
        assert original.record.hold_amount is not None
        assert row is not None and row.hold_amount == original.record.hold_amount.value


async def test_authority_change_before_organization_unlock_blocks_policy_mutation(
    database: Database,
) -> None:
    scenario = await seed_spending_scenario(database)
    task: asyncio.Task[ProjectSpendingPolicyResultDTO] | None = None
    async with asyncio.timeout(12), database.session() as holder:
        try:
            async with holder.begin():
                await holder.scalar(
                    select(OrganizationRow.id)
                    .where(OrganizationRow.id == scenario.organization_id.value)
                    .with_for_update()
                )
                task = asyncio.create_task(change_limit(database, scenario, money("2")))
                await wait_for_database_lock(database, task)
                await holder.execute(
                    update(PrincipalRow)
                    .where(PrincipalRow.id == scenario.access.actor_principal_id.value)
                    .values(status=PrincipalStatus.SUSPENDED)
                )
            with pytest.raises(ResourceNotFoundError):
                await task
        finally:
            if task is not None:
                if not task.done():
                    task.cancel()
                await asyncio.gather(task, return_exceptions=True)
    async with database.session() as session:
        policy = await session.get(ProjectSpendingPolicyRow, scenario.project_id.value)
        assert policy is not None and policy.revision == 0 and policy.monthly_limit == Decimal("1")
        assert (
            await session.scalar(
                select(func.count()).select_from(ProjectSpendingPolicyOperationResultRow)
            )
            == 0
        )


@pytest.mark.parametrize("order", ["policy-first", "approval-first"])
async def test_one_current_human_job_and_other_human_policy_edit_share_accounting_order(
    database: Database, order: str
) -> None:
    human = await seed_spending_scenario(database)
    await finish_fixture_job(database, human)
    worker = await seed_human_work(database, human, "human-work")
    call = call_context(worker)
    await reserve(database, call, basis=price_basis("0.7"))

    async def approve() -> SpendingAccountingResultDTO | SpendingLimitExceededError:
        try:
            async with open_spending_accounting(database) as service:
                return await service.approve_accounting(call=call, expected_call_revision=0)
        except SpendingLimitExceededError as error:
            return error

    approval_task: asyncio.Task[SpendingAccountingResultDTO | SpendingLimitExceededError] | None = (
        None
    )
    edit_task: asyncio.Task[ProjectSpendingPolicyResultDTO] | None = None
    async with asyncio.timeout(12), database.session() as holder:
        try:
            async with holder.begin():
                await holder.scalar(
                    select(ProjectSpendingPolicyRow.project_id)
                    .where(ProjectSpendingPolicyRow.project_id == human.project_id.value)
                    .with_for_update()
                )
                if order == "policy-first":
                    edit_task = asyncio.create_task(change_limit(database, human, money("0.5")))
                    await wait_for_database_lock(database, edit_task)
                    approval_task = asyncio.create_task(approve())
                    await wait_for_database_lock(database, approval_task, minimum=2)
                else:
                    approval_task = asyncio.create_task(approve())
                    await wait_for_database_lock(database, approval_task)
                    edit_task = asyncio.create_task(change_limit(database, human, money("0.5")))
                    await wait_for_database_lock(database, edit_task, minimum=2)
            outcome = await approval_task
            changed = await edit_task
            assert changed.policy.revision == 1
            if order == "policy-first":
                assert isinstance(outcome, SpendingLimitExceededError)
            else:
                assert isinstance(outcome, SpendingAccountingResultDTO)
                assert outcome.record.state is SpendingCallState.ACCOUNTING_APPROVED
                assert outcome.record.approved_policy_revision == 0
        finally:
            owned = [task for task in (approval_task, edit_task) if task is not None]
            for task in owned:
                if not task.done():
                    task.cancel()
            if approval_task is not None:
                await asyncio.gather(approval_task, return_exceptions=True)
            if edit_task is not None:
                await asyncio.gather(edit_task, return_exceptions=True)
    async with database.session() as session:
        row = await session.get(ModelCallAccountingRow, call.call_id.value)
        assert row is not None and row.hold_amount == Decimal("0.7")
        assert row.state == (
            SpendingCallState.RESERVED.value
            if order == "policy-first"
            else SpendingCallState.ACCOUNTING_APPROVED.value
        )
