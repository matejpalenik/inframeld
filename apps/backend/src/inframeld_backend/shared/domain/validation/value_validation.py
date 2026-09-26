"""Validate runtime primitives before storing them inside nominal domain values."""

from uuid import UUID


def require_uuid(value: object) -> None:
    """Reject unparsed input, including another ID wrapper, at value construction."""
    if not isinstance(value, UUID):
        raise TypeError("An identifier requires a parsed UUID.")


def require_string(value: object) -> None:
    """Reject non-text input without including potentially sensitive contents."""
    if not isinstance(value, str):
        raise TypeError("A text value requires a string.")
