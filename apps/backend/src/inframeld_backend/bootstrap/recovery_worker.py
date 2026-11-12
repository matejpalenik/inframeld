"""Own recovery resources and run one background action at a time."""

import asyncio
import signal
from collections.abc import AsyncGenerator
from contextlib import ExitStack, asynccontextmanager, suppress
from uuid import UUID, uuid4

import structlog
from ory_hydra_client import ApiClient, Configuration, OAuth2Api
from ory_kratos_client import ApiClient as KratosApiClient
from ory_kratos_client import Configuration as KratosConfiguration
from ory_kratos_client.api.identity_api import IdentityApi
from pydantic import ValidationError
from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError

from inframeld_backend.access.application.protocols.human_suspension_cleanup_executor import (
    HumanSuspensionCleanupExecutor,
)
from inframeld_backend.access.application.protocols.identity_recovery_cleanup_executor import (
    IdentityRecoveryCleanupExecutor,
)
from inframeld_backend.access.application.protocols.identity_recovery_cleanup_reconciler import (
    IdentityRecoveryCleanupReconciler,
)
from inframeld_backend.access.application.services.human_suspension_cleanup_execution_service import (
    HumanSuspensionCleanupExecutionService,
)
from inframeld_backend.access.application.services.identity_recovery_cleanup_execution_service import (
    IdentityRecoveryCleanupExecutionService,
)
from inframeld_backend.access.application.services.identity_recovery_cleanup_reconciliation_service import (
    IdentityRecoveryCleanupReconciliationService,
)
from inframeld_backend.access.infrastructure.readers.postgres_identity_recovery_cleanup_facts_reader import (
    PostgresIdentityRecoveryCleanupFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_identity_recovery_cleanup_proof_reader import (
    PostgresIdentityRecoveryCleanupProofReader,
)
from inframeld_backend.access.infrastructure.resources.sqlalchemy_recovery_transaction_manager import (
    SqlAlchemyRecoveryTransactionManager,
)
from inframeld_backend.access.infrastructure.revokers.hydra_human_oauth_credential_revoker import (
    HydraHumanOAuthCredentialRevoker,
)
from inframeld_backend.access.infrastructure.revokers.kratos_human_session_revoker import (
    KratosHumanSessionRevoker,
)
from inframeld_backend.access.infrastructure.writers.postgres_identity_recovery_cleanup_proof_writer import (
    PostgresIdentityRecoveryCleanupProofWriter,
)
from inframeld_backend.access.infrastructure.writers.postgres_identity_recovery_cleanup_writer import (
    PostgresIdentityRecoveryCleanupWriter,
)
from inframeld_backend.bootstrap.recovery_completion_operation import RecoveryCompletionOperation
from inframeld_backend.bootstrap.recovery_worker_application_settings import (
    RecoveryWorkerApplicationSettings,
)
from inframeld_backend.shared.application.errors.application_errors import (
    ConflictError,
    DependencyUnavailableError,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.infrastructure.logging.logging_configuration import configure_logging
from inframeld_backend.shared.infrastructure.readers.postgres_installation_identity_reader import (
    PostgresInstallationIdentityReader,
)
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.writers.postgres_human_suspension_cleanup_checkpoint_writer import (
    PostgresHumanSuspensionCleanupCheckpointWriter,
)
from inframeld_backend.shared.infrastructure.writers.postgres_human_suspension_cleanup_claim_writer import (
    PostgresHumanSuspensionCleanupClaimWriter,
)


@asynccontextmanager
async def _open_operations(
    database: Database,
    api: OAuth2Api,
    kratos: IdentityApi | None,
    settings: RecoveryWorkerApplicationSettings,
    installation: InstallationId,
    worker_id: UUID,
    stopped: asyncio.Event,
) -> AsyncGenerator[
    tuple[
        IdentityRecoveryCleanupExecutor,
        HumanSuspensionCleanupExecutor | None,
        IdentityRecoveryCleanupReconciler,
    ]
]:
    """Construct cleanup collaborators on one bounded database session."""
    cleanup = settings.recovery_cleanup
    try:
        async with database.session() as session:
            transactions = SqlAlchemyRecoveryTransactionManager(session)
            hydra_revoker = HydraHumanOAuthCredentialRevoker(api)
            execution = IdentityRecoveryCleanupExecutionService(
                transactions,
                PostgresIdentityRecoveryCleanupFactsReader(
                    session, installation_id=installation, authority=cleanup.authority
                ),
                PostgresIdentityRecoveryCleanupWriter(
                    session, installation_id=installation, authority=cleanup.authority
                ),
                hydra_revoker,
                worker_id=worker_id,
                provider_timeout_seconds=cleanup.provider_timeout_seconds,
                database_timeout_seconds=cleanup.database_timeout_seconds,
                lease_seconds=cleanup.lease_seconds,
                stop_requested=stopped.is_set,
            )
            suspension = (
                HumanSuspensionCleanupExecutionService(
                    transactions,
                    PostgresHumanSuspensionCleanupClaimWriter(
                        session, installation_id=installation, authority=cleanup.authority
                    ),
                    PostgresHumanSuspensionCleanupCheckpointWriter(session),
                    KratosHumanSessionRevoker(kratos, cleanup.authority),
                    hydra_revoker,
                    worker_id=worker_id,
                    provider_timeout_seconds=cleanup.provider_timeout_seconds,
                    database_timeout_seconds=cleanup.database_timeout_seconds,
                    lease_seconds=cleanup.lease_seconds,
                    stop_requested=stopped.is_set,
                )
                if kratos is not None
                else None
            )
            reconciliation = IdentityRecoveryCleanupReconciliationService(
                transactions,
                PostgresIdentityRecoveryCleanupProofReader(
                    session, installation_id=installation, authority=cleanup.authority
                ),
                PostgresIdentityRecoveryCleanupProofWriter(
                    session, installation_id=installation, authority=cleanup.authority
                ),
                RecoveryCompletionOperation(
                    database,
                    installation_id=installation,
                    authority=cleanup.authority,
                    database_timeout_seconds=cleanup.database_timeout_seconds,
                ),
                database_timeout_seconds=cleanup.database_timeout_seconds,
                stop_requested=stopped.is_set,
            )
            yield execution, suspension, reconciliation
    except (OperationalError, InterfaceError, SqlAlchemyTimeoutError):
        # Commit communication failure does not prove that nothing was saved.
        raise DependencyUnavailableError() from None


async def _wait(stopped: asyncio.Event, delay: float) -> None:
    with suppress(TimeoutError):
        await asyncio.wait_for(stopped.wait(), timeout=delay)


async def execute_cleanup_pass(
    routine: IdentityRecoveryCleanupExecutor,
    suspension: HumanSuspensionCleanupExecutor | None,
    *,
    routine_first: bool,
    stopped: asyncio.Event,
) -> bool:
    """Await the preferred family first and advance at most one attempt."""
    ordered = (routine, suspension) if routine_first else (suspension, routine)
    for cleanup in ordered:
        if stopped.is_set():
            break
        if cleanup is not None and await cleanup.execute_once():
            return True
    return False


async def run_recovery_worker(
    settings: RecoveryWorkerApplicationSettings, stopped: asyncio.Event
) -> None:
    """Keep durable progress on stop, with one bounded grace period for local shutdown."""
    database = Database(settings.database)
    providers = ExitStack()
    sdk = ApiClient(
        Configuration(
            host=str(settings.recovery_cleanup.hydra_admin_url).rstrip("/"), retries=0, debug=False
        )
    )
    providers.callback(sdk.rest_client.pool_manager.clear)
    log = structlog.get_logger()
    worker_id = uuid4()
    task: asyncio.Task[None] | None = None
    stop_wait: asyncio.Task[bool] | None = None
    try:
        await database.startup()
        installation = await PostgresInstallationIdentityReader(database).read()
        api = OAuth2Api(sdk)
        kratos = None
        if settings.recovery_cleanup.kratos_admin_url is not None:
            kratos_sdk = KratosApiClient(
                KratosConfiguration(
                    host=str(settings.recovery_cleanup.kratos_admin_url).rstrip("/"),
                    retries=0,
                    debug=False,
                )
            )
            providers.callback(kratos_sdk.rest_client.pool_manager.clear)
            kratos = IdentityApi(kratos_sdk)

        async def work() -> None:
            log.info("recovery_worker_ready", suspension_cleanup_enabled=kratos is not None)
            routine_first = True
            while not stopped.is_set():
                try:
                    prefer_routine = routine_first
                    routine_first = not routine_first
                    async with _open_operations(
                        database, api, kratos, settings, installation, worker_id, stopped
                    ) as (execution, suspension, reconciliation):
                        changed = await execute_cleanup_pass(
                            execution, suspension, routine_first=prefer_routine, stopped=stopped
                        )
                        completed = (
                            0 if stopped.is_set() else await reconciliation.reconcile_pending()
                        )
                    if not changed and not completed:
                        await _wait(stopped, settings.recovery_cleanup.poll_seconds)
                except (DependencyUnavailableError, ConflictError):
                    log.warning("recovery_work_deferred", category="required_state_unavailable")
                    await _wait(stopped, 15)

        task = asyncio.create_task(work())
        stop_wait = asyncio.create_task(stopped.wait())
        await asyncio.wait((task, stop_wait), return_when=asyncio.FIRST_COMPLETED)
        if task.done():
            await task
        else:
            try:
                async with asyncio.timeout(settings.recovery_cleanup.shutdown_seconds):
                    await asyncio.shield(task)
            except TimeoutError:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
    finally:
        for pending in (task, stop_wait):
            if pending is not None and not pending.done():
                pending.cancel()
        if task is not None:
            await asyncio.gather(task, return_exceptions=True)
        if stop_wait is not None:
            await asyncio.gather(stop_wait, return_exceptions=True)
        try:
            providers.close()
        finally:
            await database.shutdown()


async def _serve(settings: RecoveryWorkerApplicationSettings) -> None:
    """Install cleanup-worker stop handlers only for this process lifetime."""
    stopped = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signum, stopped.set)
    try:
        await run_recovery_worker(settings, stopped)
    finally:
        for signum in (signal.SIGINT, signal.SIGTERM):
            loop.remove_signal_handler(signum)


def main() -> int:
    try:
        settings = RecoveryWorkerApplicationSettings.model_validate({})
    except ValidationError:
        print('{"code":"invalid_configuration"}')
        return 2
    configure_logging(level=settings.log_level, log_format=settings.log_format)
    try:
        asyncio.run(_serve(settings))
    except KeyboardInterrupt:
        return 0
    except Exception:
        # Exception strings and tracebacks may contain provider or identity details.
        structlog.get_logger().error("recovery_worker_stopped", category="unexpected_error")
        return 1
    return 0
