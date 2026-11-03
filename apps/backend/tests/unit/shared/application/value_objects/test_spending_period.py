from datetime import UTC, datetime, timedelta, timezone

import pytest

from inframeld_backend.shared.application.value_objects.spending_period import SpendingPeriod


def test_captures_utc_month_instead_of_the_local_calendar_month() -> None:
    instant = datetime(2026, 12, 1, 1, tzinfo=timezone(timedelta(hours=2)))

    assert SpendingPeriod.from_instant(instant) == SpendingPeriod(2026, 11)


def test_rejects_unbound_naive_time() -> None:
    with pytest.raises(ValueError):
        SpendingPeriod.from_instant(datetime(2026, 11, 1))


@pytest.mark.parametrize(("year", "month"), [(0, 1), (2026, 0), (2026, 13), (True, 1)])
def test_rejects_invalid_calendar_period(year: int, month: int) -> None:
    with pytest.raises(ValueError):
        SpendingPeriod(year, month)


def test_month_is_independent_of_time_within_that_utc_month() -> None:
    assert SpendingPeriod.from_instant(
        datetime(2026, 11, 30, 23, 59, tzinfo=UTC)
    ) == SpendingPeriod(2026, 11)
