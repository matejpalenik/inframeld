from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ArtifactCapacityDTO:
    """Observe physical headroom separately from durable application reservations."""

    usable_bytes: int
    free_bytes: int
    backup_reserved_bytes: int = 0
