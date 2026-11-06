from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from inframeld_backend.access.application.protocols.organization_action_grant_changer import (
    OrganizationActionGrantChanger,
)
from inframeld_backend.access.application.protocols.organization_action_grants_reader import (
    OrganizationActionGrantsReader,
)
from inframeld_backend.access.application.services.organization_action_grant_change_service import (
    OrganizationActionGrantChangeService,
)
from inframeld_backend.access.application.services.organization_action_grants_service import (
    OrganizationActionGrantsService,
)
from inframeld_backend.access.infrastructure.readers.postgres_organization_action_grant_result_reader import (
    PostgresOrganizationActionGrantResultReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_organization_action_grants_facts_reader import (
    PostgresOrganizationActionGrantsFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_organization_grant_management_facts_reader import (
    PostgresOrganizationGrantManagementFactsReader,
)
from inframeld_backend.access.infrastructure.writers.postgres_audit_event_writer import (
    PostgresAuditEventWriter,
)
from inframeld_backend.access.infrastructure.writers.postgres_organization_action_grant_writer import (
    PostgresOrganizationActionGrantWriter,
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
async def open_organization_grant_change(
    database: Database, fingerprints: RequestFingerprintService
) -> AsyncGenerator[OrganizationActionGrantChanger]:
    async with database.session() as session:
        yield OrganizationActionGrantChangeService(
            transaction_manager=SqlAlchemyTransactionManager(session),
            organization_grant_facts_reader=PostgresOrganizationGrantManagementFactsReader(session),
            organization_grant_writer=PostgresOrganizationActionGrantWriter(
                session, PostgresAuditEventWriter(session)
            ),
            organization_grant_result_reader=PostgresOrganizationActionGrantResultReader(session),
            operation_idempotency=IdempotencyService(PostgresOperationReservationWriter(session)),
            request_fingerprint_service=fingerprints,
        )


@asynccontextmanager
async def open_organization_grant_read(
    database: Database,
) -> AsyncGenerator[OrganizationActionGrantsReader]:
    """Own one clean request-local session for a current-authority assignment page."""
    async with database.session() as session:
        yield OrganizationActionGrantsService(PostgresOrganizationActionGrantsFactsReader(session))
