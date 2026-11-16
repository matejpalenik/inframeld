import os
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select
from tests.support.spending_scenarios import (
    accounting_service,
    call_context,
    price_basis,
    reserve,
    seed_spending_scenario,
)

from inframeld_backend.shared.infrastructure.migrations.migration_runner import (
    BACKEND_ROOT,
    SUPPORTED_SCHEMA_REVISION,
    run_migrations,
)
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.rows.alembic_version_row import AlembicVersionRow
from inframeld_backend.shared.infrastructure.rows.model_call_accounting_row import (
    ModelCallAccountingRow,
)
from inframeld_backend.shared.infrastructure.rows.model_dispatch_issuance_row import (
    ModelDispatchIssuanceRow,
)
from inframeld_backend.shared.infrastructure.settings.database_settings import DatabaseSettings

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1", reason="Requires isolated PostgreSQL"
    ),
]

_PREVIOUS = "0039_document_upload_replay"


async def test_migration_preserves_legacy_approvals_and_refuses_to_drop_an_issuance(
    database: Database, temporary_postgres_settings: DatabaseSettings
) -> None:
    owner = await seed_spending_scenario(database)
    call = call_context(owner)
    reserved = await reserve(database, call, basis=price_basis())
    async with database.session() as session:
        original = await accounting_service(session).approve_accounting(
            call=call, expected_call_revision=reserved.record.revision
        )

    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.attributes["database_settings"] = temporary_postgres_settings
    command.downgrade(config, _PREVIOUS)
    run_migrations(temporary_postgres_settings)

    async with database.session() as session, session.begin():
        legacy = await session.get(ModelCallAccountingRow, call.call_id.value)
        assert legacy is not None and legacy.state == original.record.state
        assert legacy.revision == original.record.revision
        assert await session.get(ModelDispatchIssuanceRow, call.call_id.value) is None

        # A retained attribution does not depend on the lifetime of a live job or connection.
        session.add(
            ModelDispatchIssuanceRow(
                call_id=call.call_id.value,
                job_id=uuid4(),
                attempt_number=1,
                fence=uuid4(),
                connection_id=uuid4(),
                access_revision=0,
                credential_revision=1,
                adapter_revision="fixture-adapter",
            )
        )

    with pytest.raises(RuntimeError, match="Retained model dispatch issuance"):
        command.downgrade(config, _PREVIOUS)

    async with database.session() as session:
        assert (
            await session.scalar(select(AlembicVersionRow.version_num)) == SUPPORTED_SCHEMA_REVISION
        )
        assert await session.get(ModelDispatchIssuanceRow, call.call_id.value) is not None
