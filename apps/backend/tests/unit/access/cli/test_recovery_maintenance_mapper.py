import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from inframeld_backend.access.application.dtos.identity_recovery_cleanup_resume_result_dto import (
    IdentityRecoveryCleanupResumeResultDTO,
)
from inframeld_backend.access.application.enums.identity_recovery_cleanup_resume_outcome import (
    IdentityRecoveryCleanupResumeOutcome,
)
from inframeld_backend.access.cli.mappers.recovery_maintenance_mapper import (
    RecoveryMaintenanceMapper,
)


def _request() -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "mode": "resume-recovery-cleanup",
        "expectedInstallationId": "1ff2c32e-2438-42fc-b2a8-60d4a59ad91a",
        "operationId": "operator-request-1",
        "recoveryOperationId": "original-recovery",
        "operatorLabel": "Alice's deployment operator",
        "reason": "Hydra connectivity repaired",
    }


def test_read_retains_exact_meaning_and_canonical_installation() -> None:
    request = _request()
    request["expectedInstallationId"] = "{1FF2C32E-2438-42FC-B2A8-60D4A59AD91A}"
    request["reason"] = "  Hydra repaired  "
    command = RecoveryMaintenanceMapper.read(json.dumps(request).encode())
    assert str(command.expected_installation_id.value) == "1ff2c32e-2438-42fc-b2a8-60d4a59ad91a"
    assert command.reason == "  Hydra repaired  "
    assert command.operation_id.value == "operator-request-1"


@pytest.mark.parametrize("value", [True, 1.0, "1", 2, None])
def test_schema_version_requires_integer_token_one(value: object) -> None:
    request = _request()
    request["schemaVersion"] = value
    with pytest.raises(ValueError):
        RecoveryMaintenanceMapper.read(json.dumps(request).encode())


@pytest.mark.parametrize(
    "change",
    [
        {"extra": "secret"},
        {"mode": "bootstrap"},
        {"reason": " "},
        {"reason": "x" * 513},
        {"operatorLabel": "x" * 129},
        {"operationId": "x" * 129},
        {"operationId": 4},
        {"recoveryOperationId": " "},
        {"expectedInstallationId": "not-a-uuid"},
    ],
)
def test_invalid_requests_fail_without_reflecting_values(change: dict[str, object]) -> None:
    request = _request() | change
    with pytest.raises(ValueError) as error:
        RecoveryMaintenanceMapper.read(json.dumps(request).encode())
    assert "secret" not in str(error.value)


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        b"null",
        b"[]",
        b"{} {}",
        b"\xff",
        b'{"schemaVersion":1,"schemaVersion":1}',
        b'{"a":NaN}',
        b" " * 65_537,
    ],
)
def test_invalid_json_and_size_are_rejected(payload: bytes) -> None:
    with pytest.raises(ValueError):
        RecoveryMaintenanceMapper.read(payload)


def test_exact_byte_limit_is_accepted() -> None:
    encoded = json.dumps(_request()).encode()
    RecoveryMaintenanceMapper.read(encoded + b" " * (65_536 - len(encoded)))


@pytest.mark.parametrize("outcome", list(IdentityRecoveryCleanupResumeOutcome))
def test_result_mapping_omits_run_for_no_work(
    outcome: IdentityRecoveryCleanupResumeOutcome,
) -> None:
    command = RecoveryMaintenanceMapper.read(json.dumps(_request()).encode())
    run_id = uuid4() if outcome is IdentityRecoveryCleanupResumeOutcome.AUTHORIZED else None
    deadline = datetime(2026, 10, 26, 12, tzinfo=UTC) if run_id is not None else None
    result = IdentityRecoveryCleanupResumeResultDTO(
        command.operation_id,
        command.expected_installation_id,
        command.recovery_operation_id,
        outcome,
        False,
        run_id,
        deadline,
    )
    response = RecoveryMaintenanceMapper.result(result)
    assert response["schemaVersion"] == 1
    assert response["mode"] == "resume-recovery-cleanup"
    assert response["released"] is False
    assert response["operationId"] == command.operation_id.value
    if run_id is None:
        assert "runId" not in response and "deadline" not in response
    else:
        assert response["runId"] == str(run_id)
        assert response["deadline"] == "2026-10-26T12:00:00Z"


@pytest.mark.parametrize("field", ["operationId", "operatorLabel", "reason", "recoveryOperationId"])
@pytest.mark.parametrize("value", ["unusable\x00text", "unusable\ud800text"])
def test_text_must_be_representable_in_postgres(field: str, value: str) -> None:
    request = _request() | {field: value}
    with pytest.raises(ValueError):
        RecoveryMaintenanceMapper.read(json.dumps(request).encode())
