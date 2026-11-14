from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError

from inframeld_backend.access.application.dtos.application_key_verification_profile_dto import (
    ApplicationKeyVerificationProfileDTO,
)
from inframeld_backend.access.application.protocols.processing_profile_grant_changer import (
    ProcessingProfileGrantChanger,
)
from inframeld_backend.access.application.protocols.processing_profile_grants_reader import (
    ProcessingProfileGrantsReader,
)
from inframeld_backend.access.application.services.processing_profile_grant_change_service import (
    ProcessingProfileGrantChangeService,
)
from inframeld_backend.access.application.services.processing_profile_grants_read_service import (
    ProcessingProfileGrantsReadService,
)
from inframeld_backend.access.infrastructure.repositories.postgres_processing_profile_grant_repository import (
    PostgresProcessingProfileGrantRepository,
)
from inframeld_backend.indexing.application.protocols.processing_profile_creator import (
    ProcessingProfileCreator,
)
from inframeld_backend.indexing.application.protocols.processing_profile_reader import (
    ProcessingProfileReader,
)
from inframeld_backend.indexing.application.services.processing_profile_creation_service import (
    ProcessingProfileCreationService,
)
from inframeld_backend.indexing.application.services.processing_profile_read_service import (
    ProcessingProfileReadService,
)
from inframeld_backend.indexing.infrastructure.repositories.postgres_processing_profile_creation_repository import (
    PostgresProcessingProfileCreationRepository,
)
from inframeld_backend.indexing.infrastructure.repositories.postgres_processing_profile_read_repository import (
    PostgresProcessingProfileReadRepository,
)
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.application.services.idempotency_service import IdempotencyService
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.resources.sqlalchemy_transaction_manager import (
    SqlAlchemyTransactionManager,
)
from inframeld_backend.shared.infrastructure.writers.postgres_operation_reservation_writer import (
    PostgresOperationReservationWriter,
)


@asynccontextmanager
async def open_processing_profile_creation(
    database: Database, fingerprints: RequestFingerprintService
) -> AsyncGenerator[ProcessingProfileCreator]:
    try:
        async with database.session() as session:
            yield ProcessingProfileCreationService(
                PostgresProcessingProfileCreationRepository(session),
                IdempotencyService(PostgresOperationReservationWriter(session)),
                fingerprints,
                transactions=SqlAlchemyTransactionManager(session),
            )
    except (OperationalError, SqlAlchemyTimeoutError):
        raise DependencyUnavailableError() from None


@asynccontextmanager
async def open_processing_profile_read(
    database: Database, application_key_profile: ApplicationKeyVerificationProfileDTO | None
) -> AsyncGenerator[ProcessingProfileReader]:
    try:
        async with database.session() as session:
            yield ProcessingProfileReadService(
                SqlAlchemyTransactionManager(session),
                PostgresProcessingProfileReadRepository(session, application_key_profile),
            )
    except (OperationalError, SqlAlchemyTimeoutError):
        raise DependencyUnavailableError() from None


@asynccontextmanager
async def open_processing_profile_grant_change(
    database: Database, fingerprints: RequestFingerprintService
) -> AsyncGenerator[ProcessingProfileGrantChanger]:
    try:
        async with database.session() as session:
            yield ProcessingProfileGrantChangeService(
                SqlAlchemyTransactionManager(session),
                PostgresProcessingProfileGrantRepository(session),
                IdempotencyService(PostgresOperationReservationWriter(session)),
                fingerprints,
            )
    except (OperationalError, SqlAlchemyTimeoutError):
        raise DependencyUnavailableError() from None


@asynccontextmanager
async def open_processing_profile_grant_read(
    database: Database,
) -> AsyncGenerator[ProcessingProfileGrantsReader]:
    try:
        async with database.session() as session:
            yield ProcessingProfileGrantsReadService(
                SqlAlchemyTransactionManager(session),
                PostgresProcessingProfileGrantRepository(session),
            )
    except (OperationalError, SqlAlchemyTimeoutError):
        raise DependencyUnavailableError() from None
