"""Preserve delivered deletion status, metadata and product replay through allocation upgrade."""

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, inspect, select
from sqlalchemy.exc import IntegrityError
from tests.support.artifact_scenarios import (
    allocate_artifact,
    artifact_scenario,
    seed_artifact_scope,
)
from tests.support.artifact_storage_legacy_rows import LegacyDurableJobRow
from tests.support.postgres import database_connection, database_session

from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.access.infrastructure.rows.host_maintenance_receipt_row import (
    HostMaintenanceReceiptRow,
)
from inframeld_backend.access.infrastructure.rows.human_credential_version_row import (
    HumanCredentialVersionRow,
)
from inframeld_backend.access.infrastructure.rows.human_identity_link_row import (
    HumanIdentityLinkRow,
)
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_metadata_operation_result_row import (
    ProjectMetadataOperationResultRow,
)
from inframeld_backend.access.infrastructure.rows.project_metadata_repair_receipt_row import (
    ProjectMetadataRepairReceiptRow,
)
from inframeld_backend.access.infrastructure.rows.project_name_reservation_row import (
    ProjectNameReservationRow,
)
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.shared.application.dtos.product_job_binding_dto import ProductJobBindingDTO
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.enums.operation_reservation_state import (
    OperationReservationState,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.infrastructure.migrations.migration_runner import (
    BACKEND_ROOT,
    run_migrations,
)
from inframeld_backend.shared.infrastructure.repositories.postgres_job_store import PostgresJobStore
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.rows.alembic_version_row import AlembicVersionRow
from inframeld_backend.shared.infrastructure.rows.artifact_attempt_row import ArtifactAttemptRow
from inframeld_backend.shared.infrastructure.rows.artifact_cleanup_obligation_row import (
    ArtifactCleanupObligationRow,
)
from inframeld_backend.shared.infrastructure.rows.artifact_cleanup_target_row import (
    ArtifactCleanupTargetRow,
)
from inframeld_backend.shared.infrastructure.rows.artifact_staging_reservation_row import (
    ArtifactStagingReservationRow,
)
from inframeld_backend.shared.infrastructure.rows.artifact_storage_capacity_row import (
    ArtifactStorageCapacityRow,
)
from inframeld_backend.shared.infrastructure.rows.deletion_status_binding_row import (
    DeletionStatusBindingRow,
)
from inframeld_backend.shared.infrastructure.rows.deletion_status_observation_row import (
    DeletionStatusObservationRow,
)
from inframeld_backend.shared.infrastructure.rows.durable_job_row import DurableJobRow
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)
from inframeld_backend.shared.infrastructure.rows.installation_identity_row import (
    InstallationIdentityRow,
)
from inframeld_backend.shared.infrastructure.settings.database_settings import DatabaseSettings

pytestmark = pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
    reason="Requires isolated PostgreSQL integration services",
)


@pytest.mark.asyncio
@pytest.mark.parametrize("legacy", ["", "legacy\x01\n" + "x" * 1000])
@pytest.mark.parametrize("selector", [None, "support"])
@pytest.mark.parametrize("roundtrip", [False, True], ids=["forward", "empty_roundtrip"])
async def test_artifact_upgrade_preserves_0014_metadata_deletion_status_product_job_and_typed_repair(
    temporary_postgres_settings: DatabaseSettings,
    legacy: str,
    selector: str | None,
    roundtrip: bool,
) -> None:
    settings = temporary_postgres_settings
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.attributes["database_settings"] = settings
    command.upgrade(config, "0014_project_metadata")
    organization, project, principal, job_id, request_id = (uuid4() for _ in range(5))
    now = datetime.now(UTC)
    expiry = now + timedelta(hours=24)
    unfinished = uuid4()
    with database_session(settings) as session, session.begin():
        installation = session.scalar(select(InstallationIdentityRow.installation_id))
        assert installation is not None
        session.add(OrganizationRow(id=organization, name="Support"))
        session.flush()
        row = ProjectRow(
            id=project,
            organization_id=organization,
            name=legacy,
            resource_name=selector,
            status=ProjectStatus.ACTIVE,
        )
        row.metadata_revision = 7
        row.access_revision = 4
        session.add_all(
            [
                row,
                PrincipalRow(
                    id=principal,
                    organization_id=organization,
                    kind=PrincipalKind.HUMAN,
                    status=PrincipalStatus.ACTIVE,
                    display_name="Alice",
                ),
            ]
        )
        session.flush()
        session.add_all(
            [
                HumanIdentityLinkRow(
                    authority="kratos:test",
                    subject="alice",
                    organization_id=organization,
                    principal_id=principal,
                    principal_kind=PrincipalKind.HUMAN,
                ),
                HumanCredentialVersionRow(
                    installation_id=installation,
                    authority="kratos:test",
                    subject="alice",
                    version=1,
                ),
            ]
        )
        if selector is not None:
            session.add(
                ProjectNameReservationRow(
                    organization_id=organization,
                    name=selector,
                    project_id=project,
                    binding_revision=7,
                    retired=False,
                )
            )
        session.add(
            ProjectNameReservationRow(
                organization_id=organization,
                name="retired-support",
                project_id=project,
                binding_revision=6,
                retired=True,
            )
        )
        for operation_id, replay in [
            ("original-metadata", OperationReplayKind.SAFE_RESULT),
            ("original-job", OperationReplayKind.ASYNC_JOB),
        ]:
            reservation = IdempotencyReservationRow(
                operation_id=operation_id,
                principal_id=principal,
                organization_id=organization,
                project_id=project,
                method="PATCH" if replay is OperationReplayKind.SAFE_RESULT else "POST",
                requested_route="/test/projects/{project_id}/metadata"
                if replay is OperationReplayKind.SAFE_RESULT
                else "/test/projects/{project_id}/feedback-reports",
                request_key=operation_id,
                request_fingerprint=b"F" * 32,
                replay_kind=replay,
                expires_at=expiry if replay is OperationReplayKind.SAFE_RESULT else None,
            )
            reservation.state = OperationReservationState.REPLAYABLE
            session.add(reservation)
        session.flush()
        session.add(
            ProjectMetadataOperationResultRow(
                operation_id="original-metadata",
                organization_id=organization,
                project_id=project,
                name=selector,
                display_name=legacy,
                metadata_revision=7,
            )
        )
        session.add(
            LegacyDurableJobRow(
                id=job_id,
                operation_id="original-job",
                request_id=request_id,
                installation_id=installation,
                principal_id=principal,
                principal_kind="human",
                organization_id=organization,
                project_id=project,
                action_id="inspect-feedback",
                admitted_at=now,
                queued_deadline=expiry,
                due_at=now,
                human_authority="kratos:test",
                human_subject="alice",
                human_version=1,
                checkpoint=b"original-progress",
            )
        )
        session.add(
            DeletionStatusBindingRow(
                operation_id="original-deletion",
                request_id=request_id,
                installation_id=installation,
                organization_id=organization,
                project_id=project,
                initiator_principal_id=principal,
                method="DELETE",
                requested_route="/v1/projects/{project_id}",
                request_key="original-deletion",
                request_fingerprint=b"D" * 32,
                authority_family="project_action_use",
                action_id="delete-project",
                retention_days=30,
                retention_policy_version="original-policy",
            )
        )
        session.flush()
        session.add(
            DeletionStatusObservationRow(
                operation_id="original-deletion",
                owner_revision=7,
                job_status="failed",
                admission_confirmed=True,
                access_blocked=True,
                application_shutdown_complete=True,
                physical_cleanup_complete=False,
                unfinished_obligation_id=unfinished,
                unfinished_operation_id="original-deletion",
                unfinished_installation_id=installation,
                unfinished_organization_id=organization,
                unfinished_project_id=project,
                unfinished_initiator_principal_id=principal,
                unfinished_observed_at=now,
                unfinished_source_revision=7,
            )
        )
        session.add(
            HostMaintenanceReceiptRow(
                installation_id=installation,
                operator_request_id="original-repair",
                authority="kratos:test",
                subject="operator",
                mode="repair-stranded-authority",
                recovery_operation_id=None,
                operator_label="Operator",
                reason="Restore original authority",
                authorized_at=now,
                outcome="repaired",
                released=None,
                run_id=None,
                deadline=None,
            )
        )
        session.flush()
        session.add(
            ProjectMetadataRepairReceiptRow(
                installation_id=installation,
                operator_request_id="original-repair",
                organization_id=organization,
                project_id=project,
                recipient_id=principal,
                expected_identity_id=uuid4(),
                request_fingerprint=b"R" * 32,
                before_revision=3,
                after_revision=4,
            )
        )
    run_migrations(settings)
    if roundtrip:
        # No artifact ownership exists. Product jobs, retained deletion status
        # and metadata must survive removal and reinstallation of this schema.
        command.downgrade(config, "0014_project_metadata")
        with database_connection(settings) as connection:
            assert (
                connection.scalar(select(AlembicVersionRow.version_num)) == "0014_project_metadata"
            )
            for table in (
                "artifact_storage_capacity",
                "artifact_attempts",
                "artifact_staging_reservations",
                "artifact_cleanup_obligations",
                "artifact_cleanup_targets",
            ):
                assert not inspect(connection).has_table(table, schema="public")
        with database_session(settings) as session:
            product_job = session.get(LegacyDurableJobRow, job_id)
            deletion = session.get(DeletionStatusObservationRow, "original-deletion")
            metadata = session.get(ProjectMetadataOperationResultRow, "original-metadata")
            assert product_job is not None and product_job.checkpoint == b"original-progress"
            assert deletion is not None and deletion.unfinished_obligation_id == unfinished
            assert metadata is not None and metadata.metadata_revision == 7
        run_migrations(settings)

    database = Database(settings)
    try:
        await database.startup()
        async with database.session() as session:
            assert (
                await session.scalar(select(AlembicVersionRow.version_num))
                == "0026_access_action_grant_results"
            )
            snapshot = await PostgresJobStore(session).find(OperationId("original-job"))
            assert snapshot is not None and snapshot.job_id.value == job_id
            assert isinstance(snapshot.binding, ProductJobBindingDTO)
            assert snapshot.binding.request_id.value == request_id
            assert snapshot.checkpoint == b"original-progress" and snapshot.attempt == 0
            saved_job = await session.get(DurableJobRow, job_id)
            assert (
                saved_job is not None
                and saved_job.binding_kind == "product"
                and saved_job.cleanup_obligation_id is None
            )
            saved = await session.get(ProjectRow, project)
            assert saved is not None and (
                saved.name,
                saved.resource_name,
                saved.metadata_revision,
                saved.access_revision,
            ) == (legacy, selector, 7, 4)
            result = await session.get(ProjectMetadataOperationResultRow, "original-metadata")
            assert result is not None and (
                result.display_name,
                result.name,
                result.metadata_revision,
            ) == (legacy, selector, 7)
            original = await session.get(IdempotencyReservationRow, "original-metadata")
            assert (
                original is not None
                and original.replay_kind is OperationReplayKind.SAFE_RESULT
                and original.expires_at == expiry
            )
            repair = await session.get(
                ProjectMetadataRepairReceiptRow, (installation, "original-repair")
            )
            receipt = await session.get(
                HostMaintenanceReceiptRow, (installation, "original-repair")
            )
            assert repair is not None and (repair.before_revision, repair.after_revision) == (3, 4)
            assert (
                receipt is not None
                and receipt.mode == "repair-stranded-authority"
                and receipt.recovery_operation_id is None
                and receipt.released is None
                and receipt.run_id is None
            )
            retired = await session.get(
                ProjectNameReservationRow, (organization, "retired-support")
            )
            assert retired is not None and retired.retired
            deletion = await session.get(DeletionStatusBindingRow, "original-deletion")
            observation = await session.get(DeletionStatusObservationRow, "original-deletion")
            assert deletion is not None and observation is not None
            assert (
                deletion.request_id,
                deletion.installation_id,
                deletion.organization_id,
                deletion.project_id,
                deletion.initiator_principal_id,
                deletion.request_fingerprint,
                deletion.retention_days,
                deletion.retention_policy_version,
            ) == (
                request_id,
                installation,
                organization,
                project,
                principal,
                b"D" * 32,
                30,
                "original-policy",
            )
            assert (
                observation.owner_revision,
                observation.job_status,
                observation.admission_confirmed,
                observation.access_blocked,
                observation.application_shutdown_complete,
                observation.physical_cleanup_complete,
                observation.unfinished_obligation_id,
                observation.unfinished_operation_id,
                observation.unfinished_installation_id,
                observation.unfinished_organization_id,
                observation.unfinished_project_id,
                observation.unfinished_initiator_principal_id,
                observation.unfinished_observed_at,
                observation.unfinished_source_revision,
                observation.retention_started_at,
                observation.expires_at,
            ) == (
                7,
                "failed",
                True,
                True,
                True,
                False,
                unfinished,
                "original-deletion",
                installation,
                organization,
                project,
                principal,
                now,
                7,
                None,
                None,
            )
        # The scoped metadata FK must remain effective after the new migration.
        async with database.session() as session, session.begin():
            result = await session.get(ProjectMetadataOperationResultRow, "original-metadata")
            assert result is not None
            with pytest.raises(IntegrityError):
                async with session.begin_nested():
                    result.project_id = uuid4()
                    await session.flush()
    finally:
        await database.shutdown()


@pytest.mark.asyncio
async def test_retained_artifact_ownership_refuses_downgrade_without_changing_state(
    temporary_postgres_settings: DatabaseSettings,
) -> None:
    settings = temporary_postgres_settings
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.attributes["database_settings"] = settings
    run_migrations(settings)
    database = Database(settings)
    try:
        await database.startup()
        scenario = artifact_scenario(await seed_artifact_scope(database))
        original = await allocate_artifact(database, scenario)
        with pytest.raises(
            RuntimeError, match="Retained artifact ownership prevents this downgrade"
        ):
            command.downgrade(config, "0014_project_metadata")

        async with database.session() as session:
            assert (
                await session.scalar(select(AlembicVersionRow.version_num))
                == "0026_access_action_grant_results"
            )
            attempt = await session.get(ArtifactAttemptRow, scenario.attempt_id.value)
            reservation = await session.get(
                ArtifactStagingReservationRow, scenario.reservation_id.value
            )
            obligation = await session.get(
                ArtifactCleanupObligationRow, scenario.obligation_id.value
            )
            job = await session.get(DurableJobRow, original.cleanup_job_id.value)
            ledger = await session.get(
                ArtifactStorageCapacityRow, scenario.scope.installation_id.value
            )
            assert attempt is not None and (
                attempt.artifact_id,
                attempt.installation_id,
                attempt.organization_id,
                attempt.project_id,
                attempt.state,
                attempt.length,
                attempt.digest,
            ) == (
                scenario.artifact_id.value,
                scenario.scope.installation_id.value,
                scenario.scope.organization_id.value,
                scenario.scope.project_id.value,
                "allocated",
                None,
                None,
            )
            assert reservation is not None and (
                reservation.attempt_id,
                reservation.limit_bytes,
                reservation.local_reserved_bytes,
                reservation.remote_reserved_bytes,
                reservation.expires_at,
                reservation.released,
                reservation.staging_removed,
            ) == (
                scenario.attempt_id.value,
                25 * 1024**2,
                25 * 1024**2,
                25 * 1024**2,
                original.reservation.expires_at,
                False,
                False,
            )
            assert obligation is not None and (
                obligation.staging_reservation_id,
                obligation.origin_attempt_id,
                obligation.request_id,
                obligation.transfer_deadline,
                obligation.physically_complete,
            ) == (
                scenario.reservation_id.value,
                scenario.attempt_id.value,
                scenario.origin.request_id.value,
                original.reservation.expires_at,
                False,
            )
            assert job is not None and (
                job.binding_kind,
                job.cleanup_obligation_id,
                job.status,
                job.attempt_count,
            ) == ("artifact_cleanup", scenario.obligation_id.value, "queued", 0)
            assert ledger is not None and (
                ledger.spool_reserved_bytes,
                ledger.protected_reserved_bytes,
                ledger.occupied_bytes,
            ) == (25 * 1024**2, 50 * 1024**2, 0)
            for model in (
                ArtifactAttemptRow,
                ArtifactStagingReservationRow,
                ArtifactCleanupObligationRow,
                ArtifactCleanupTargetRow,
                DurableJobRow,
                AccessAuditEventRow,
            ):
                assert await session.scalar(select(func.count()).select_from(model)) == 1
            assert (
                await session.scalar(select(func.count()).select_from(IdempotencyReservationRow))
                == 0
            )

        replay = await allocate_artifact(database, scenario)
        assert replay.cleanup_binding == original.cleanup_binding
        assert replay.cleanup_job_id == original.cleanup_job_id
        assert replay.reservation.expires_at == original.reservation.expires_at
        async with database.session() as session:
            assert await session.scalar(select(func.count()).select_from(AccessAuditEventRow)) == 1
    finally:
        await database.shutdown()
