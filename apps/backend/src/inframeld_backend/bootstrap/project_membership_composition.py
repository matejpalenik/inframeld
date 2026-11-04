from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from inframeld_backend.access.application.protocols.project_membership_changer import (
    ProjectMembershipChanger,
)
from inframeld_backend.access.application.services.project_membership_change_fingerprint_service import (
    ProjectMembershipChangeFingerprintService,
)
from inframeld_backend.access.application.services.project_membership_change_service import (
    ProjectMembershipChangeService,
)
from inframeld_backend.access.infrastructure.readers.postgres_project_membership_change_facts_reader import (
    PostgresProjectMembershipChangeFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_project_membership_change_result_reader import (
    PostgresProjectMembershipChangeResultReader,
)
from inframeld_backend.access.infrastructure.writers.postgres_project_membership_change_writer import (
    PostgresProjectMembershipChangeWriter,
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
async def open_project_membership_change(
    database: Database, fingerprints: ProjectMembershipChangeFingerprintService
) -> AsyncGenerator[ProjectMembershipChanger]:
    """Bind the complete membership operation to one request-local database session."""
    async with database.session() as session:
        yield ProjectMembershipChangeService(
            transactions=SqlAlchemyTransactionManager(session),
            facts=PostgresProjectMembershipChangeFactsReader(session),
            writer=PostgresProjectMembershipChangeWriter(session),
            results=PostgresProjectMembershipChangeResultReader(session),
            idempotency=IdempotencyService(PostgresOperationReservationWriter(session)),
            fingerprints=fingerprints,
        )
