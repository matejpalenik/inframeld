from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True, slots=True)
class SpendingPeriod:
    """Keep a call in the UTC calendar month captured by its reservation."""

    year: int
    month: int

    def __post_init__(self) -> None:
        if type(self.year) is not int or type(self.month) is not int:
            raise ValueError("A spending period requires integer calendar fields.")
        datetime(self.year, self.month, 1, tzinfo=UTC)

    @staticmethod
    def from_instant(instant: datetime) -> SpendingPeriod:
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise ValueError("A spending period requires an aware instant.")
        captured = instant.astimezone(UTC)
        return SpendingPeriod(captured.year, captured.month)
