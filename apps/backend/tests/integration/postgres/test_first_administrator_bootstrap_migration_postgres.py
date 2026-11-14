"""Preserve pre-admission metadata and refuse to erase an accepted first claim."""

import os
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, select
from tests.support.first_administrator_bootstrap_scenarios import (
    bootstrap_scenario,
    bootstrap_service,
)
from tests.support.postgres import database_connection, database_session

from inframeld_backend.access.application.enums.identity_recovery_event_kind import (
    IdentityRecoveryEventKind,
)
from inframeld_backend.access.infrastructure.rows.first_administrator_bootstrap_receipt_row import (
    FirstAdministratorBootstrapReceiptRow,
)
from inframeld_backend.access.infrastructure.rows.human_credential_version_row import (
    HumanCredentialVersionRow,
)
from inframeld_backend.access.infrastructure.rows.identity_recovery_admission_row import (
    IdentityRecoveryAdmissionRow,
)
from inframeld_backend.shared.infrastructure.migrations.migration_runner import (
    BACKEND_ROOT,
    SUPPORTED_SCHEMA_REVISION,
    run_migrations,
)
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.rows.alembic_version_row import AlembicVersionRow
from inframeld_backend.shared.infrastructure.rows.artifact_storage_capacity_row import (
    ArtifactStorageCapacityRow,
)
from inframeld_backend.shared.infrastructure.rows.installation_identity_row import (
    InstallationIdentityRow,
)
from inframeld_backend.shared.infrastructure.settings.database_settings import DatabaseSettings

pytestmark = pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
    reason="Requires PostgreSQL integration services",
)


@pytest.mark.asyncio
async def test_upgrade_and_empty_claim_roundtrip_preserve_existing_identity_recovery_and_artifact_metadata(
    temporary_postgres_settings: DatabaseSettings,
) -> None:
    settings = temporary_postgres_settings
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.attributes["database_settings"] = settings
    command.upgrade(config, "0015_artifact_allocation")
    subject, flow = str(uuid4()), uuid4()
    with database_session(settings) as session, session.begin():
        installed = session.scalar(select(InstallationIdentityRow.installation_id))
        assert installed is not None
        session.add_all(
            [
                HumanCredentialVersionRow(
                    installation_id=installed, authority="kratos:test", subject=subject, version=7
                ),
                IdentityRecoveryAdmissionRow(
                    operation_id="retained-recovery",
                    installation_id=installed,
                    authority="kratos:test",
                    subject=subject,
                    flow_id=flow,
                    event_kind=IdentityRecoveryEventKind.RECOVERY,
                ),
                ArtifactStorageCapacityRow(
                    installation_id=installed, protected_reserved_bytes=128, occupied_bytes=91
                ),
            ]
        )
    for downgrade in (False, True, False):
        if downgrade:
            command.downgrade(config, "0015_artifact_allocation")
        else:
            run_migrations(settings)
        with database_session(settings) as session:
            capacity = session.get(ArtifactStorageCapacityRow, installed)
            assert capacity is not None
            assert capacity.protected_reserved_bytes == 128
            assert capacity.occupied_bytes == 91
    with database_connection(settings) as connection:
        assert "first_administrator_bootstrap_receipts" in inspect(connection).get_table_names()
    with database_session(settings) as session:
        assert session.scalar(select(InstallationIdentityRow.installation_id)) == installed
        version = session.get(HumanCredentialVersionRow, (installed, "kratos:test", subject))
        assert version is not None and version.version == 7
        recovery = session.get(IdentityRecoveryAdmissionRow, "retained-recovery")
        assert recovery is not None and recovery.flow_id == flow and recovery.released_at is None
        capacity = session.get(ArtifactStorageCapacityRow, installed)
        assert capacity is not None and capacity.occupied_bytes == 91


@pytest.mark.asyncio
async def test_retained_claim_refuses_downgrade_without_losing_original_typed_result(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
) -> None:
    scenario = await bootstrap_scenario(database)
    async with database.session() as session:
        original = await bootstrap_service(session, scenario.binding).bootstrap(scenario.command)
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.attributes["database_settings"] = temporary_postgres_settings
    with pytest.raises(RuntimeError, match="Retained first-administrator claims"):
        command.downgrade(config, "0015_artifact_allocation")
    async with database.session() as session:
        assert (
            await session.scalar(select(AlembicVersionRow.version_num)) == SUPPORTED_SCHEMA_REVISION
        )
        receipt = await session.get(
            FirstAdministratorBootstrapReceiptRow, original.installation_id.value
        )
        assert receipt is not None and receipt.organization_id == original.organization_id.value
        assert receipt.recipient_id == original.recipient_id.value and receipt.after_revision == 1
    async with database.session() as session:
        replay = await bootstrap_service(session, scenario.binding).bootstrap(scenario.command)
        assert replay == original
