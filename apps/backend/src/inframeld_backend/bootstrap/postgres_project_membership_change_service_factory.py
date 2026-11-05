from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import override

from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.protocols.project_membership_change_service_factory import (
    ProjectMembershipChangeServiceFactory,
)
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


class PostgresProjectMembershipChangeServiceFactory(ProjectMembershipChangeServiceFactory):
    """Bind each membership operation's database collaborators to one fresh session."""

    def __init__(
        self, database: Database, fingerprints: ProjectMembershipChangeFingerprintService
    ) -> None:
        self._database = database
        self._fingerprints = fingerprints

    @override
    @asynccontextmanager
    async def open(self) -> AsyncGenerator[ProjectMembershipChanger]:
        async with self._database.session() as session:
            yield self.create(session, self._fingerprints)

    @staticmethod
    def create(
        session: AsyncSession, fingerprints: ProjectMembershipChangeFingerprintService
    ) -> ProjectMembershipChangeService:
        """Assemble one service on the session owned by the calling scope."""
        return ProjectMembershipChangeService(
            transactions=SqlAlchemyTransactionManager(session),
            facts=PostgresProjectMembershipChangeFactsReader(session),
            writer=PostgresProjectMembershipChangeWriter(session),
            results=PostgresProjectMembershipChangeResultReader(session),
            idempotency=IdempotencyService(PostgresOperationReservationWriter(session)),
            fingerprints=fingerprints,
        )
