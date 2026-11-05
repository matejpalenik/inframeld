from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from functools import partial

from inframeld_backend.access.application.commands.repair_project_metadata_authority_command import (
    RepairProjectMetadataAuthorityCommand,
)
from inframeld_backend.access.application.protocols.project_metadata_repairer import (
    ProjectMetadataRepairer,
)
from inframeld_backend.access.application.services.project_metadata_fingerprint_service import (
    ProjectMetadataFingerprintService,
)
from inframeld_backend.access.application.services.project_metadata_repair_service import (
    ProjectMetadataRepairService,
)
from inframeld_backend.access.cli.project_metadata_maintenance_cli import (
    ProjectMetadataMaintenanceCli,
)
from inframeld_backend.access.infrastructure.readers.postgres_project_metadata_repair_facts_reader import (
    PostgresProjectMetadataRepairFactsReader,
)
from inframeld_backend.access.infrastructure.writers.postgres_project_metadata_audit_writer import (
    PostgresProjectMetadataAuditWriter,
)
from inframeld_backend.access.infrastructure.writers.postgres_project_metadata_repair_writer import (
    PostgresProjectMetadataRepairWriter,
)
from inframeld_backend.bootstrap.access_composition import create_access_components
from inframeld_backend.bootstrap.project_metadata_maintenance_settings import (
    ProjectMetadataMaintenanceSettings,
)
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.infrastructure.readers.file_request_fingerprint_key_reader import (
    FileRequestFingerprintKeyReader,
)
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.resources.sqlalchemy_transaction_manager import (
    SqlAlchemyTransactionManager,
)


@asynccontextmanager
async def open_project_metadata_repair(
    database: Database, fingerprints: ProjectMetadataFingerprintService
) -> AsyncGenerator[ProjectMetadataRepairer]:
    async with database.session() as session:
        yield ProjectMetadataRepairService(
            transaction_manager=SqlAlchemyTransactionManager(session),
            metadata_repair_facts_reader=PostgresProjectMetadataRepairFactsReader(session),
            metadata_repair_writer=PostgresProjectMetadataRepairWriter(
                session, PostgresProjectMetadataAuditWriter(session)
            ),
            metadata_fingerprint_service=fingerprints,
        )


async def execute_project_metadata_repair(
    command: RepairProjectMetadataAuthorityCommand, settings: ProjectMetadataMaintenanceSettings
) -> dict[str, object]:
    database = Database(settings.database)
    access = None
    try:
        await database.startup()
        access = create_access_components(
            settings.kratos,
            settings.hydra,
            database,
            human_authentication_settings=settings.human_authentication,
        )
        authenticator = access.access_token_authenticator
        if authenticator is None:
            raise DependencyUnavailableError("Recipient verification is unavailable.")
        fingerprints = ProjectMetadataFingerprintService(
            RequestFingerprintService(
                FileRequestFingerprintKeyReader(settings.request_fingerprint.key_file).read()
            )
        )
        return await ProjectMetadataMaintenanceCli(
            authenticator, partial(open_project_metadata_repair, database, fingerprints)
        ).execute(command)
    finally:
        if access is not None:
            for client in (access.kratos_client, access.kratos_admin_client, access.hydra_client):
                if client is not None:
                    client.rest_client.pool_manager.clear()
        await database.shutdown()
