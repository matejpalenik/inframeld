import re
import unicodedata
from dataclasses import dataclass

from inframeld_backend.shared.domain.validation.value_validation import ValueValidation


@dataclass(frozen=True, slots=True)
class ResourceName:
    """Carry an exact selector. Suggestions never allocate or normalize lookup input."""

    value: str

    def __post_init__(self) -> None:
        ValueValidation.require_string(self.value)
        if (
            not 1 <= len(self.value) <= 63
            or re.fullmatch(r"[a-z](?:[a-z0-9-]*[a-z0-9])?", self.value) is None
        ):
            raise ValueError(
                "A resource name requires 1–63 lowercase ASCII characters with a valid start and end."
            )

    @staticmethod
    def suggest(display_name: str) -> "ResourceName | None":
        ValueValidation.require_string(display_name)
        decomposed = unicodedata.normalize("NFKD", display_name)
        plain = "".join(c for c in decomposed if not unicodedata.combining(c))
        ascii_lower = plain.translate(
            str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")
        )
        preview = re.sub(r"[^a-z0-9]+", "-", ascii_lower).strip("-")
        try:
            return ResourceName(preview)
        except ValueError:
            return None
