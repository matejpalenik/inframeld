import io
import json
from uuid import UUID

import pytest

from inframeld_backend.access.cli.errors.stranded_authority_maintenance_input_error import (
    StrandedAuthorityMaintenanceInputError,
)
from inframeld_backend.access.cli.maintenance_cli import MaintenanceCli
from inframeld_backend.access.cli.mappers.restored_job_quarantine_mapper import (
    RestoredJobQuarantineMapper,
)
from inframeld_backend.shared.application.commands.restored_job_quarantine_command import (
    RestoredJobQuarantineCommand,
)
from inframeld_backend.shared.application.dtos.restored_job_quarantine_result_dto import (
    RestoredJobQuarantineResultDTO,
)
from inframeld_backend.shared.application.enums.restored_job_quarantine_intent import (
    RestoredJobQuarantineIntent as Intent,
)
from inframeld_backend.shared.application.value_objects.job_id import JobId
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.domain.enums.job_status import JobStatus
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


def _request() -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "mode": "quarantine-restored-job",
        "intent": "quarantine",
        "operationId": str(UUID(int=1)),
        "expectedInstallationId": str(UUID(int=2)),
        "jobId": str(UUID(int=3)),
        "jobOperationId": "original-job",
        "expectedStatus": "queued",
        "expectedAttempt": 0,
        "operatorLabel": "Recovery operator",
        "reason": "Post-cut effects cannot be ruled out",
    }


def test_protected_dispatch_preserves_exact_original_job_and_reviewed_state() -> None:
    request = _request()
    command = MaintenanceCli.read(io.BytesIO(json.dumps(request).encode()))
    assert command == RestoredJobQuarantineCommand(
        OperationId(str(UUID(int=1))),
        InstallationId(UUID(int=2)),
        JobId(UUID(int=3)),
        OperationId("original-job"),
        Intent.QUARANTINE,
        JobStatus.QUEUED,
        0,
        "Recovery operator",
        "Post-cut effects cannot be ruled out",
    )


def test_inspection_has_no_expected_state_or_attribution() -> None:
    request = _request()
    request["intent"] = "inspect"
    for field in ("expectedStatus", "expectedAttempt", "operatorLabel", "reason"):
        del request[field]
    assert MaintenanceCli.read(
        io.BytesIO(json.dumps(request).encode())
    ) == RestoredJobQuarantineCommand(
        OperationId(str(UUID(int=1))),
        InstallationId(UUID(int=2)),
        JobId(UUID(int=3)),
        OperationId("original-job"),
        Intent.INSPECT,
    )


def test_result_exposes_only_the_exact_job_and_safe_review_state() -> None:
    command = RestoredJobQuarantineMapper.read(_request())
    result = RestoredJobQuarantineResultDTO(JobStatus.RECOVERY_REQUIRED, 0, False)
    assert RestoredJobQuarantineMapper.result(command, result) == {
        "schemaVersion": 1,
        "mode": "quarantine-restored-job",
        "intent": "quarantine",
        "operationId": str(UUID(int=1)),
        "installationId": str(UUID(int=2)),
        "jobId": str(UUID(int=3)),
        "jobOperationId": "original-job",
        "status": "recovery_required",
        "attempt": 0,
        "eligible": False,
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schemaVersion", True),
        ("operationId", "operator-supplied-label"),
        ("expectedStatus", "succeeded"),
        ("expectedAttempt", True),
        ("expectedAttempt", 4),
        ("expectedAttempt", -1),
        ("operatorLabel", "  "),
        ("reason", "x" * 513),
        ("resume", True),
    ],
)
def test_rejects_unreviewed_or_malformed_protected_input(field: str, value: object) -> None:
    request = _request()
    request[field] = value
    with pytest.raises(StrandedAuthorityMaintenanceInputError):
        MaintenanceCli.read(io.BytesIO(json.dumps(request).encode()))
