"""Validate runtime primitives before storing them inside nominal domain values."""

from uuid import UUID


class ValueValidation:
    """Check shared runtime types before values enforce their own invariants."""

    @staticmethod
    def require_uuid(value: object) -> None:
        """Reject unparsed input, including another ID wrapper, at value construction."""
        if not isinstance(value, UUID):
            raise TypeError("An identifier requires a parsed UUID.")

    @staticmethod
    def require_string(value: object) -> None:
        """Reject non-text input without including potentially sensitive contents."""
        if not isinstance(value, str):
            raise TypeError("A text value requires a string.")
