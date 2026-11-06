from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from inframeld_backend.access.application.protocols.project_grant_changer import ProjectGrantChanger
from inframeld_backend.access.application.services.project_grant_change_fingerprint_service import (
    ProjectGrantChangeFingerprintService,
)
from inframeld_backend.access.application.services.project_grant_change_service import (
    ProjectGrantChangeService,
)
from inframeld_backend.access.infrastructure.readers.postgres_project_action_grant_result_reader import (
    PostgresProjectActionGrantResultReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_project_grant_change_facts_reader import (
    PostgresProjectGrantChangeFactsReader,
)
from inframeld_backend.access.infrastructure.repositories.postgres_project_membership_repository import (
    PostgresProjectMembershipRepository,
)
from inframeld_backend.access.infrastructure.writers.postgres_audit_event_writer import (
    PostgresAuditEventWriter,
)
from inframeld_backend.access.infrastructure.writers.postgres_project_action_grant_result_writer import (
    PostgresProjectActionGrantResultWriter,
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
async def open_project_grant_change(
    database: Database,
    project_grant_change_fingerprint_service: ProjectGrantChangeFingerprintService,
) -> AsyncGenerator[ProjectGrantChanger]:
    """Close one request-local session after the application operation owns its transaction."""
    async with database.session() as session:
        yield ProjectGrantChangeService(
            transaction_manager=SqlAlchemyTransactionManager(session),
            operation_idempotency=IdempotencyService(PostgresOperationReservationWriter(session)),
            membership_repository=PostgresProjectMembershipRepository(
                session, PostgresAuditEventWriter(session)
            ),
            project_grant_change_fingerprint_service=project_grant_change_fingerprint_service,
            grant_management_facts_reader=PostgresProjectGrantChangeFactsReader(session),
            grant_result_reader=PostgresProjectActionGrantResultReader(session),
            grant_result_writer=PostgresProjectActionGrantResultWriter(session),
        )
