from datetime import UTC, datetime, timedelta, timezone

import pytest

from inframeld_backend.access.application.value_objects.identity_recovery_cleanup_run_budget import (
    IdentityRecoveryCleanupRunBudget,
)


@pytest.mark.parametrize(
    "at",
    [
        datetime(2026, 10, 26, 12, tzinfo=UTC),
        datetime(2026, 10, 26, 14, tzinfo=timezone(timedelta(hours=2))),
    ],
)
def test_budget_allows_twelve_attempts_within_one_hour_of_the_supplied_instant(
    at: datetime,
) -> None:
    budget = IdentityRecoveryCleanupRunBudget(at)
    assert budget.started_at == at
    assert budget.started_at.tzinfo is UTC
    assert budget.deadline == at + timedelta(hours=1)
    assert budget.max_attempts == 12


def test_naive_start_time_is_rejected() -> None:
    with pytest.raises(ValueError, match="timezone"):
        IdentityRecoveryCleanupRunBudget(datetime(2026, 10, 26, 12))


def test_start_time_without_a_representable_deadline_is_rejected() -> None:
    with pytest.raises(ValueError, match="deadline"):
        IdentityRecoveryCleanupRunBudget(datetime.max.replace(tzinfo=UTC))
