from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class JobQueueStatusDTO:
    """Report bounded ordinary queue health without exposing job inputs."""

    depth: int
    oldest_eligible_age_seconds: float | None
    active: bool
