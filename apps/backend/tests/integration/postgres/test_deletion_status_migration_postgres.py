"""Qualify retained status storage through the real operator migration chain."""

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from tests.support.deletion_status_scenarios import (
    DeletionStatusSeedDTO,
    MockDeletionStatusScenarios,
)
from tests.support.postgres import database_connection
from tests.support.project_metadata_legacy_rows import LegacyProjectRow

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.browser_session_authentication_dto import (
    BrowserSessionAuthenticationDTO,
)
from inframeld_backend.access.application.dtos.project_action_authorization_dto import (
    ProjectActionAuthorizationDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.repositories.postgres_project_metadata_repository import (
    PostgresProjectMetadataRepository,
)
from inframeld_backend.access.infrastructure.rows.human_credential_version_row import (
    HumanCredentialVersionRow,
)
from inframeld_backend.access.infrastructure.rows.human_identity_link_row import (
    HumanIdentityLinkRow,
)
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_membership_row import ProjectMembershipRow
from inframeld_backend.access.infrastructure.writers.postgres_project_metadata_audit_writer import (
    PostgresProjectMetadataAuditWriter,
)
from inframeld_backend.shared.application.dtos.new_operation_reservation_dto import (
    NewOperationReservationDTO,
)
from inframeld_backend.shared.application.dtos.operation_admission_context_dto import (
    OperationAdmissionContextDTO,
)
from inframeld_backend.shared.application.dtos.operation_reservation_request_dto import (
    OperationReservationRequestDTO,
)
from inframeld_backend.shared.application.enums.operation_lookup_authority_family import (
    OperationLookupAuthorityFamily,
)
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.services.idempotency_service import IdempotencyService
from inframeld_backend.shared.application.value_objects.deletion_status_retention_profile import (
    DeletionStatusRetentionProfile,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.operation_lookup_authority import (
    OperationLookupAuthority,
)
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)
from inframeld_backend.shared.application.value_objects.request_id import RequestId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.infrastructure.migrations.migration_runner import (
    BACKEND_ROOT,
    run_migrations,
)
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.rows.alembic_version_row import AlembicVersionRow
from inframeld_backend.shared.infrastructure.rows.deletion_status_binding_row import (
    DeletionStatusBindingRow,
)
from inframeld_backend.shared.infrastructure.rows.deletion_status_observation_row import (
    DeletionStatusObservationRow,
)
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)
from inframeld_backend.shared.infrastructure.rows.installation_identity_row import (
    InstallationIdentityRow,
)
from inframeld_backend.shared.infrastructure.settings.database_settings import DatabaseSettings
from inframeld_backend.shared.infrastructure.writers.postgres_operation_reservation_writer import (
    PostgresOperationReservationWriter,
)

pytestmark = pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
    reason="Requires PostgreSQL integration services",
)


async def _seed_legacy_request(session: AsyncSession) -> DeletionStatusSeedDTO:
    """Reserve real original work using only columns present before Project metadata."""
    organization, principal, project = (
        OrganizationId(uuid4()),
        PrincipalId(uuid4()),
        ProjectId(uuid4()),
    )
    identity = VerifiedHumanIdentityDTO(
        IdentityAuthority("kratos:migration"), IdentitySubject(str(uuid4()))
    )
    session.add(OrganizationRow(id=organization.value, name="Support"))
    await session.flush()
    session.add_all(
        [
            PrincipalRow(
                id=principal.value,
                organization_id=organization.value,
                kind=PrincipalKind.HUMAN,
                status=PrincipalStatus.ACTIVE,
                display_name="Alice",
            ),
            LegacyProjectRow(
                id=project.value,
                organization_id=organization.value,
                name="Legacy Support",
                status="active",
            ),
        ]
    )
    await session.flush()
    session.add(
        HumanIdentityLinkRow(
            authority=identity.authority.value,
            subject=identity.subject.value,
            organization_id=organization.value,
            principal_id=principal.value,
            principal_kind=PrincipalKind.HUMAN,
        )
    )
    await session.flush()
    installed = (await session.scalars(select(InstallationIdentityRow.installation_id))).one()
    session.add_all(
        [
            ProjectMembershipRow(
                project_id=project.value,
                principal_id=principal.value,
                organization_id=organization.value,
                principal_kind=PrincipalKind.HUMAN,
            ),
            HumanCredentialVersionRow(
                installation_id=installed,
                authority=identity.authority.value,
                subject=identity.subject.value,
                version=1,
            ),
        ]
    )
    await session.flush()
    access = AccessContextDTO(principal, BrowserSessionAuthenticationDTO(identity))
    authority = OperationLookupAuthority(
        OperationLookupAuthorityFamily.PROJECT_ACTION_USE, ActionId("delete-project")
    )
    request = OperationReservationRequestDTO(
        principal_id=principal,
        organization_id=organization,
        project_id=project,
        method="DELETE",
        requested_route="/v1/projects/{project_id}",
        key=IdempotencyKey(str(uuid4())),
        fingerprint=b"F" * 32,
        lookup_authority=authority,
    )
    reservation = await IdempotencyService(
        PostgresOperationReservationWriter(session)
    ).find_or_reserve(
        context=OperationAdmissionContextDTO(request.method, request.requested_route, request.key),
        access=access,
        authorization=ProjectActionAuthorizationDTO(organization, project),
        fingerprint=RequestFingerprint(request.fingerprint),
        expected_replay_kind=OperationReplayKind.ASYNC_JOB,
        lookup_authority=authority,
    )
    assert isinstance(reservation, NewOperationReservationDTO)
    return DeletionStatusSeedDTO(
        access, request, reservation, RequestId(uuid4()), InstallationId(installed), identity
    )


@pytest.mark.parametrize("table_name", ["deletion_status_bindings", "deletion_status_observations"])
def test_migration_installs_retained_status_storage(
    temporary_postgres_settings: DatabaseSettings, table_name: str
) -> None:
    """Install both retained records rather than relying on a test-only schema."""
    run_migrations(temporary_postgres_settings)

    with database_connection(temporary_postgres_settings) as connection:
        assert inspect(connection).has_table(table_name, schema="public"), table_name


@pytest.mark.asyncio
async def test_upgrade_downgrade_and_reupgrade_preserve_original_foundation(
    temporary_postgres_settings: DatabaseSettings,
) -> None:
    """Preserve the original0010/0013 round trip independently of later migrations."""
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    config.attributes["database_settings"] = temporary_postgres_settings
    command.upgrade(config, "0010_durable_jobs")
    database = Database(temporary_postgres_settings)

    try:
        async with database.session() as session, session.begin():
            seed = await _seed_legacy_request(session)

        for revision in (
            "0013_deletion_status",
            "0010_durable_jobs",
            "0013_deletion_status",
        ):
            if revision == "0010_durable_jobs":
                command.downgrade(config, revision)
            else:
                command.upgrade(config, revision)

            with database_connection(temporary_postgres_settings) as connection:
                assert connection.scalar(select(AlembicVersionRow.version_num)) == revision
                for table in ("deletion_status_bindings", "deletion_status_observations"):
                    assert inspect(connection).has_table(table, schema="public") is (
                        revision == "0013_deletion_status"
                    )

            async with database.session() as session:
                original = await session.get(
                    IdempotencyReservationRow, seed.reservation.operation_id.value
                )
                assert original is not None
                assert original.principal_id == seed.request.principal_id.value
                assert original.request_key == seed.request.key.value
                assert original.request_fingerprint == seed.request.fingerprint
                assert await session.scalar(select(InstallationIdentityRow.installation_id)) == (
                    seed.installation_id.value
                )
    finally:
        await database.shutdown()


@pytest.mark.asyncio
async def test_metadata_upgrade_preserves_retained_status_and_original_foundation(
    temporary_postgres_settings: DatabaseSettings,
) -> None:
    """Add metadata above delivered0013 without replacing retained status or original work."""
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    config.attributes["database_settings"] = temporary_postgres_settings
    command.upgrade(config, "0013_deletion_status")
    database = Database(temporary_postgres_settings)
    started = datetime(2030, 1, 1, tzinfo=UTC)
    profile = DeletionStatusRetentionProfile(30)

    try:
        async with database.session() as session, session.begin():
            seed = await _seed_legacy_request(session)
            request = seed.request
            assert request.project_id is not None and request.lookup_authority is not None
            session.add(
                DeletionStatusBindingRow(
                    operation_id=seed.reservation.operation_id.value,
                    request_id=seed.request_id.value,
                    installation_id=seed.installation_id.value,
                    organization_id=request.organization_id.value,
                    project_id=request.project_id.value,
                    initiator_principal_id=request.principal_id.value,
                    method=request.method,
                    requested_route=request.requested_route,
                    request_key=request.key.value,
                    request_fingerprint=request.fingerprint,
                    authority_family=request.lookup_authority.family.value,
                    action_id=request.lookup_authority.action_id.value,
                    retention_days=profile.days,
                    retention_policy_version=profile.policy_version,
                )
            )
            session.add(
                DeletionStatusObservationRow(
                    operation_id=seed.reservation.operation_id.value,
                    owner_revision=7,
                    job_status="succeeded",
                    admission_confirmed=True,
                    access_blocked=True,
                    application_shutdown_complete=True,
                    physical_cleanup_complete=True,
                    retention_started_at=started,
                    expires_at=started + timedelta(days=30),
                )
            )
            await session.flush()

        command.upgrade(config, "0014_project_metadata")

        async with database.session() as session, session.begin():
            binding = await session.get(
                DeletionStatusBindingRow, seed.reservation.operation_id.value
            )
            observation = await session.get(
                DeletionStatusObservationRow, seed.reservation.operation_id.value
            )
            original = await session.get(
                IdempotencyReservationRow, seed.reservation.operation_id.value
            )
            assert binding is not None and observation is not None and original is not None
            assert (
                binding.request_id,
                binding.installation_id,
                binding.organization_id,
                binding.project_id,
                binding.initiator_principal_id,
            ) == (
                seed.request_id.value,
                seed.installation_id.value,
                request.organization_id.value,
                request.project_id.value,
                request.principal_id.value,
            )
            assert (
                binding.method,
                binding.requested_route,
                binding.request_key,
                binding.request_fingerprint,
                binding.authority_family,
                binding.action_id,
            ) == (
                request.method,
                request.requested_route,
                request.key.value,
                request.fingerprint,
                request.lookup_authority.family.value,
                request.lookup_authority.action_id.value,
            )
            assert (binding.retention_days, binding.retention_policy_version) == (
                30,
                profile.policy_version,
            )
            assert (
                observation.owner_revision,
                observation.job_status,
                observation.admission_confirmed,
                observation.access_blocked,
                observation.application_shutdown_complete,
                observation.physical_cleanup_complete,
            ) == (7, "succeeded", True, True, True, True)
            assert observation.retention_started_at == started
            assert observation.expires_at == started + timedelta(days=30)
            assert observation.unfinished_obligation_id is None
            assert (original.principal_id, original.request_key, original.request_fingerprint) == (
                request.principal_id.value,
                request.key.value,
                request.fingerprint,
            )
            assert (
                await session.scalar(select(InstallationIdentityRow.installation_id))
                == seed.installation_id.value
            )
            link = await session.get(
                HumanIdentityLinkRow, (seed.identity.authority.value, seed.identity.subject.value)
            )
            assert link is not None and link.principal_id == request.principal_id.value
            generation = await session.get(
                HumanCredentialVersionRow,
                (
                    seed.installation_id.value,
                    seed.identity.authority.value,
                    seed.identity.subject.value,
                ),
            )
            assert generation is not None and generation.version == 1

            metadata = await PostgresProjectMetadataRepository(
                session, PostgresProjectMetadataAuditWriter(session)
            ).get(organization_id=request.organization_id, project_id=request.project_id)
            assert metadata.display_name == "Legacy Support"
            assert metadata.name is None and metadata.revision == 0
            assert (
                await session.scalar(select(AlembicVersionRow.version_num))
                == "0014_project_metadata"
            )
    finally:
        await database.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize("days", [0, -1, 91])
async def test_schema_rejects_nonpositive_or_excessive_retention_without_changing_capture(
    database: Database, days: int
) -> None:
    async with database.session() as session, session.begin():
        await MockDeletionStatusScenarios.seed_private_binding(session)
    async with database.session() as session:
        with pytest.raises(IntegrityError):
            async with session.begin():
                await session.execute(update(DeletionStatusBindingRow).values(retention_days=days))
        async with session.begin():
            assert await session.scalar(select(DeletionStatusBindingRow.retention_days)) == 30
