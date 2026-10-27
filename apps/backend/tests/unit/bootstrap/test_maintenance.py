import io
import json
import logging
import os
import subprocess
import sys
from unittest.mock import AsyncMock

import pytest
import structlog
from sqlalchemy.exc import DBAPIError
from structlog.contextvars import bound_contextvars

from inframeld_backend.access.application.commands.resume_identity_recovery_cleanup_command import (
    ResumeIdentityRecoveryCleanupCommand,
)
from inframeld_backend.access.application.dtos.identity_recovery_cleanup_resume_result_dto import (
    IdentityRecoveryCleanupResumeResultDTO,
)
from inframeld_backend.access.application.enums.identity_recovery_cleanup_resume_outcome import (
    IdentityRecoveryCleanupResumeOutcome,
)
from inframeld_backend.access.cli.mappers.recovery_maintenance_mapper import (
    RecoveryMaintenanceMapper,
)
from inframeld_backend.bootstrap import maintenance
from inframeld_backend.bootstrap.maintenance_application_settings import (
    MaintenanceApplicationSettings,
)
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.infrastructure.diagnostics.error_reporting import (
    report_unexpected_error,
)
from inframeld_backend.shared.infrastructure.types.logging_types import LogFormat


def _payload() -> bytes:
    return json.dumps(
        {
            "schemaVersion": 1,
            "mode": "resume-recovery-cleanup",
            "expectedInstallationId": "1ff2c32e-2438-42fc-b2a8-60d4a59ad91a",
            "operationId": "operator-request",
            "recoveryOperationId": "original",
            "operatorLabel": "Operator",
            "reason": "Provider fixed",
        }
    ).encode()


def _stdin(monkeypatch: pytest.MonkeyPatch, payload: bytes) -> None:
    monkeypatch.setattr("sys.stdin", io.TextIOWrapper(io.BytesIO(payload), encoding="utf-8"))


def test_invalid_input_stops_before_configuration_or_database(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _stdin(monkeypatch, b'{"secret":"never print"}')
    assert maintenance.main(()) == 2
    assert json.loads(capsys.readouterr().out) == {"schemaVersion": 1, "code": "invalid_input"}


def test_unsupported_arguments_fail_safely(capsys: pytest.CaptureFixture[str]) -> None:
    assert maintenance.main(("--operator=secret",)) == 2
    assert "secret" not in capsys.readouterr().out


def test_configuration_failure_has_safe_parsed_request_id(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _stdin(monkeypatch, _payload())
    monkeypatch.setenv("INFRAMELD_DATABASE__PORT", "secret-invalid")
    assert maintenance.main(()) == 2
    assert json.loads(capsys.readouterr().out) == {
        "schemaVersion": 1,
        "operationId": "operator-request",
        "code": "invalid_input",
    }


@pytest.mark.parametrize(
    "error", [DependencyUnavailableError("secret"), RuntimeError("secret"), KeyboardInterrupt()]
)
def test_failures_never_reflect_diagnostics(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], error: BaseException
) -> None:
    _stdin(monkeypatch, _payload())
    monkeypatch.setenv("INFRAMELD_DATABASE__NAME", "test")
    monkeypatch.setenv("INFRAMELD_DATABASE__USER", "test")
    monkeypatch.setenv("INFRAMELD_DATABASE__PASSWORD", "secret")
    operation = AsyncMock(side_effect=error)
    monkeypatch.setattr(maintenance, "_execute", operation, raising=False)
    assert maintenance.main(()) == 1
    output = capsys.readouterr().out
    assert "secret" not in output
    assert json.loads(output)["operationId"] == "operator-request"
    operation.assert_awaited_once()


def test_successful_command_emits_one_result(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _stdin(monkeypatch, _payload())
    monkeypatch.setenv("INFRAMELD_DATABASE__NAME", "test")
    monkeypatch.setenv("INFRAMELD_DATABASE__USER", "test")
    monkeypatch.setenv("INFRAMELD_DATABASE__PASSWORD", "secret")
    command = RecoveryMaintenanceMapper.read(_payload())
    result = IdentityRecoveryCleanupResumeResultDTO(
        command.operation_id,
        command.expected_installation_id,
        command.recovery_operation_id,
        IdentityRecoveryCleanupResumeOutcome.ALREADY_COMPLETED,
        True,
    )
    monkeypatch.setattr(
        maintenance,
        "_execute",
        AsyncMock(return_value=RecoveryMaintenanceMapper.result(result)),
        raising=False,
    )
    assert maintenance.main(()) == 0
    assert json.loads(capsys.readouterr().out)["outcome"] == "already-completed"


@pytest.mark.parametrize("log_format", ["json", "console"])
@pytest.mark.parametrize("already_reported", [False, True])
def test_unexpected_failure_has_one_safe_diagnostic_and_original_stdout_result(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    log_format: LogFormat,
    already_reported: bool,
) -> None:
    """An unlogged failure needs a diagnostic, while a reported failure keeps its original one."""
    _stdin(monkeypatch, _payload())
    monkeypatch.setenv("INFRAMELD_DATABASE__NAME", "test")
    monkeypatch.setenv("INFRAMELD_DATABASE__USER", "test")
    monkeypatch.setenv("INFRAMELD_DATABASE__PASSWORD", "unused-test-only")
    monkeypatch.setenv("INFRAMELD_LOG_FORMAT", log_format)
    monkeypatch.setenv("INFRAMELD_LOG_LEVEL", "ERROR")

    async def execute(
        command: ResumeIdentityRecoveryCleanupCommand, _settings: MaintenanceApplicationSettings
    ) -> dict[str, object]:
        try:
            try:
                raise DBAPIError(
                    statement="SELECT synthetic_private_statement",
                    params={"private_value": "synthetic-private-parameter"},
                    orig=RuntimeError("synthetic-private-driver-text"),
                    hide_parameters=True,
                )
            except DBAPIError as cause:
                raise RuntimeError("synthetic-private-message") from cause
        except RuntimeError as failure:
            if already_reported:
                with bound_contextvars(operation_id=command.operation_id.value):
                    report_unexpected_error(
                        failure,
                        event="maintenance_operation_failed",
                        error_code="unexpected_error",
                    )
            raise

    monkeypatch.setattr(maintenance, "_execute", execute)
    assert maintenance.main(()) == 1

    captured = capsys.readouterr()
    assert len(captured.out.splitlines()) == 1
    assert json.loads(captured.out) == {
        "schemaVersion": 1,
        "operationId": "operator-request",
        "code": "unexpected_error",
    }
    event = "maintenance_operation_failed" if already_reported else "maintenance_failed"
    assert captured.err.count(event) == 1
    assert captured.err.count("maintenance_failed") == (0 if already_reported else 1)
    assert captured.err.count("operator-request") == 1
    assert "unexpected_error" in captured.err
    assert "RuntimeError" in captured.err and "DBAPIError" in captured.err
    if log_format == "json":
        diagnostic = json.loads(captured.err)
        assert diagnostic["event"] == event
        assert diagnostic["operation_id"] == "operator-request"
        assert diagnostic["error_code"] == "unexpected_error"
        assert "request_id" not in diagnostic

    for secret in (
        "synthetic_private_statement",
        "synthetic-private-parameter",
        "synthetic-private-driver-text",
        "synthetic-private-message",
        "unused-test-only",
    ):
        assert secret not in captured.out + captured.err


@pytest.mark.parametrize("log_format", ["json", "console"])
@pytest.mark.parametrize("unavailable", [False, True])
def test_operation_diagnostics_leave_one_stdout_result(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    log_format: LogFormat,
    unavailable: bool,
) -> None:
    _stdin(monkeypatch, _payload())
    monkeypatch.setenv("INFRAMELD_DATABASE__NAME", "test")
    monkeypatch.setenv("INFRAMELD_DATABASE__USER", "test")
    monkeypatch.setenv("INFRAMELD_DATABASE__PASSWORD", "unused-test-only")
    monkeypatch.setenv("INFRAMELD_LOG_FORMAT", log_format)
    monkeypatch.setenv("INFRAMELD_LOG_LEVEL", "ERROR")
    command = RecoveryMaintenanceMapper.read(_payload())
    response = RecoveryMaintenanceMapper.result(
        IdentityRecoveryCleanupResumeResultDTO(
            command.operation_id,
            command.expected_installation_id,
            command.recovery_operation_id,
            IdentityRecoveryCleanupResumeOutcome.ALREADY_COMPLETED,
            True,
        )
    )
    calls: list[ResumeIdentityRecoveryCleanupCommand] = []

    async def execute(
        requested: ResumeIdentityRecoveryCleanupCommand, _settings: MaintenanceApplicationSettings
    ) -> dict[str, object]:
        calls.append(requested)
        try:
            raise DBAPIError(
                statement="SELECT :private_value",
                params={"private_value": "synthetic-private-parameter"},
                orig=RuntimeError("synthetic-private-driver-text"),
                hide_parameters=True,
            )
        except DBAPIError:
            logging.getLogger("sqlalchemy.pool.impl.AsyncAdaptedQueuePool").exception(
                "maintenance_database_diagnostic"
            )
            structlog.get_logger("maintenance.output_test").exception(
                "maintenance_operation_diagnostic"
            )

        if unavailable:
            raise DependencyUnavailableError("synthetic-private-dependency-text")

        return response

    monkeypatch.setattr(maintenance, "_execute", execute)
    assert maintenance.main(()) == (1 if unavailable else 0)
    captured = capsys.readouterr()
    expected = (
        {"schemaVersion": 1, "operationId": "operator-request", "code": "dependency_unavailable"}
        if unavailable
        else response
    )
    assert json.loads(captured.out) == expected
    assert "maintenance_database_diagnostic" in captured.err
    assert "maintenance_operation_diagnostic" in captured.err
    assert "DBAPIError" in captured.err
    assert calls == [command]

    for secret in (
        "synthetic-private-parameter",
        "synthetic-private-driver-text",
        "synthetic-private-dependency-text",
    ):
        assert secret not in captured.out + captured.err


def _run_with_closed_stdout(*, complete_operation: bool) -> tuple[int, bytes, bytes]:
    observed, observation = os.pipe()
    process: subprocess.Popen[bytes] | None = None
    try:
        command = [sys.executable, "-B", "-m", "inframeld_backend.maintenance"]
        if complete_operation:
            command = [
                sys.executable,
                "-B",
                "-c",
                """
import os
import sys
from datetime import UTC, datetime
from uuid import UUID

from inframeld_backend.access.application.commands.resume_identity_recovery_cleanup_command import ResumeIdentityRecoveryCleanupCommand
from inframeld_backend.access.application.dtos.identity_recovery_cleanup_resume_result_dto import IdentityRecoveryCleanupResumeResultDTO
from inframeld_backend.access.application.enums.identity_recovery_cleanup_resume_outcome import IdentityRecoveryCleanupResumeOutcome
from inframeld_backend.access.cli.mappers.recovery_maintenance_mapper import RecoveryMaintenanceMapper
from inframeld_backend.bootstrap import maintenance
from inframeld_backend.bootstrap.maintenance_application_settings import MaintenanceApplicationSettings

async def complete(command: ResumeIdentityRecoveryCleanupCommand, settings: MaintenanceApplicationSettings) -> dict[str, object]:
    os.write(int(sys.argv[1]), b"accepted\\n")
    return RecoveryMaintenanceMapper.result(IdentityRecoveryCleanupResumeResultDTO(
        command.operation_id, command.expected_installation_id, command.recovery_operation_id,
        IdentityRecoveryCleanupResumeOutcome.AUTHORIZED, False,
        UUID("868d9dbf-562a-4163-862b-23a6b0954b21"), datetime(2026, 10, 26, 12, tzinfo=UTC),
    ))

maintenance._execute = complete
raise SystemExit(maintenance.main(()))
""",
                str(observation),
            ]
        environment = {
            key: value for key, value in os.environ.items() if not key.startswith("INFRAMELD_")
        }
        environment.update(
            {
                "INFRAMELD_DATABASE__NAME": "unused",
                "INFRAMELD_DATABASE__USER": "unused",
                "INFRAMELD_DATABASE__PASSWORD": "unused-test-only",
                "PYTHONDONTWRITEBYTECODE": "1",
            }
        )
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=environment,
            pass_fds=(observation,),
        )
        assert process.stdout is not None
        process.stdout.close()
        process.stdout = None
        _, stderr = process.communicate(_payload() if complete_operation else b"{}", timeout=10)
        assert process.returncode is not None
        os.close(observation)
        observation = -1
        return process.returncode, stderr, os.read(observed, 1024)
    finally:
        try:
            if process is not None and process.poll() is None:
                process.kill()
                process.communicate(timeout=10)
        finally:
            if observation != -1:
                os.close(observation)
            os.close(observed)


@pytest.mark.parametrize("complete_operation", [False, True])
def test_closed_stdout_preserves_exit_code_without_repeating_work(
    complete_operation: bool,
) -> None:
    status, stderr, observed = _run_with_closed_stdout(complete_operation=complete_operation)
    assert status == 1
    assert stderr == b""
    assert observed == (b"accepted\n" if complete_operation else b"")


def test_valid_correlation_survives_an_unsupported_mode(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    request = json.loads(_payload())
    request["mode"] = "bootstrap"
    _stdin(monkeypatch, json.dumps(request).encode())
    assert maintenance.main(()) == 2
    assert json.loads(capsys.readouterr().out) == {
        "schemaVersion": 1,
        "operationId": "operator-request",
        "code": "invalid_input",
    }
