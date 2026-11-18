from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from inframeld_backend.access.application.services.admitted_work_authorization_service import (
    AdmittedWorkAuthorizationService,
)
from inframeld_backend.access.infrastructure.readers.postgres_admitted_work_facts_reader import (
    PostgresAdmittedWorkFactsReader,
)
from inframeld_backend.access.infrastructure.writers.postgres_job_admission_audit_writer import (
    PostgresJobAdmissionAuditWriter,
)
from inframeld_backend.indexing.application.protocols.pdf_parser import PdfParser
from inframeld_backend.indexing.application.services.pipeline_pdf_preparation_job_handler import (
    PipelinePdfPreparationJobHandler,
)
from inframeld_backend.indexing.application.services.sealed_pdf_processing_service import (
    SealedPdfProcessingService,
)
from inframeld_backend.indexing.infrastructure.repositories.postgres_pipeline_pdf_preparation_records import (
    PostgresPipelinePdfPreparationRecords,
)
from inframeld_backend.pipelines.application.services.pipeline_pdf_preparation_admission_service import (
    PipelinePdfPreparationAdmissionService,
)
from inframeld_backend.pipelines.infrastructure.readers.postgres_pipeline_pdf_preparation_facts_reader import (
    PostgresPipelinePdfPreparationFactsReader,
)
from inframeld_backend.shared.application.protocols.artifact_capacity_reader import (
    ArtifactCapacityReader,
)
from inframeld_backend.shared.application.protocols.job_effect_observation_recorder import (
    JobEffectObservationRecorder,
)
from inframeld_backend.shared.application.protocols.retained_history_safety_headroom import (
    RetainedHistorySafetyHeadroom,
)
from inframeld_backend.shared.application.services.idempotency_service import IdempotencyService
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.infrastructure.repositories.postgres_job_store import PostgresJobStore
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.resources.private_artifact_preparation import (
    PrivateArtifactPreparation,
)
from inframeld_backend.shared.infrastructure.resources.private_artifact_staging import (
    PrivateArtifactStaging,
)
from inframeld_backend.shared.infrastructure.resources.s3_artifact_store import S3ArtifactStore
from inframeld_backend.shared.infrastructure.resources.sqlalchemy_transaction_manager import (
    SqlAlchemyTransactionManager,
)
from inframeld_backend.shared.infrastructure.settings.artifact_storage_settings import (
    ArtifactStorageSettings,
)
from inframeld_backend.shared.infrastructure.settings.job_settings import JobSettings
from inframeld_backend.shared.infrastructure.writers.postgres_build_history_reservation_writer import (
    PostgresBuildHistoryReservationWriter,
)
from inframeld_backend.shared.infrastructure.writers.postgres_operation_reservation_writer import (
    PostgresOperationReservationWriter,
)


@asynccontextmanager
async def open_pipeline_pdf_preparation(
    database: Database,
    fingerprints: RequestFingerprintService,
    safety_headroom: RetainedHistorySafetyHeadroom,
) -> AsyncGenerator[PipelinePdfPreparationAdmissionService]:
    """Give private Build admission one session and a verified safety-space gate."""
    async with database.session() as session:
        yield PipelinePdfPreparationAdmissionService(
            transactions=SqlAlchemyTransactionManager(session),
            facts=PostgresPipelinePdfPreparationFactsReader(session),
            authority=AdmittedWorkAuthorizationService(PostgresAdmittedWorkFactsReader(session)),
            idempotency=IdempotencyService(PostgresOperationReservationWriter(session)),
            fingerprints=fingerprints,
            history=PostgresBuildHistoryReservationWriter(session, safety_headroom=safety_headroom),
            jobs=PostgresJobStore(session),
            audit=PostgresJobAdmissionAuditWriter(session),
        )


def create_pipeline_pdf_preparation_handler(
    database: Database,
    *,
    jobs: JobSettings,
    storage: ArtifactStorageSettings,
    staging: PrivateArtifactStaging,
    capacity: ArtifactCapacityReader,
    source_store: S3ArtifactStore,
    parser: PdfParser,
    observations: JobEffectObservationRecorder,
) -> PipelinePdfPreparationJobHandler:
    """Register the ordinary handler when protected parser and storage inputs exist."""
    return PipelinePdfPreparationJobHandler(
        PostgresPipelinePdfPreparationRecords(
            database, capacity, database_seconds=jobs.database_timeout_seconds
        ),
        SealedPdfProcessingService(source_store, parser),
        lambda: PrivateArtifactPreparation(
            staging,
            lambda: S3ArtifactStore(storage, effect_observation_recorder=observations),
        ),
    )
