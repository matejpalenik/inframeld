import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import override

from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.services.admitted_work_authorization_service import (
    AdmittedWorkAuthorizationService,
)
from inframeld_backend.access.infrastructure.readers.postgres_admitted_work_facts_reader import (
    PostgresAdmittedWorkFactsReader,
)
from inframeld_backend.shared.application.dtos.artifact_attempt_dto import ArtifactAttemptDTO
from inframeld_backend.shared.application.dtos.artifact_cleanup_job_binding_dto import (
    ArtifactCleanupJobBindingDTO,
)
from inframeld_backend.shared.application.dtos.artifact_scope_dto import ArtifactScopeDTO
from inframeld_backend.shared.application.dtos.job_attempt_context_dto import JobAttemptContextDTO
from inframeld_backend.shared.application.dtos.job_effect_binding_dto import JobEffectBindingDTO
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.application.errors.job_errors import JobWorkerStoppingError
from inframeld_backend.shared.application.protocols.artifact_cleanup_preparer import (
    ArtifactCleanupPreparer,
)
from inframeld_backend.shared.application.protocols.job_checkpoints import JobCheckpoints
from inframeld_backend.shared.application.protocols.job_effect_observation_recorder import (
    JobEffectObservationRecorder,
)
from inframeld_backend.shared.application.services.artifact_cleanup_authorization_service import (
    ArtifactCleanupAuthorizationService,
)
from inframeld_backend.shared.application.services.artifact_cleanup_checkpoint_service import (
    ArtifactCleanupCheckpointService,
)
from inframeld_backend.shared.application.services.artifact_cleanup_preparation_service import (
    ArtifactCleanupPreparationService,
)
from inframeld_backend.shared.application.services.job_checkpoint_service import (
    JobCheckpointService,
)
from inframeld_backend.shared.application.services.job_effect_observation_service import (
    JobEffectObservationService,
)
from inframeld_backend.shared.application.value_objects.artifact_attempt_id import ArtifactAttemptId
from inframeld_backend.shared.application.value_objects.job_effect_id import JobEffectId
from inframeld_backend.shared.infrastructure.readers.postgres_artifact_cleanup_facts_reader import (
    PostgresArtifactCleanupFactsReader,
)
from inframeld_backend.shared.infrastructure.readers.postgres_artifact_cleanup_target_reader import (
    PostgresArtifactCleanupTargetReader,
)
from inframeld_backend.shared.infrastructure.repositories.postgres_job_store import PostgresJobStore
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.resources.sqlalchemy_transaction_manager import (
    SqlAlchemyTransactionManager,
)
from inframeld_backend.shared.infrastructure.settings.job_settings import JobSettings


class ApplicationWorkerOperations(
    JobCheckpoints, ArtifactCleanupPreparer, JobEffectObservationRecorder
):
    """Close each protected SQL session before returning to the handler or native-call gate."""

    def __init__(self, database: Database, settings: JobSettings, stopped: asyncio.Event) -> None:
        self._database = database
        self._settings = settings
        self._stopped = stopped

    @asynccontextmanager
    async def _session(self) -> AsyncGenerator[AsyncSession]:
        try:
            async with (
                asyncio.timeout(self._settings.database_timeout_seconds),
                self._database.session() as session,
            ):
                yield session
        except (TimeoutError, OperationalError, InterfaceError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError(
                "The original job state could not be confirmed."
            ) from None

    @asynccontextmanager
    async def _open(self, context: JobAttemptContextDTO) -> AsyncGenerator[JobCheckpoints]:
        async with self._session() as session:
            transactions = SqlAlchemyTransactionManager(session)
            jobs = PostgresJobStore(session)
            if isinstance(context.binding, ArtifactCleanupJobBindingDTO):
                yield ArtifactCleanupCheckpointService(
                    transactions,
                    jobs,
                    ArtifactCleanupAuthorizationService(
                        PostgresArtifactCleanupFactsReader(session)
                    ),
                    lease_seconds=self._settings.lease_seconds,
                )
            else:
                yield JobCheckpointService(
                    transactions,
                    jobs,
                    AdmittedWorkAuthorizationService(PostgresAdmittedWorkFactsReader(session)),
                    lease_seconds=self._settings.lease_seconds,
                )

    @asynccontextmanager
    async def _observations(self) -> AsyncGenerator[JobEffectObservationService]:
        async with self._session() as session:
            yield JobEffectObservationService(
                SqlAlchemyTransactionManager(session),
                PostgresJobStore(session),
                AdmittedWorkAuthorizationService(PostgresAdmittedWorkFactsReader(session)),
                ArtifactCleanupAuthorizationService(PostgresArtifactCleanupFactsReader(session)),
            )

    @override
    async def prepare(self, context: JobAttemptContextDTO) -> JobEffectBindingDTO | None:
        if self._stopped.is_set():
            raise JobWorkerStoppingError()
        async with self._session() as session:
            return await ArtifactCleanupPreparationService(
                SqlAlchemyTransactionManager(session),
                PostgresJobStore(session),
                ArtifactCleanupAuthorizationService(PostgresArtifactCleanupFactsReader(session)),
                PostgresArtifactCleanupTargetReader(session),
            ).prepare(context)

    @override
    async def admit_put(self, observation: JobEffectId, attempt: ArtifactAttemptDTO) -> None:
        if self._stopped.is_set():
            raise JobWorkerStoppingError()
        async with self._observations() as operation:
            await operation.admit_put(observation, attempt)

    @override
    async def admit_delete(
        self, observation: JobEffectId, scope: ArtifactScopeDTO, attempt_id: ArtifactAttemptId
    ) -> None:
        if self._stopped.is_set():
            raise JobWorkerStoppingError()
        async with self._observations() as operation:
            await operation.admit_delete(observation, scope, attempt_id)

    @override
    async def record_put_abort(self, observation: JobEffectId, attempt: ArtifactAttemptDTO) -> None:
        async with self._observations() as operation:
            await operation.record_put_abort(observation, attempt)

    @override
    async def record_delete_abort(
        self, observation: JobEffectId, scope: ArtifactScopeDTO, attempt_id: ArtifactAttemptId
    ) -> None:
        async with self._observations() as operation:
            await operation.record_delete_abort(observation, scope, attempt_id)

    @override
    async def check(self, context: JobAttemptContextDTO) -> None:
        if self._stopped.is_set():
            raise JobWorkerStoppingError()
        await self.renew(context)

    async def renew(self, context: JobAttemptContextDTO) -> None:
        async with self._open(context) as operation:
            await operation.check(context)

    @override
    async def save(self, context: JobAttemptContextDTO, data: bytes) -> None:
        async with self._open(context) as operation:
            await operation.save(context, data)

    @override
    async def begin_effect(self, context: JobAttemptContextDTO, effect_id: str) -> None:
        if self._stopped.is_set():
            raise JobWorkerStoppingError()
        async with self._open(context) as operation:
            await operation.begin_effect(context, effect_id)

    @override
    async def confirm_effect(
        self, context: JobAttemptContextDTO, effect_id: str, data: bytes
    ) -> None:
        async with self._open(context) as operation:
            await operation.confirm_effect(context, effect_id, data)

    @override
    async def succeed(self, context: JobAttemptContextDTO) -> None:
        async with self._open(context) as operation:
            await operation.succeed(context)

    @override
    async def fail(self, context: JobAttemptContextDTO) -> None:
        async with self._open(context) as operation:
            await operation.fail(context)
