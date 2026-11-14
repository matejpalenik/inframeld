import re
from dataclasses import dataclass, field
from typing import ClassVar

from inframeld_backend.shared.domain.validation.value_validation import ValueValidation

_BEARER_VALUE = re.compile(r"[A-Za-z0-9._~+/-]+=*")


@dataclass(frozen=True, slots=True)
class ProviderCredentialValue:
    """Carry one opaque provider token through the protected management boundary."""

    MAX_BYTES: ClassVar[int] = 16_384
    value: str = field(repr=False)

    def __post_init__(self) -> None:
        ValueValidation.require_string(self.value)
        # An accepted value is ASCII, so its length is also its exact encoded size.
        if (
            not 1 <= len(self.value) <= self.MAX_BYTES
            or _BEARER_VALUE.fullmatch(self.value) is None
        ):
            raise ValueError("Use a supported provider bearer token.")
