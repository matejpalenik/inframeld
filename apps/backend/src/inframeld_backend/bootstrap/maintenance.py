"""Own protected maintenance resources and emit one secret-safe stdout result."""

import asyncio
import json
import os
import sys
from collections.abc import Sequence

from pydantic import ValidationError
from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError
from structlog.contextvars import bound_contextvars

from inframeld_backend.access.application.commands.resume_identity_recovery_cleanup_command import (
    ResumeIdentityRecoveryCleanupCommand,
)
from inframeld_backend.access.application.enums.recovery_maintenance_error_code import (
    RecoveryMaintenanceErrorCode,
)
from inframeld_backend.access.application.errors.recovery_maintenance_error import (
    RecoveryMaintenanceError,
)
from inframeld_backend.access.application.services.identity_recovery_cleanup_resume_service import (
    IdentityRecoveryCleanupResumeService,
)
from inframeld_backend.access.cli.errors.recovery_maintenance_input_error import (
    RecoveryMaintenanceInputError,
)
from inframeld_backend.access.cli.recovery_maintenance_cli import RecoveryMaintenanceCli
from inframeld_backend.access.infrastructure.readers.postgres_identity_recovery_cleanup_resume_facts_reader import (
    PostgresIdentityRecoveryCleanupResumeFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_identity_recovery_completion_facts_reader import (
    PostgresIdentityRecoveryCompletionFactsReader,
)
from inframeld_backend.access.infrastructure.resources.sqlalchemy_recovery_transaction_manager import (
    SqlAlchemyRecoveryTransactionManager,
)
from inframeld_backend.access.infrastructure.writers.postgres_identity_recovery_cleanup_resume_writer import (
    PostgresIdentityRecoveryCleanupResumeWriter,
)
from inframeld_backend.bootstrap.maintenance_application_settings import (
    MaintenanceApplicationSettings,
)
from inframeld_backend.shared.application.errors.application_errors import (
    ConflictError,
    DependencyUnavailableError,
)
from inframeld_backend.shared.infrastructure.diagnostics.error_reporting import (
    report_unexpected_error,
)
from inframeld_backend.shared.infrastructure.errors.database_errors import (
    DatabaseSchemaCompatibilityError,
    DatabaseStartupError,
)
from inframeld_backend.shared.infrastructure.logging.logging_configuration import configure_logging
from inframeld_backend.shared.infrastructure.resources.database import Database


async def _execute(
    command: ResumeIdentityRecoveryCleanupCommand, settings: MaintenanceApplicationSettings
) -> dict[str, object]:
    database = Database(settings.database)
    try:
        await database.startup()
        async with database.session() as session:
            service = IdentityRecoveryCleanupResumeService(
                SqlAlchemyRecoveryTransactionManager(session),
                PostgresIdentityRecoveryCleanupResumeFactsReader(session),
                PostgresIdentityRecoveryCompletionFactsReader(session),
                PostgresIdentityRecoveryCleanupResumeWriter(session),
            )
            return await RecoveryMaintenanceCli(service).execute(command)
    finally:
        await database.shutdown()


def _discard_failed_stdout() -> None:
    """Prevent shutdown from retrying the failed stdout flush."""
    descriptor = os.open(os.devnull, os.O_WRONLY)
    try:
        os.dup2(descriptor, sys.stdout.fileno())
    finally:
        os.close(descriptor)


def _emit(response: dict[str, object], status: int) -> int:
    try:
        print(json.dumps(response, ensure_ascii=True), flush=True)
    except BrokenPipeError:
        _discard_failed_stdout()
        return 1
    except (OSError, UnicodeError):
        # A committed authorization may already exist. Never dispatch again here.
        return 1

    return status


def main(arguments: Sequence[str] | None = None) -> int:
    arguments = tuple(sys.argv[1:] if arguments is None else arguments)
    error: dict[str, object] = {"schemaVersion": 1}
    try:
        if arguments:
            raise ValueError("Unsupported arguments.")
        command = RecoveryMaintenanceCli.read(sys.stdin.buffer)
        error["operationId"] = command.operation_id.value
        settings = MaintenanceApplicationSettings.model_validate({})
    except RecoveryMaintenanceInputError as failure:
        if failure.operation_id is not None:
            error["operationId"] = failure.operation_id.value
        return _emit(error | {"code": "invalid_input"}, 2)
    except (ValueError, ValidationError, OSError):
        return _emit(error | {"code": "invalid_input"}, 2)

    configure_logging(level=settings.log_level, log_format=settings.log_format, stream=sys.stderr)
    try:
        response = asyncio.run(_execute(command, settings))
    except RecoveryMaintenanceError as failure:
        code = failure.code.value
    except (
        DependencyUnavailableError,
        DatabaseStartupError,
        DatabaseSchemaCompatibilityError,
        OperationalError,
        InterfaceError,
        SqlAlchemyTimeoutError,
        TimeoutError,
        KeyboardInterrupt,
        asyncio.CancelledError,
    ):
        code = RecoveryMaintenanceErrorCode.DEPENDENCY_UNAVAILABLE.value
    except ConflictError:
        code = RecoveryMaintenanceErrorCode.DEPENDENCY_UNAVAILABLE.value
    except Exception as failure:
        code = RecoveryMaintenanceErrorCode.UNEXPECTED_ERROR.value
        with bound_contextvars(operation_id=command.operation_id.value):
            report_unexpected_error(failure, event="maintenance_failed", error_code=code)
    else:
        return _emit(response, 0)

    return _emit(error | {"code": code}, 1)
