from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from inframeld_backend.access.application.dtos.application_key_verification_profile_dto import (
    ApplicationKeyVerificationProfileDTO,
)
from inframeld_backend.access.application.protocols.application_key_issuer import (
    ApplicationKeyIssuer,
)
from inframeld_backend.access.application.protocols.application_key_revoker import (
    ApplicationKeyRevoker,
)
from inframeld_backend.access.application.services.application_key_issuance_fingerprint_service import (
    ApplicationKeyIssuanceFingerprintService,
)
from inframeld_backend.access.application.services.application_key_issuance_service import (
    ApplicationKeyIssuanceService,
)
from inframeld_backend.access.application.services.application_key_revocation_fingerprint_service import (
    ApplicationKeyRevocationFingerprintService,
)
from inframeld_backend.access.application.services.application_key_revocation_service import (
    ApplicationKeyRevocationService,
)
from inframeld_backend.access.infrastructure.readers.postgres_application_key_issuance_facts_reader import (
    PostgresApplicationKeyIssuanceFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_application_key_revocation_facts_reader import (
    PostgresApplicationKeyRevocationFactsReader,
)
from inframeld_backend.access.infrastructure.settings.application_key_issuance_settings import (
    ApplicationKeyIssuanceSettings,
)
from inframeld_backend.access.infrastructure.writers.postgres_application_key_issuance_writer import (
    PostgresApplicationKeyIssuanceWriter,
)
from inframeld_backend.access.infrastructure.writers.postgres_application_key_revocation_writer import (
    PostgresApplicationKeyRevocationWriter,
)
from inframeld_backend.shared.application.services.idempotency_service import IdempotencyService
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.resources.sqlalchemy_transaction_manager import (
    SqlAlchemyTransactionManager,
)
from inframeld_backend.shared.infrastructure.writers.postgres_operation_reservation_writer import (
    PostgresOperationReservationWriter,
)


@asynccontextmanager
async def open_application_key_issuance(
    database: Database,
    fingerprints: ApplicationKeyIssuanceFingerprintService,
    *,
    http_profile: ApplicationKeyVerificationProfileDTO | None,
    mcp_profile: ApplicationKeyVerificationProfileDTO | None,
    settings: ApplicationKeyIssuanceSettings,
) -> AsyncGenerator[ApplicationKeyIssuer]:
    async with database.session() as session:
        yield ApplicationKeyIssuanceService(
            transaction_manager=SqlAlchemyTransactionManager(session),
            issuance_facts_reader=PostgresApplicationKeyIssuanceFactsReader(session),
            issuance_writer=PostgresApplicationKeyIssuanceWriter(session),
            operation_idempotency=IdempotencyService(PostgresOperationReservationWriter(session)),
            issuance_fingerprint_service=fingerprints,
            http_profile=http_profile,
            mcp_profile=mcp_profile,
            default_lifetime_seconds=settings.default_lifetime_seconds,
            maximum_lifetime_seconds=settings.maximum_lifetime_seconds,
        )


@asynccontextmanager
async def open_application_key_revocation(
    database: Database, fingerprints: ApplicationKeyRevocationFingerprintService
) -> AsyncGenerator[ApplicationKeyRevoker]:
    async with database.session() as session:
        yield ApplicationKeyRevocationService(
            transaction_manager=SqlAlchemyTransactionManager(session),
            revocation_facts_reader=PostgresApplicationKeyRevocationFactsReader(session),
            revocation_writer=PostgresApplicationKeyRevocationWriter(session),
            operation_idempotency=IdempotencyService(PostgresOperationReservationWriter(session)),
            revocation_fingerprint_service=fingerprints,
        )
