from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from hashlib import sha256

from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError

from inframeld_backend.access.application.dtos.application_key_verification_profile_dto import (
    ApplicationKeyVerificationProfileDTO,
)
from inframeld_backend.access.application.protocols.model_connection_creator import (
    ModelConnectionCreator,
)
from inframeld_backend.access.application.protocols.model_connection_grant_changer import (
    ModelConnectionGrantChanger,
)
from inframeld_backend.access.application.protocols.model_connection_grants_reader import (
    ModelConnectionGrantsReader,
)
from inframeld_backend.access.application.protocols.model_connection_reader import (
    ModelConnectionReader,
)
from inframeld_backend.access.application.services.model_connection_creation_service import (
    ModelConnectionCreationService,
)
from inframeld_backend.access.application.services.model_connection_credential_service import (
    ModelConnectionCredentialService,
)
from inframeld_backend.access.application.services.model_connection_grant_change_service import (
    ModelConnectionGrantChangeService,
)
from inframeld_backend.access.application.services.model_connection_grants_read_service import (
    ModelConnectionGrantsReadService,
)
from inframeld_backend.access.application.services.model_connection_read_service import (
    ModelConnectionReadService,
)
from inframeld_backend.access.domain.policies.model_connection_destination_policy import (
    ModelConnectionDestinationPolicy,
)
from inframeld_backend.access.infrastructure.repositories.postgres_model_connection_creation_repository import (
    PostgresModelConnectionCreationRepository,
)
from inframeld_backend.access.infrastructure.repositories.postgres_model_connection_credential_repository import (
    PostgresModelConnectionCredentialRepository,
)
from inframeld_backend.access.infrastructure.repositories.postgres_model_connection_grant_repository import (
    PostgresModelConnectionGrantRepository,
)
from inframeld_backend.access.infrastructure.repositories.postgres_model_connection_read_repository import (
    PostgresModelConnectionReadRepository,
)
from inframeld_backend.access.infrastructure.resources.pynacl_provider_credential_cipher import (
    PyNaClProviderCredentialCipher,
)
from inframeld_backend.access.infrastructure.settings.model_connection_destination_settings import (
    ModelConnectionDestinationSettings,
)
from inframeld_backend.access.infrastructure.settings.provider_credential_settings import (
    ProviderCredentialSettings,
)
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.application.services.idempotency_service import IdempotencyService
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.request_fingerprint_key import (
    RequestFingerprintKey,
)
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.resources.sqlalchemy_transaction_manager import (
    SqlAlchemyTransactionManager,
)
from inframeld_backend.shared.infrastructure.writers.postgres_operation_reservation_writer import (
    PostgresOperationReservationWriter,
)


@asynccontextmanager
async def open_model_connection_creation(
    database: Database,
    fingerprints: RequestFingerprintService,
    destinations: ModelConnectionDestinationSettings,
) -> AsyncGenerator[ModelConnectionCreator]:
    async with database.session() as session:
        yield ModelConnectionCreationService(
            SqlAlchemyTransactionManager(session),
            PostgresModelConnectionCreationRepository(session),
            IdempotencyService(PostgresOperationReservationWriter(session)),
            fingerprints,
            ModelConnectionDestinationPolicy(
                destinations.https_base_urls, destinations.local_ollama_base_urls
            ),
        )


@asynccontextmanager
async def open_model_connection_read(
    database: Database,
    application_key_profile: ApplicationKeyVerificationProfileDTO | None,
) -> AsyncGenerator[ModelConnectionReader]:
    async with database.session() as session:
        yield ModelConnectionReadService(
            SqlAlchemyTransactionManager(session),
            PostgresModelConnectionReadRepository(session, application_key_profile),
        )


@asynccontextmanager
async def open_model_connection_grant_change(
    database: Database,
    fingerprints: RequestFingerprintService,
) -> AsyncGenerator[ModelConnectionGrantChanger]:
    async with database.session() as session:
        yield ModelConnectionGrantChangeService(
            SqlAlchemyTransactionManager(session),
            PostgresModelConnectionGrantRepository(session),
            IdempotencyService(PostgresOperationReservationWriter(session)),
            fingerprints,
        )


@asynccontextmanager
async def open_model_connection_grant_read(
    database: Database,
) -> AsyncGenerator[ModelConnectionGrantsReader]:
    async with database.session() as session:
        yield ModelConnectionGrantsReadService(
            SqlAlchemyTransactionManager(session),
            PostgresModelConnectionGrantRepository(session),
        )


@asynccontextmanager
async def open_model_connection_credentials(
    database: Database,
    fingerprint_key: RequestFingerprintKey,
    destinations: ModelConnectionDestinationSettings,
    settings: ProviderCredentialSettings,
) -> AsyncGenerator[ModelConnectionCredentialService]:
    try:
        async with database.session() as session:
            yield ModelConnectionCredentialService(
                SqlAlchemyTransactionManager(session),
                PostgresModelConnectionCredentialRepository(session),
                IdempotencyService(PostgresOperationReservationWriter(session)),
                RequestFingerprintService(fingerprint_key),
                PyNaClProviderCredentialCipher(
                    settings.key_file,
                    settings.expected_key_id,
                    sha256(fingerprint_key.value).hexdigest(),
                ),
                ModelConnectionDestinationPolicy(
                    destinations.https_base_urls, destinations.local_ollama_base_urls
                ),
            )
    except (OperationalError, SqlAlchemyTimeoutError):
        raise DependencyUnavailableError() from None
