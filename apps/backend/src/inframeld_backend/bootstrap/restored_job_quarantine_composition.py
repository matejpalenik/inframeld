import asyncio

from inframeld_backend.access.cli.mappers.restored_job_quarantine_mapper import (
    RestoredJobQuarantineMapper,
)
from inframeld_backend.shared.application.commands.restored_job_quarantine_command import (
    RestoredJobQuarantineCommand,
)
from inframeld_backend.shared.application.services.restored_job_quarantine_service import (
    RestoredJobQuarantineService,
)
from inframeld_backend.shared.infrastructure.repositories.postgres_job_store import PostgresJobStore
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.resources.sqlalchemy_transaction_manager import (
    SqlAlchemyTransactionManager,
)


async def execute_restored_job_quarantine(
    command: RestoredJobQuarantineCommand, database: Database
) -> dict[str, object]:
    """Use the maintenance-owned pool without enabling worker or provider operations."""
    async with asyncio.timeout(5), database.session() as session:
        service = RestoredJobQuarantineService(
            SqlAlchemyTransactionManager(session), PostgresJobStore(session)
        )
        result = await service.execute(command)
    return RestoredJobQuarantineMapper.result(command, result)
