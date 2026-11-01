"""Exercise lossless upgrade of real 0013 rows through the operator migration path."""

import os
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from tests.support.postgres import database_session
from tests.support.project_metadata_legacy_rows import LegacyProjectRow

from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.repositories.postgres_project_metadata_repository import (
    PostgresProjectMetadataRepository,
)
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.writers.postgres_project_metadata_audit_writer import (
    PostgresProjectMetadataAuditWriter,
)
from inframeld_backend.shared.infrastructure.migrations.migration_runner import (
    BACKEND_ROOT,
    run_migrations,
)
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.settings.database_settings import DatabaseSettings

pytestmark = pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
    reason="Requires PostgreSQL integration services",
)


@pytest.mark.asyncio
@pytest.mark.parametrize("legacy", ["", " ", "a" * 1000, "legacy\x01\nlabel"])
async def test_upgrade_reads_unrestricted_legacy_label_without_allocating_selector(
    temporary_postgres_settings: DatabaseSettings, legacy: str
) -> None:
    settings = temporary_postgres_settings
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.attributes["database_settings"] = settings
    command.upgrade(config, "0013_deletion_status")
    organization_id, project_id = OrganizationId(uuid4()), ProjectId(uuid4())
    with database_session(settings) as session, session.begin():
        session.add(OrganizationRow(id=organization_id.value, name="Support"))
        session.flush()
        session.add(
            LegacyProjectRow(
                id=project_id.value,
                organization_id=organization_id.value,
                name=legacy,
                status="active",
            )
        )
    run_migrations(settings)
    database = Database(settings)
    try:
        await database.startup()
        async with database.session() as session, session.begin():
            metadata = await PostgresProjectMetadataRepository(
                session, PostgresProjectMetadataAuditWriter(session)
            ).get(organization_id=organization_id, project_id=project_id)
            assert metadata.display_name == legacy
            assert metadata.name is None
            assert metadata.revision == 0
    finally:
        await database.shutdown()


@pytest.mark.asyncio
async def test_upgrade_preserves_original_completed_recovery_receipt_and_replay(
    temporary_postgres_settings: DatabaseSettings,
) -> None:
    from datetime import UTC, datetime

    from sqlalchemy import select

    from inframeld_backend.access.application.commands.resume_identity_recovery_cleanup_command import (
        ResumeIdentityRecoveryCleanupCommand,
    )
    from inframeld_backend.access.application.enums.identity_recovery_event_kind import (
        IdentityRecoveryEventKind,
    )
    from inframeld_backend.access.application.services.identity_recovery_cleanup_resume_service import (
        IdentityRecoveryCleanupResumeService,
    )
    from inframeld_backend.access.domain.enums.identity_recovery_cleanup_state import (
        IdentityRecoveryCleanupState,
    )
    from inframeld_backend.access.infrastructure.readers.postgres_identity_recovery_cleanup_resume_facts_reader import (
        PostgresIdentityRecoveryCleanupResumeFactsReader,
    )
    from inframeld_backend.access.infrastructure.readers.postgres_identity_recovery_completion_facts_reader import (
        PostgresIdentityRecoveryCompletionFactsReader,
    )
    from inframeld_backend.access.infrastructure.resources.sqlalchemy_recovery_transaction_manager import (
        SqlAlchemyRecoveryTransactionManager,
    )
    from inframeld_backend.access.infrastructure.rows.host_maintenance_receipt_row import (
        HostMaintenanceReceiptRow,
    )
    from inframeld_backend.access.infrastructure.rows.human_credential_version_row import (
        HumanCredentialVersionRow,
    )
    from inframeld_backend.access.infrastructure.rows.identity_recovery_admission_row import (
        IdentityRecoveryAdmissionRow,
    )
    from inframeld_backend.access.infrastructure.writers.postgres_identity_recovery_cleanup_resume_writer import (
        PostgresIdentityRecoveryCleanupResumeWriter,
    )
    from inframeld_backend.shared.application.value_objects.operation_id import OperationId
    from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
    from inframeld_backend.shared.infrastructure.rows.installation_identity_row import (
        InstallationIdentityRow,
    )

    settings = temporary_postgres_settings
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.attributes["database_settings"] = settings
    command.upgrade(config, "0013_deletion_status")
    at = datetime(2026, 10, 1, 12, 30, 45, 123456, tzinfo=UTC)
    subject, flow = str(uuid4()), uuid4()
    with database_session(settings) as session, session.begin():
        installed = session.scalar(select(InstallationIdentityRow.installation_id))
        assert installed is not None
        admission = IdentityRecoveryAdmissionRow(
            operation_id="legacy-recovery-operation",
            installation_id=installed,
            authority="kratos:legacy",
            subject=subject,
            flow_id=flow,
            event_kind=IdentityRecoveryEventKind.RECOVERY,
        )
        admission.kratos_cleanup_state = IdentityRecoveryCleanupState.CONFIRMED
        admission.hydra_cleanup_state = IdentityRecoveryCleanupState.CONFIRMED
        admission.released_at = at
        session.add(admission)
        session.add(
            HumanCredentialVersionRow(
                installation_id=installed,
                authority="kratos:legacy",
                subject=subject,
                version=2,
            )
        )
        session.flush()
        session.add(
            HostMaintenanceReceiptRow(
                installation_id=installed,
                operator_request_id="legacy-operator-operation",
                mode="resume-recovery-cleanup",
                authority="kratos:legacy",
                subject=subject,
                recovery_operation_id="legacy-recovery-operation",
                operator_label="Original operator",
                reason="Original reviewed reason",
                authorized_at=at,
                outcome="already-completed",
                released=True,
                run_id=None,
                deadline=None,
            )
        )
    run_migrations(settings)
    database = Database(settings)
    try:
        await database.startup()
        request = ResumeIdentityRecoveryCleanupCommand(
            InstallationId(installed),
            OperationId("legacy-operator-operation"),
            OperationId("legacy-recovery-operation"),
            "Original operator",
            "Original reviewed reason",
        )
        async with database.session() as session, session.begin():
            receipt = await PostgresIdentityRecoveryCleanupResumeFactsReader(session).receipt(
                installation_id=request.expected_installation_id,
                operation_id=request.operation_id,
            )
            assert receipt is not None and receipt.command == request
            assert receipt.authorized_at == at
            assert receipt.result.outcome.value == "already-completed"
            assert (
                receipt.result.released
                and receipt.result.run_id is None
                and receipt.result.deadline is None
            )
            row = await session.get(
                HostMaintenanceReceiptRow, (installed, request.operation_id.value)
            )
            assert row is not None and (row.authority, row.subject, row.recovery_operation_id) == (
                "kratos:legacy",
                subject,
                "legacy-recovery-operation",
            )
        async with database.session() as session:
            replay = await IdentityRecoveryCleanupResumeService(
                SqlAlchemyRecoveryTransactionManager(session),
                PostgresIdentityRecoveryCleanupResumeFactsReader(session),
                PostgresIdentityRecoveryCompletionFactsReader(session),
                PostgresIdentityRecoveryCleanupResumeWriter(session),
            ).resume(command=request)
        assert replay == receipt.result
    finally:
        await database.shutdown()
