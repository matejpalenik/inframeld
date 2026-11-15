from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from inframeld_backend.access.infrastructure.writers.postgres_artifact_cleanup_audit_writer import (
    PostgresArtifactCleanupAuditWriter,
)
from inframeld_backend.bootstrap.artifact_preparation_composition import create_artifact_preparation
from inframeld_backend.knowledge.application.services.document_upload_service import (
    DocumentUploadService,
)
from inframeld_backend.knowledge.infrastructure.repositories.postgres_document_upload_repository import (
    PostgresDocumentUploadRepository,
)
from inframeld_backend.knowledge.infrastructure.resources.postgres_document_upload_authorizer import (
    PostgresDocumentUploadAuthorizer,
)
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.application.protocols.artifact_capacity_reader import (
    ArtifactCapacityReader,
)
from inframeld_backend.shared.application.services.artifact_allocation_service import (
    ArtifactAllocationService,
)
from inframeld_backend.shared.application.services.artifact_cleanup_admission_service import (
    ArtifactCleanupAdmissionService,
)
from inframeld_backend.shared.infrastructure.repositories.postgres_artifact_attempt_repository import (
    PostgresArtifactAttemptRepository,
)
from inframeld_backend.shared.infrastructure.repositories.postgres_artifact_cleanup_obligation_repository import (
    PostgresArtifactCleanupObligationRepository,
)
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.resources.sqlalchemy_transaction_manager import (
    SqlAlchemyTransactionManager,
)
from inframeld_backend.shared.infrastructure.settings.artifact_staging_settings import (
    ArtifactStagingSettings,
)
from inframeld_backend.shared.infrastructure.settings.artifact_storage_settings import (
    ArtifactStorageSettings,
)
from inframeld_backend.shared.infrastructure.writers.postgres_artifact_cleanup_admission_writer import (
    PostgresArtifactCleanupAdmissionWriter,
)


@asynccontextmanager
async def open_document_upload(
    database: Database,
    staging_settings: ArtifactStagingSettings,
    storage_settings: ArtifactStorageSettings,
    capacity_reader: ArtifactCapacityReader,
) -> AsyncGenerator[DocumentUploadService]:
    """Bind a private upload to real storage and the caller's trusted capacity reader."""
    try:
        preparation = await create_artifact_preparation(
            database, staging_settings, storage_settings
        )
    except OSError as error:
        raise DependencyUnavailableError() from error
    async with database.session() as session:
        transactions = SqlAlchemyTransactionManager(session)
        attempts = PostgresArtifactAttemptRepository(session)
        allocator = ArtifactAllocationService(
            transactions,
            attempts,
            PostgresArtifactCleanupObligationRepository(session),
            ArtifactCleanupAdmissionService(
                PostgresArtifactCleanupAdmissionWriter(session),
                PostgresArtifactCleanupAuditWriter(session),
            ),
            capacity_reader,
        )
        yield DocumentUploadService(
            transactions,
            PostgresDocumentUploadAuthorizer(session),
            PostgresDocumentUploadRepository(session, allocator, attempts),
            preparation,
        )
