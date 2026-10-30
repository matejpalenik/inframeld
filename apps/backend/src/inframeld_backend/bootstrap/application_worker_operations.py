import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import override

from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError

from inframeld_backend.access.application.services.admitted_work_authorization_service import (
    AdmittedWorkAuthorizationService,
)
from inframeld_backend.access.infrastructure.readers.postgres_admitted_work_facts_reader import (
    PostgresAdmittedWorkFactsReader,
)
from inframeld_backend.shared.application.dtos.job_attempt_context_dto import JobAttemptContextDTO
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.application.errors.job_errors import JobWorkerStoppingError
from inframeld_backend.shared.application.protocols.job_checkpoints import JobCheckpoints
from inframeld_backend.shared.application.services.job_checkpoint_service import (
    JobCheckpointService,
)
from inframeld_backend.shared.infrastructure.repositories.postgres_job_store import PostgresJobStore
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.resources.sqlalchemy_transaction_manager import (
    SqlAlchemyTransactionManager,
)
from inframeld_backend.shared.infrastructure.settings.job_settings import JobSettings


class ApplicationWorkerOperations(JobCheckpoints):
    """Close every checkpoint session before control returns to the owning handler."""

    def __init__(self, database: Database, settings: JobSettings, stopped: asyncio.Event) -> None:
        self._database = database
        self._settings = settings
        self._stopped = stopped

    @asynccontextmanager
    async def _open(self) -> AsyncGenerator[JobCheckpoints]:
        try:
            async with (
                asyncio.timeout(self._settings.database_timeout_seconds),
                self._database.session() as session,
            ):
                yield JobCheckpointService(
                    SqlAlchemyTransactionManager(session),
                    PostgresJobStore(session),
                    AdmittedWorkAuthorizationService(PostgresAdmittedWorkFactsReader(session)),
                    lease_seconds=self._settings.lease_seconds,
                )
        except (TimeoutError, OperationalError, InterfaceError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError(
                "The job checkpoint state could not be confirmed."
            ) from None

    @override
    async def check(self, context: JobAttemptContextDTO) -> None:
        if self._stopped.is_set():
            raise JobWorkerStoppingError()
        await self.renew(context)

    async def renew(self, context: JobAttemptContextDTO) -> None:
        async with self._open() as operation:
            await operation.check(context)

    @override
    async def save(self, context: JobAttemptContextDTO, data: bytes) -> None:
        async with self._open() as operation:
            await operation.save(context, data)

    @override
    async def begin_effect(self, context: JobAttemptContextDTO, effect_id: str) -> None:
        if self._stopped.is_set():
            raise JobWorkerStoppingError()
        async with self._open() as operation:
            await operation.begin_effect(context, effect_id)

    @override
    async def confirm_effect(
        self, context: JobAttemptContextDTO, effect_id: str, data: bytes
    ) -> None:
        async with self._open() as operation:
            await operation.confirm_effect(context, effect_id, data)

    @override
    async def succeed(self, context: JobAttemptContextDTO) -> None:
        async with self._open() as operation:
            await operation.succeed(context)

    @override
    async def fail(self, context: JobAttemptContextDTO) -> None:
        async with self._open() as operation:
            await operation.fail(context)
