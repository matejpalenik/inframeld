from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True, slots=True)
class RecoveryHookCredentials:
    current: bytes = field(repr=False)
    retiring: bytes | None = field(default=None, repr=False)
    retiring_accept_until: datetime | None = None
