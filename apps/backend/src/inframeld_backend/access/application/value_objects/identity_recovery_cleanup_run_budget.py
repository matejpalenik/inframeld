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
