"""Preserve old request meaning while backfilling only the fixed delivered grant."""

import os
from datetime import UTC, datetime

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from tests.support.access_scenarios import MockAccessScenarios
from tests.support.legacy_operation_reservation_row import LegacyOperationReservationRow

from inframeld_backend.shared.infrastructure.migrations.migration_runner import (
    BACKEND_ROOT,
    run_migrations,
)
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)
from inframeld_backend.shared.infrastructure.settings.database_settings import DatabaseSettings

pytestmark = pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
    reason="Requires PostgreSQL integration services",
)


@pytest.mark.asyncio
async def test_only_fixed_grant_history_gets_authoritative_backfill(
    temporary_postgres_settings: DatabaseSettings,
) -> None:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    config.attributes["database_settings"] = temporary_postgres_settings
    command.upgrade(config, "0008_host_maintenance_receipts")
    database = Database(temporary_postgres_settings)
    expiry = datetime(2030, 1, 1, tzinfo=UTC)
    try:
        async with database.session() as session, session.begin():
            seed = await MockAccessScenarios.seed_project_authorization(
                session, is_project_member=True, has_action_grant=False
            )
            for operation, route in [
                ("old-grant", "/v1/projects/{project_id}/grants"),
                ("old-generic", "/v1/original-project-operation"),
            ]:
                session.add(
                    LegacyOperationReservationRow(
                        operation_id=operation,
                        principal_id=seed.principal_id.value,
                        organization_id=seed.organization_id.value,
                        project_id=seed.project_id.value,
                        method="POST",
                        requested_route=route,
                        request_key=operation,
                        request_fingerprint=b"F" * 32,
                        state="replayable",
                        replay_kind="safe_result",
                        expires_at=expiry,
                    )
                )
        run_migrations(temporary_postgres_settings)
        async with database.session() as session:
            grant = await session.get(IdempotencyReservationRow, "old-grant")
            generic = await session.get(IdempotencyReservationRow, "old-generic")
            assert grant is not None and generic is not None
            assert (grant.lookup_authority_family, grant.lookup_action_id) == (
                "project_grant_read",
                "create-access-groups",
            )
            assert (generic.lookup_authority_family, generic.lookup_action_id) == (None, None)
            assert grant.request_fingerprint == generic.request_fingerprint == b"F" * 32
            assert grant.expires_at == generic.expires_at == expiry
    finally:
        await database.shutdown()


@pytest.mark.asyncio
async def test_binding_fields_cannot_be_partially_saved(database: Database) -> None:
    async with database.session() as session, session.begin():
        seed = await MockAccessScenarios.seed_project_authorization(
            session, is_project_member=True, has_action_grant=False
        )
        session.add(
            IdempotencyReservationRow(
                operation_id="original",
                principal_id=seed.principal_id.value,
                organization_id=seed.organization_id.value,
                project_id=seed.project_id.value,
                method="POST",
                requested_route="/v1/original-project-operation",
                request_key="original",
                request_fingerprint=b"F" * 32,
            )
        )
    with pytest.raises(IntegrityError):
        async with database.session() as session, session.begin():
            await session.execute(
                update(IdempotencyReservationRow)
                .where(IdempotencyReservationRow.operation_id == "original")
                .values(lookup_authority_family="project_action_use")
            )
