from dataclasses import dataclass, field
from typing import ClassVar

from inframeld_backend.shared.domain.validation.value_validation import ValueValidation


@dataclass(frozen=True, slots=True)
class SuspensionReason:
    """Preserve bounded single-line audit text without displaying it in repr."""

    MAX_LENGTH: ClassVar[int] = 512
    value: str = field(repr=False)

    def __post_init__(self) -> None:
        ValueValidation.require_string(self.value)
        if (
            not self.value
            or self.value != self.value.strip()
            or len(self.value) > self.MAX_LENGTH
            or any(
                ord(char) < 32 or ord(char) == 127 or char in "\x85\u2028\u2029"
                for char in self.value
            )
        ):
            raise ValueError("The audit reference must be bounded, nonblank single-line text.")
        try:
            self.value.encode("utf-8")
        except UnicodeEncodeError:
            raise ValueError("The audit reference must be valid UTF-8 text.") from None
