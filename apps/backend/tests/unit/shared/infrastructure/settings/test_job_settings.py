import pytest
from pydantic import ValidationError

from inframeld_backend.shared.infrastructure.settings.job_settings import JobSettings


@pytest.mark.parametrize(
    "values",
    [
        {"lease_seconds": 121},
        {"poll_seconds": 0},
        {"lease_seconds": float("inf")},
        {"poll_seconds": float("nan")},
        {"work_seconds": 7201},
        {"database_timeout_seconds": 0},
        {"shutdown_seconds": 0},
        {"lease_seconds": 1, "database_timeout_seconds": 5},
    ],
)
def test_unsafe_job_settings_fail_before_worker_start(values: dict[str, float]) -> None:
    with pytest.raises(ValidationError):
        JobSettings.model_validate(values)
