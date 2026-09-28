"""Identify an application operation without prescribing its external encoding."""

from dataclasses import dataclass

from inframeld_backend.shared.domain.validation.value_validation import require_string


@dataclass(frozen=True, slots=True)
class OperationId:
    """Carry a nonblank opaque operation identity used for diagnostic correlation."""

    value: str

    def __post_init__(self) -> None:
        require_string(self.value)
        if not self.value.strip():
            raise ValueError("Operation ID must not be blank.")
