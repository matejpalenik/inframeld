from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class IdentityRecoveryCleanupRunDTO:
    id: UUID
    authorized_at: datetime
    deadline: datetime
    next_attempt_at: datetime
    max_attempts: int
    consumed_attempts: int
    ended_at: datetime | None
    terminal_reason: str | None
