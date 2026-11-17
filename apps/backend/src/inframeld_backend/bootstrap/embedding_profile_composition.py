from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError

from inframeld_backend.access.application.dtos.application_key_verification_profile_dto import (
    ApplicationKeyVerificationProfileDTO,
)
from inframeld_backend.access.domain.policies.model_connection_destination_policy import (
    ModelConnectionDestinationPolicy,
)
from inframeld_backend.access.infrastructure.settings.model_connection_destination_settings import (
    ModelConnectionDestinationSettings,
)
from inframeld_backend.indexing.application.protocols.embedding_profile_creator import (
    EmbeddingProfileCreator,
)
from inframeld_backend.indexing.application.protocols.embedding_profile_reader import (
    EmbeddingProfileReader,
)
from inframeld_backend.indexing.application.services.embedding_profile_creation_service import (
    EmbeddingProfileCreationService,
)
from inframeld_backend.indexing.application.services.embedding_profile_read_service import (
    EmbeddingProfileReadService,
)
from inframeld_backend.indexing.infrastructure.repositories.postgres_embedding_profile_creation_repository import (
    PostgresEmbeddingProfileCreationRepository,
)
from inframeld_backend.indexing.infrastructure.repositories.postgres_embedding_profile_read_repository import (
    PostgresEmbeddingProfileReadRepository,
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
async def open_embedding_profile_creation(
    database: Database,
    fingerprints: RequestFingerprintService,
    destinations: ModelConnectionDestinationSettings,
) -> AsyncGenerator[EmbeddingProfileCreator]:
    try:
        async with database.session() as session:
            yield EmbeddingProfileCreationService(
                PostgresEmbeddingProfileCreationRepository(session),
                IdempotencyService(PostgresOperationReservationWriter(session)),
                fingerprints,
                transactions=SqlAlchemyTransactionManager(session),
                official_destinations=ModelConnectionDestinationPolicy(
                    https_base_urls=destinations.https_base_urls
                ),
            )
    except (OperationalError, SqlAlchemyTimeoutError):
        raise DependencyUnavailableError() from None


@asynccontextmanager
async def open_embedding_profile_read(
    database: Database, application_key_profile: ApplicationKeyVerificationProfileDTO | None
) -> AsyncGenerator[EmbeddingProfileReader]:
    try:
        async with database.session() as session:
            yield EmbeddingProfileReadService(
                SqlAlchemyTransactionManager(session),
                PostgresEmbeddingProfileReadRepository(session, application_key_profile),
            )
    except (OperationalError, SqlAlchemyTimeoutError):
        raise DependencyUnavailableError() from None
