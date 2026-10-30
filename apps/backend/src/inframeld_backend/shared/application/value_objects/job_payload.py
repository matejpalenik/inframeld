from dataclasses import dataclass, field
from re import fullmatch

from inframeld_backend.shared.domain.validation.value_validation import ValueValidation


@dataclass(frozen=True, slots=True)
class JobPayload:
    """Keep one immutable, bounded versioned handler input out of diagnostics."""

    kind: str
    version: int
    data: bytes = field(repr=False)

    def __post_init__(self) -> None:
        ValueValidation.require_string(self.kind)
        if fullmatch(r"[a-z][a-z0-9_.-]{0,99}", self.kind) is None:
            raise ValueError("A job kind must be a bounded application identifier.")
        if type(self.version) is not int or not 1 <= self.version <= 65535:
            raise ValueError("A job payload version must be a positive bounded integer.")
        self._require_data(self.data)

    @staticmethod
    def _require_data(data: object) -> None:
        if not isinstance(data, bytes) or len(data) > 65536:
            raise ValueError("A job payload must contain at most 64 KiB of immutable bytes.")
