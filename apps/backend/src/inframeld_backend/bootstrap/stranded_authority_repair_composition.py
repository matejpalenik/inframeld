from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from functools import partial

from inframeld_backend.access.application.commands.repair_stranded_authority_command import (
    RepairStrandedAuthorityCommand,
)
from inframeld_backend.access.application.protocols.stranded_authority_repairer import (
    StrandedAuthorityRepairer,
)
from inframeld_backend.access.application.services.stranded_authority_fingerprint_service import (
    StrandedAuthorityFingerprintService,
)
from inframeld_backend.access.application.services.stranded_authority_repair_service import (
    StrandedAuthorityRepairService,
)
from inframeld_backend.access.cli.stranded_authority_maintenance_cli import (
    StrandedAuthorityMaintenanceCli,
)
from inframeld_backend.access.infrastructure.readers.postgres_stranded_authority_repair_facts_reader import (
    PostgresStrandedAuthorityRepairFactsReader,
)
from inframeld_backend.access.infrastructure.writers.postgres_project_metadata_audit_writer import (
    PostgresProjectMetadataAuditWriter,
)
from inframeld_backend.access.infrastructure.writers.postgres_stranded_authority_audit_writer import (
    PostgresStrandedAuthorityAuditWriter,
)
from inframeld_backend.access.infrastructure.writers.postgres_stranded_authority_repair_writer import (
    PostgresStrandedAuthorityRepairWriter,
)
from inframeld_backend.bootstrap.access_composition import create_access_components
from inframeld_backend.bootstrap.stranded_authority_maintenance_settings import (
    StrandedAuthorityMaintenanceSettings,
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
async def open_stranded_authority_repair(
    database: Database, repair_fingerprint_service: StrandedAuthorityFingerprintService
) -> AsyncGenerator[StrandedAuthorityRepairer]:
    async with database.session() as session:
        yield StrandedAuthorityRepairService(
            transaction_manager=SqlAlchemyTransactionManager(session),
            repair_facts_reader=PostgresStrandedAuthorityRepairFactsReader(session),
            repair_writer=PostgresStrandedAuthorityRepairWriter(
                session,
                PostgresStrandedAuthorityAuditWriter(
                    session, PostgresProjectMetadataAuditWriter(session)
                ),
            ),
            repair_fingerprint_service=repair_fingerprint_service,
        )


async def execute_stranded_authority_repair(
    command: RepairStrandedAuthorityCommand, settings: StrandedAuthorityMaintenanceSettings
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
        repair_fingerprint_service = StrandedAuthorityFingerprintService(
            RequestFingerprintService(
                FileRequestFingerprintKeyReader(settings.request_fingerprint.key_file).read()
            )
        )
        return await StrandedAuthorityMaintenanceCli(
            authenticator,
            partial(open_stranded_authority_repair, database, repair_fingerprint_service),
        ).execute(command)
    finally:
        if access is not None:
            for client in (access.kratos_client, access.kratos_admin_client, access.hydra_client):
                if client is not None:
                    client.rest_client.pool_manager.clear()
        await database.shutdown()
