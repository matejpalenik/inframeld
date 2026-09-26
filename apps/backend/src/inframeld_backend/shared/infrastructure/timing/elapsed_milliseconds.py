"""Technical timing helpers used by observability components."""

from time import perf_counter

__all__ = ["elapsed_milliseconds"]


def elapsed_milliseconds(started_at: float) -> float:
    """Return elapsed monotonic time since ``started_at`` in milliseconds."""
    return round((perf_counter() - started_at) * 1000, 2)
