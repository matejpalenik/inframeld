import io
import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import structlog
from sqlalchemy.exc import DBAPIError
from structlog.contextvars import bound_contextvars

from inframeld_backend.access.application.commands.resume_identity_recovery_cleanup_command import (
    ResumeIdentityRecoveryCleanupCommand,
)
from inframeld_backend.access.application.dtos.human_suspension_cleanup_maintenance_result_dto import (
    HumanSuspensionCleanupMaintenanceResultDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_cleanup_resume_result_dto import (
    IdentityRecoveryCleanupResumeResultDTO,
)
from inframeld_backend.access.application.enums.first_administrator_bootstrap_error_code import (
    FirstAdministratorBootstrapErrorCode,
)
from inframeld_backend.access.application.enums.human_suspension_cleanup_execution_state import (
    HumanSuspensionCleanupExecutionState,
)
from inframeld_backend.access.application.enums.identity_recovery_cleanup_resume_outcome import (
    IdentityRecoveryCleanupResumeOutcome,
)
from inframeld_backend.access.application.errors.first_administrator_bootstrap_error import (
    FirstAdministratorBootstrapError,
)
from inframeld_backend.access.cli.mappers.human_suspension_cleanup_maintenance_mapper import (
    HumanSuspensionCleanupMaintenanceMapper,
)
from inframeld_backend.access.cli.mappers.recovery_maintenance_mapper import (
    RecoveryMaintenanceMapper,
)
from inframeld_backend.access.domain.enums.identity_recovery_cleanup_state import (
    IdentityRecoveryCleanupState,
)
from inframeld_backend.bootstrap import maintenance
from inframeld_backend.bootstrap.maintenance_application_settings import (
    MaintenanceApplicationSettings,
)
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.application.errors.restored_job_quarantine_error import (
    RestoredJobQuarantineError,
)
from inframeld_backend.shared.infrastructure.diagnostics.error_reporting import (
    report_unexpected_error,
)
from inframeld_backend.shared.infrastructure.types.log_format import LogFormat


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


def _bootstrap_payload() -> bytes:
    return json.dumps(
        {
            "schemaVersion": 1,
            "mode": "bootstrap-first-administrator",
            "expectedInstallationId": "1ff2c32e-2438-42fc-b2a8-60d4a59ad91a",
            "operationId": "first-claim",
            "operatorLabel": "Operator",
            "reason": "First admission",
            "expectedAccessRevision": 0,
            "expectedIdentityId": "15ad714a-752d-49ef-a9e1-c5d1426df4fa",
            "identityProof": {"kind": "hydra-access-token", "accessToken": "private-proof"},
        }
    ).encode()


def _stdin(monkeypatch: pytest.MonkeyPatch, payload: bytes) -> None:
    monkeypatch.setattr("sys.stdin", io.TextIOWrapper(io.BytesIO(payload), encoding="utf-8"))


def test_invalid_restored_job_request_does_not_echo_unverified_operation_id(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _stdin(
        monkeypatch,
        b'{"schemaVersion":1,"mode":"quarantine-restored-job","operationId":"private-text"}',
    )
    execute = AsyncMock()
    monkeypatch.setattr(maintenance, "_execute", execute)

    assert maintenance.main(()) == 2
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {"schemaVersion": 1, "code": "invalid_input"}
    assert "private-text" not in captured.err
    execute.assert_not_awaited()


def test_restored_job_quarantine_conflict_has_fixed_safe_output(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    operation_id = "1ff2c32e-2438-42fc-b2a8-60d4a59ad91a"
    _stdin(
        monkeypatch,
        json.dumps(
            {
                "schemaVersion": 1,
                "mode": "quarantine-restored-job",
                "intent": "inspect",
                "operationId": operation_id,
                "expectedInstallationId": "3ff2c32e-2438-42fc-b2a8-60d4a59ad91a",
                "jobId": "4ff2c32e-2438-42fc-b2a8-60d4a59ad91a",
                "jobOperationId": "original",
            }
        ).encode(),
    )
    monkeypatch.setenv("INFRAMELD_DATABASE__NAME", "test")
    monkeypatch.setenv("INFRAMELD_DATABASE__USER", "test")
    monkeypatch.setenv("INFRAMELD_DATABASE__PASSWORD", "unused-test-only")
    monkeypatch.setattr(
        maintenance,
        "_execute",
        AsyncMock(side_effect=RestoredJobQuarantineError("private internal cause")),
    )
    assert maintenance.main(()) == 1
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {
        "schemaVersion": 1,
        "operationId": operation_id,
        "code": "restore_quarantine_conflict",
    }
    assert "private internal cause" not in captured.out + captured.err


def test_invalid_input_stops_before_configuration_or_database(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _stdin(monkeypatch, b'{"secret":"never print"}')
    assert maintenance.main(()) == 2
    assert json.loads(capsys.readouterr().out) == {"schemaVersion": 1, "code": "invalid_input"}


def test_bootstrap_requires_private_provider_configuration_before_execution(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _stdin(monkeypatch, _bootstrap_payload())
    monkeypatch.setenv("INFRAMELD_DATABASE__NAME", "test")
    monkeypatch.setenv("INFRAMELD_DATABASE__USER", "test")
    monkeypatch.setenv("INFRAMELD_DATABASE__PASSWORD", "unused-test-only")
    monkeypatch.delenv("INFRAMELD_HYDRA__ADMIN_URL", raising=False)
    monkeypatch.delenv("INFRAMELD_KRATOS__ADMIN_URL", raising=False)
    execute = AsyncMock(return_value={"outcome": "bootstrapped"})
    monkeypatch.setattr(maintenance, "_execute", execute)

    assert maintenance.main(()) == 2
    assert json.loads(capsys.readouterr().out) == {
        "schemaVersion": 1,
        "operationId": "first-claim",
        "code": "invalid_input",
    }
    execute.assert_not_awaited()


def test_bootstrap_controlled_failure_has_only_safe_original_correlation(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _stdin(monkeypatch, _bootstrap_payload())
    for name, value in {
        "INFRAMELD_DATABASE__NAME": "test",
        "INFRAMELD_DATABASE__USER": "test",
        "INFRAMELD_DATABASE__PASSWORD": "unused-test-only",
        "INFRAMELD_KRATOS__PUBLIC_URL": "http://kratos.test:4433",
        "INFRAMELD_KRATOS__ADMIN_URL": "http://kratos.test:4434",
        "INFRAMELD_KRATOS__AUTHORITY": "kratos:test",
        "INFRAMELD_HYDRA__ADMIN_URL": "http://hydra.test:4445",
        "INFRAMELD_HYDRA__ISSUER": "https://hydra.example.test/",
        "INFRAMELD_HYDRA__API_AUDIENCE": "https://api.example.test",
    }.items():
        monkeypatch.setenv(name, value)
    from inframeld_backend.bootstrap.application_settings import get_settings

    monkeypatch.setenv(
        "INFRAMELD_REQUEST_FINGERPRINT__KEY_FILE",
        str(get_settings().request_fingerprint.key_file),
    )
    execute = AsyncMock(
        side_effect=FirstAdministratorBootstrapError(
            FirstAdministratorBootstrapErrorCode.IDENTITY_INELIGIBLE
        )
    )
    monkeypatch.setattr(maintenance, "_execute", execute)

    assert maintenance.main(()) == 1
    result = capsys.readouterr().out
    assert "private-proof" not in result
    assert json.loads(result) == {
        "schemaVersion": 1,
        "operationId": "first-claim",
        "code": "identity_ineligible",
    }


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


def test_suspension_inspection_stdout_has_only_fixed_safe_fields(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    request = {
        "schemaVersion": 1,
        "mode": "human-suspension-cleanup",
        "intent": "inspect",
        "expectedInstallationId": "1ff2c32e-2438-42fc-b2a8-60d4a59ad91a",
        "operationId": "inspect-original",
        "cleanupOperationId": "original",
    }
    payload = json.dumps(request).encode()
    _stdin(monkeypatch, payload)
    monkeypatch.setenv("INFRAMELD_DATABASE__NAME", "test")
    monkeypatch.setenv("INFRAMELD_DATABASE__USER", "test")
    monkeypatch.setenv("INFRAMELD_DATABASE__PASSWORD", "unused-test-only")
    command = HumanSuspensionCleanupMaintenanceMapper.read(payload)
    result = HumanSuspensionCleanupMaintenanceResultDTO(
        command.operation_id,
        command.expected_installation_id,
        command.cleanup_operation_id,
        HumanSuspensionCleanupExecutionState.STOPPED,
        IdentityRecoveryCleanupState.CONFIRMED,
        IdentityRecoveryCleanupState.UNCERTAIN,
        IdentityRecoveryCleanupState.PENDING,
    )
    operation = AsyncMock(return_value=HumanSuspensionCleanupMaintenanceMapper.result(result))
    monkeypatch.setattr(maintenance, "_execute", operation)
    assert maintenance.main(()) == 0
    assert json.loads(capsys.readouterr().out) == {
        "schemaVersion": 1,
        "mode": "human-suspension-cleanup",
        "intent": "inspect",
        "installationId": request["expectedInstallationId"],
        "operationId": "inspect-original",
        "cleanupOperationId": "original",
        "execution": "stopped",
        "steps": {
            "kratosSessions": "confirmed",
            "hydraCliGrants": "uncertain",
            "hydraRememberedLogins": "pending",
        },
    }
    operation.assert_awaited_once()


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


def test_restricted_metadata_mode_uses_safe_output_without_affecting_recovery_configuration(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: "Path"
) -> None:
    request = {
        "schemaVersion": 1,
        "mode": "repair-stranded-authority",
        "expectedInstallationId": "00000000-0000-0000-0000-000000000004",
        "operationId": "metadata-repair",
        "operatorLabel": "Operator",
        "reason": "Repair metadata authority",
        "expectedAccessRevision": 0,
        "expectedIdentityId": "00000000-0000-0000-0000-000000000005",
        "identityProof": {"kind": "hydra-access-token", "accessToken": "private-proof"},
        "responsibility": {
            "kind": "action-grantor",
            "target": {"kind": "project", "projectId": "00000000-0000-0000-0000-000000000003"},
            "actionId": "edit-project-metadata",
        },
    }
    _stdin(monkeypatch, json.dumps(request).encode())
    configuration = {
        "INFRAMELD_DATABASE__NAME": "test",
        "INFRAMELD_DATABASE__USER": "test",
        "INFRAMELD_DATABASE__PASSWORD": "test-only",
        "INFRAMELD_KRATOS__PUBLIC_URL": "http://kratos.test:4433",
        "INFRAMELD_KRATOS__ADMIN_URL": "http://kratos.test:4434",
        "INFRAMELD_KRATOS__AUTHORITY": "kratos:test",
        "INFRAMELD_HYDRA__ADMIN_URL": "http://hydra.test:4445",
        "INFRAMELD_HYDRA__ISSUER": "https://issuer.test",
        "INFRAMELD_HYDRA__API_AUDIENCE": "https://api.test",
        "INFRAMELD_REQUEST_FINGERPRINT__KEY_FILE": str(tmp_path / "fingerprint.key"),
    }
    for key, value in configuration.items():
        monkeypatch.setenv(key, value)
    execute = AsyncMock(
        return_value={
            "schemaVersion": 1,
            "mode": "repair-stranded-authority",
            "operationId": "metadata-repair",
            "outcome": "repaired",
        }
    )
    monkeypatch.setattr(maintenance, "_execute", execute)
    assert maintenance.main(()) == 0
    output = capsys.readouterr().out
    assert json.loads(output)["outcome"] == "repaired"
    assert "private-proof" not in output
    execute.assert_awaited_once()
