import pytest

from inframeld_backend.shared.application.enums.job_status import JobStatus
from inframeld_backend.shared.application.services.job_retry_policy import JobRetryPolicy


@pytest.mark.parametrize(
    "attempt, uncertain, expired, expected",
    [
        (1, False, False, JobStatus.QUEUED),
        (3, False, False, JobStatus.FAILED),
        (1, False, True, JobStatus.FAILED),
        (1, True, False, JobStatus.RECOVERY_REQUIRED),
        (3, True, True, JobStatus.RECOVERY_REQUIRED),
    ],
)
def test_interrupted_attempt_only_repeats_established_safe_work(
    attempt: int, uncertain: bool, expired: bool, expected: JobStatus
) -> None:
    assert (
        JobRetryPolicy.after_interruption(
            attempt=attempt, uncertain_effect=uncertain, deadline_expired=expired
        )
        is expected
    )
