from datetime import UTC, datetime, timedelta

import pytest

from inframeld_backend.access.application.value_objects.identity_recovery_cleanup_run_budget import (
    IdentityRecoveryCleanupRunBudget,
)

START = datetime(2026, 10, 26, tzinfo=UTC)


@pytest.mark.parametrize("attempt,ceiling", [(1, 15), (2, 30), (3, 60), (7, 600), (11, 600)])
def test_positive_jitter_and_retry_after_choose_one_bounded_time(
    attempt: int, ceiling: int
) -> None:
    budget = IdentityRecoveryCleanupRunBudget(START)
    assert budget.retry_at(
        attempt_number=attempt, failed_at=START, jitter_seconds=ceiling
    ) == START + timedelta(seconds=ceiling)
    assert budget.retry_at(
        attempt_number=attempt, failed_at=START, jitter_seconds=1, retry_after_seconds=700
    ) == START + timedelta(seconds=700)


def test_exhausted_attempt_or_deadline_never_dispatches_again() -> None:
    budget = IdentityRecoveryCleanupRunBudget(START)
    assert budget.retry_at(attempt_number=12, failed_at=START, jitter_seconds=1) is None
    assert (
        budget.retry_at(
            attempt_number=1, failed_at=budget.deadline - timedelta(seconds=1), jitter_seconds=1
        )
        is None
    )
    assert (
        budget.retry_at(
            attempt_number=1, failed_at=START, jitter_seconds=1, retry_after_seconds=3600
        )
        is None
    )


@pytest.mark.parametrize("attempt,jitter", [(0, 1), (13, 1), (True, 1), (1, 0), (1, 16), (1, True)])
def test_invalid_attempt_and_jitter_are_rejected(attempt: int, jitter: int) -> None:
    with pytest.raises(ValueError):
        IdentityRecoveryCleanupRunBudget(START).retry_at(
            attempt_number=attempt, failed_at=START, jitter_seconds=jitter
        )
