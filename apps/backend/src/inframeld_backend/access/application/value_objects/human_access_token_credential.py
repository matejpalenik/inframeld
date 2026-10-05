from dataclasses import dataclass, field

from inframeld_backend.shared.domain.validation.value_validation import require_string


@dataclass(frozen=True, slots=True)
class HumanAccessTokenCredential:
    """Carry an untrusted human token without exposing it in representations."""

    value: str = field(repr=False)

    def __post_init__(self) -> None:
        require_string(self.value)

        if not self.value.strip():
            raise ValueError("An access token credential must be nonblank.")

        if self.value.startswith("ifm_app_"):
            raise ValueError("An application key is not a human access token credential.")
