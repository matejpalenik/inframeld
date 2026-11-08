"""Protect spending persistence without changing delivered Project/job records."""

import os
from decimal import Decimal
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from tests.support.spending_scenarios import (
    call_context,
    finish_fixture_job,
    money,
    observation,
    price_basis,
    reserve,
    seed_spending_scenario,
)

from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.bootstrap.spending_accounting_composition import open_spending_accounting
from inframeld_backend.shared.infrastructure.migrations.migration_runner import (
    BACKEND_ROOT,
    run_migrations,
)
from inframeld_backend.shared.infrastructure.readers.postgres_spending_ledger_reader import (
    PostgresSpendingLedgerReader,
)
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.rows.alembic_version_row import AlembicVersionRow
from inframeld_backend.shared.infrastructure.rows.durable_job_row import DurableJobRow
from inframeld_backend.shared.infrastructure.rows.model_call_accounting_evidence_row import (
    ModelCallAccountingEvidenceRow,
)
from inframeld_backend.shared.infrastructure.rows.model_call_accounting_row import (
    ModelCallAccountingRow,
)
from inframeld_backend.shared.infrastructure.rows.project_spending_policy_row import (
    ProjectSpendingPolicyRow,
)
from inframeld_backend.shared.infrastructure.settings.database_settings import DatabaseSettings

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
        reason="Requires PostgreSQL integration services",
    ),
]


def configuration(settings: DatabaseSettings) -> Config:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.attributes["database_settings"] = settings
    return config


async def test_empty_spending_roundtrip_preserves_delivered_project_and_original_job(
    database: Database, temporary_postgres_settings: DatabaseSettings
) -> None:
    scenario = await seed_spending_scenario(database, create_account=False)
    for _ in range(2):
        command.downgrade(configuration(temporary_postgres_settings), "0017_project_creation")
        run_migrations(temporary_postgres_settings)
        async with database.session() as session:
            assert await session.scalar(select(AlembicVersionRow.version_num)) == "0027_invitations"
            assert await session.get(ProjectRow, scenario.project_id.value) is not None
            job = await session.get(DurableJobRow, scenario.attempt.job_id.value)
            assert job is not None and job.fence == scenario.attempt.fence.value
            assert (
                await session.scalar(select(func.count()).select_from(ProjectSpendingPolicyRow))
                == 0
            )


@pytest.mark.parametrize(
    "corruption", ["negative", "quantum", "nonfinite", "month", "fingerprint", "state", "scope"]
)
async def test_constraints_refuse_invalid_amount_period_identity_state_and_scope(
    database: Database, corruption: str
) -> None:
    scenario = await seed_spending_scenario(database)
    call = call_context(scenario)
    await reserve(database, call, basis=price_basis())
    statement = update(ModelCallAccountingRow).where(
        ModelCallAccountingRow.call_id == call.call_id.value
    )
    if corruption == "negative":
        statement = statement.values(hold_amount=Decimal("-0.1"))
    elif corruption == "quantum":
        statement = statement.values(hold_amount=Decimal("0.0000000000001"))
    elif corruption == "nonfinite":
        statement = statement.values(hold_amount=Decimal("Infinity"))
    elif corruption == "month":
        statement = statement.values(period_month=13)
    elif corruption == "fingerprint":
        statement = statement.values(meaning_fingerprint=b"short")
    elif corruption == "state":
        statement = statement.values(state="free-without-evidence")
    else:
        statement = statement.values(project_id=uuid4())
    async with database.session() as session:
        with pytest.raises(IntegrityError):
            async with session.begin():
                await session.execute(statement)
    async with database.session() as session:
        row = await session.get(ModelCallAccountingRow, call.call_id.value)
        assert row is not None and row.hold_amount == Decimal("0.1") and row.revision == 0


async def test_resolution_relation_must_name_evidence_for_the_same_call(database: Database) -> None:
    scenario = await seed_spending_scenario(database)
    call = call_context(scenario)
    other_call = call_context(scenario, 2)
    await reserve(database, call, basis=price_basis())
    await reserve(database, other_call, basis=price_basis())
    await finish_fixture_job(database, scenario, pending_effect="accounting-relation-fixture")
    evidence = observation(call, charge="0.08")
    other_evidence = observation(other_call, charge="0.07")
    async with open_spending_accounting(database) as service:
        pending = await service.record_observation(
            call=call, observation=evidence, expected_call_revision=0
        )
        other_pending = await service.record_observation(
            call=other_call, observation=other_evidence, expected_call_revision=0
        )
        assert pending.pending and other_pending.pending
        resolved = await service.reconcile(
            access=scenario.access,
            project_id=scenario.project_id,
            call_id=call.call_id,
            pending_evidence_id=evidence.evidence_id,
            authoritative_evidence_id=evidence.evidence_id,
            expected_call_revision=pending.record.revision,
        )
    assert resolved.record.settled_amount == money("0.08")
    async with database.session() as session:
        existing_other = await session.get(
            ModelCallAccountingEvidenceRow, (other_call.call_id.value, other_evidence.evidence_id)
        )
        assert existing_other is not None and existing_other.was_pending
        assert existing_other.resolved_by_evidence_id is None
    async with database.session() as session:
        with pytest.raises(IntegrityError):
            async with session.begin():
                await session.execute(
                    update(ModelCallAccountingEvidenceRow)
                    .where(
                        ModelCallAccountingEvidenceRow.call_id == call.call_id.value,
                        ModelCallAccountingEvidenceRow.evidence_id == evidence.evidence_id,
                    )
                    .values(resolved_by_evidence_id=other_evidence.evidence_id)
                )
    async with database.session() as session:
        reader = PostgresSpendingLedgerReader(session)
        record = await reader.find_call(
            organization_id=scenario.organization_id,
            project_id=scenario.project_id,
            call_id=call.call_id,
        )
        assert record == resolved.record
        retained = await reader.resolution(
            record=resolved.record, pending_evidence_id=evidence.evidence_id
        )
        assert retained is not None and retained.authoritative_evidence_id == evidence.evidence_id
        assert retained.result == resolved.record


async def test_retained_financial_obligations_refuse_downgrade(
    database: Database, temporary_postgres_settings: DatabaseSettings
) -> None:
    scenario = await seed_spending_scenario(database)
    call = call_context(scenario)
    await reserve(database, call, basis=price_basis())
    with pytest.raises(RuntimeError, match="Retained spending"):
        command.downgrade(configuration(temporary_postgres_settings), "0017_project_creation")
    async with database.session() as session:
        assert await session.scalar(select(AlembicVersionRow.version_num)) == "0027_invitations"
        row = await session.get(ModelCallAccountingRow, call.call_id.value)
        assert row is not None and row.hold_amount == Decimal("0.1")
