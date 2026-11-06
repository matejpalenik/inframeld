from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from inframeld_backend.access.application.protocols.application_account_action_grant_changer import (
    ApplicationAccountActionGrantChanger,
)
from inframeld_backend.access.application.protocols.application_account_action_grants_reader import (
    ApplicationAccountActionGrantsReader,
)
from inframeld_backend.access.application.services.application_account_action_grant_change_service import (
    ApplicationAccountActionGrantChangeService,
)
from inframeld_backend.access.application.services.application_account_action_grants_service import (
    ApplicationAccountActionGrantsService,
)
from inframeld_backend.access.infrastructure.readers.postgres_application_account_action_grant_result_reader import (
    PostgresApplicationAccountActionGrantResultReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_application_account_action_grants_facts_reader import (
    PostgresApplicationAccountActionGrantsFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_application_account_grant_management_facts_reader import (
    PostgresApplicationAccountGrantManagementFactsReader,
)
from inframeld_backend.access.infrastructure.writers.postgres_application_account_action_grant_writer import (
    PostgresApplicationAccountActionGrantWriter,
)
from inframeld_backend.access.infrastructure.writers.postgres_audit_event_writer import (
    PostgresAuditEventWriter,
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
async def open_application_account_grant_change(
    database: Database, fingerprints: RequestFingerprintService
) -> AsyncGenerator[ApplicationAccountActionGrantChanger]:
    async with database.session() as session:
        yield ApplicationAccountActionGrantChangeService(
            transaction_manager=SqlAlchemyTransactionManager(session),
            application_account_grant_facts_reader=PostgresApplicationAccountGrantManagementFactsReader(
                session
            ),
            application_account_grant_writer=PostgresApplicationAccountActionGrantWriter(
                session, PostgresAuditEventWriter(session)
            ),
            application_account_grant_result_reader=PostgresApplicationAccountActionGrantResultReader(
                session
            ),
            operation_idempotency=IdempotencyService(PostgresOperationReservationWriter(session)),
            request_fingerprint_service=fingerprints,
        )


@asynccontextmanager
async def open_application_account_grant_read(
    database: Database,
) -> AsyncGenerator[ApplicationAccountActionGrantsReader]:
    """Own one clean request-local session for a current-authority assignment page."""
    async with database.session() as session:
        yield ApplicationAccountActionGrantsService(
            PostgresApplicationAccountActionGrantsFactsReader(session)
        )
