import math
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta


@dataclass(frozen=True, slots=True)
class IdentityRecoveryCleanupRunBudget:
    """Bound one recovery cleanup run to twelve attempts within one hour.

    The application supplies a trusted eligibility or authorization time.
    Constructing this value does not authorize cleanup.
    """

    started_at: datetime
    deadline: datetime = field(init=False)
    max_attempts: int = field(init=False, default=12)

    def __post_init__(self) -> None:
        started_at = self._start_in_utc(self.started_at)
        try:
            deadline = started_at + timedelta(hours=1)
        except (OverflowError, ValueError):
            raise ValueError("The cleanup deadline cannot be represented.") from None
        object.__setattr__(self, "started_at", started_at)
        object.__setattr__(self, "deadline", deadline)

    def retry_at(
        self,
        *,
        attempt_number: int,
        failed_at: datetime,
        jitter_seconds: int,
        retry_after_seconds: float | None = None,
    ) -> datetime | None:
        if isinstance(attempt_number, bool) or not 1 <= attempt_number <= self.max_attempts:
            raise ValueError("The attempt must belong to this run's budget.")

        ceiling = min(600, 15 * 2 ** (attempt_number - 1))
        if isinstance(jitter_seconds, bool) or not 1 <= jitter_seconds <= ceiling:
            raise ValueError("The retry delay must be within this attempt's positive ceiling.")

        failed_at = self._start_in_utc(failed_at)
        if failed_at < self.started_at:
            raise ValueError("A failure cannot precede the run.")

        if retry_after_seconds is not None and (
            isinstance(retry_after_seconds, bool)
            or not math.isfinite(retry_after_seconds)
            or retry_after_seconds < 0
        ):
            raise ValueError("The provider delay must be finite and non-negative.")

        delay = max(float(jitter_seconds), retry_after_seconds or 0)
        if (
            attempt_number == self.max_attempts
            or delay >= (self.deadline - failed_at).total_seconds()
        ):
            return None

        return failed_at + timedelta(seconds=delay)

    @staticmethod
    def _start_in_utc(value: object) -> datetime:
        if not isinstance(value, datetime):
            raise TypeError("A cleanup budget requires a datetime start.")
        if value.utcoffset() is None:
            raise ValueError("The cleanup start must include timezone information.")
        try:
            return value.astimezone(UTC)
        except (OverflowError, ValueError):
            raise ValueError("The cleanup deadline cannot be represented.") from None
