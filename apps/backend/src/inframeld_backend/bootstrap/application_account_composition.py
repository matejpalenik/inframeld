from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from inframeld_backend.access.application.protocols.application_account_creator import (
    ApplicationAccountCreator,
)
from inframeld_backend.access.application.protocols.application_account_deleter import (
    ApplicationAccountDeleter,
)
from inframeld_backend.access.application.protocols.application_account_reader import (
    ApplicationAccountReader,
)
from inframeld_backend.access.application.services.application_account_creation_fingerprint_service import (
    ApplicationAccountCreationFingerprintService,
)
from inframeld_backend.access.application.services.application_account_creation_service import (
    ApplicationAccountCreationService,
)
from inframeld_backend.access.application.services.application_account_deletion_fingerprint_service import (
    ApplicationAccountDeletionFingerprintService,
)
from inframeld_backend.access.application.services.application_account_deletion_service import (
    ApplicationAccountDeletionService,
)
from inframeld_backend.access.application.services.application_account_read_service import (
    ApplicationAccountReadService,
)
from inframeld_backend.access.infrastructure.readers.postgres_application_account_creation_facts_reader import (
    PostgresApplicationAccountCreationFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_application_account_creation_result_reader import (
    PostgresApplicationAccountCreationResultReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_application_account_deletion_facts_reader import (
    PostgresApplicationAccountDeletionFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_application_account_facts_reader import (
    PostgresApplicationAccountFactsReader,
)
from inframeld_backend.access.infrastructure.writers.postgres_application_account_creation_writer import (
    PostgresApplicationAccountCreationWriter,
)
from inframeld_backend.access.infrastructure.writers.postgres_application_account_deletion_writer import (
    PostgresApplicationAccountDeletionWriter,
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
async def open_application_account_creation(
    database: Database, fingerprints: ApplicationAccountCreationFingerprintService
) -> AsyncGenerator[ApplicationAccountCreator]:
    async with database.session() as session:
        yield ApplicationAccountCreationService(
            transaction_manager=SqlAlchemyTransactionManager(session),
            creation_facts_reader=PostgresApplicationAccountCreationFactsReader(session),
            creation_writer=PostgresApplicationAccountCreationWriter(session),
            creation_result_reader=PostgresApplicationAccountCreationResultReader(session),
            operation_idempotency=IdempotencyService(PostgresOperationReservationWriter(session)),
            creation_fingerprint_service=fingerprints,
        )


@asynccontextmanager
async def open_application_account_read(
    database: Database,
) -> AsyncGenerator[ApplicationAccountReader]:
    async with database.session() as session:
        yield ApplicationAccountReadService(PostgresApplicationAccountFactsReader(session))


@asynccontextmanager
async def open_application_account_deletion(
    database: Database, fingerprints: ApplicationAccountDeletionFingerprintService
) -> AsyncGenerator[ApplicationAccountDeleter]:
    async with database.session() as session:
        yield ApplicationAccountDeletionService(
            transaction_manager=SqlAlchemyTransactionManager(session),
            deletion_facts_reader=PostgresApplicationAccountDeletionFactsReader(session),
            deletion_writer=PostgresApplicationAccountDeletionWriter(session),
            operation_idempotency=IdempotencyService(PostgresOperationReservationWriter(session)),
            deletion_fingerprint_service=fingerprints,
        )
