"""Keep numeric revisions exact in every supported application client."""

from typing import ClassVar


class RevisionValidation:
    """Validate counters in JSON's interoperable nonnegative integer range."""

    MAX_VALUE: ClassVar[int] = 2**53 - 1

    @staticmethod
    def require(value: int) -> None:
        if type(value) is not int:
            raise TypeError("A revision must be a whole number.")
        if not 0 <= value <= RevisionValidation.MAX_VALUE:
            raise ValueError("A revision is outside the supported integer range.")
