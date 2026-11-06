from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from inframeld_backend.access.application.protocols.access_group_action_grant_changer import (
    AccessGroupActionGrantChanger,
)
from inframeld_backend.access.application.protocols.access_group_action_grants_reader import (
    AccessGroupActionGrantsReader,
)
from inframeld_backend.access.application.services.access_group_action_grant_change_service import (
    AccessGroupActionGrantChangeService,
)
from inframeld_backend.access.application.services.access_group_action_grants_service import (
    AccessGroupActionGrantsService,
)
from inframeld_backend.access.infrastructure.readers.postgres_access_group_action_grant_result_reader import (
    PostgresAccessGroupActionGrantResultReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_access_group_action_grants_facts_reader import (
    PostgresAccessGroupActionGrantsFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_access_group_grant_management_facts_reader import (
    PostgresAccessGroupGrantManagementFactsReader,
)
from inframeld_backend.access.infrastructure.writers.postgres_access_group_action_grant_writer import (
    PostgresAccessGroupActionGrantWriter,
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
async def open_access_group_grant_change(
    database: Database, fingerprints: RequestFingerprintService
) -> AsyncGenerator[AccessGroupActionGrantChanger]:
    async with database.session() as session:
        yield AccessGroupActionGrantChangeService(
            transaction_manager=SqlAlchemyTransactionManager(session),
            access_group_grant_facts_reader=PostgresAccessGroupGrantManagementFactsReader(session),
            access_group_grant_writer=PostgresAccessGroupActionGrantWriter(
                session, PostgresAuditEventWriter(session)
            ),
            access_group_grant_result_reader=PostgresAccessGroupActionGrantResultReader(session),
            operation_idempotency=IdempotencyService(PostgresOperationReservationWriter(session)),
            request_fingerprint_service=fingerprints,
        )


@asynccontextmanager
async def open_access_group_grant_read(
    database: Database,
) -> AsyncGenerator[AccessGroupActionGrantsReader]:
    """Own one clean request-local session for a current-authority assignment page."""
    async with database.session() as session:
        yield AccessGroupActionGrantsService(PostgresAccessGroupActionGrantsFactsReader(session))
