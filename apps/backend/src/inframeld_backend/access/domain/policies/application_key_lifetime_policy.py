from datetime import datetime, timedelta
from typing import ClassVar


class ApplicationKeyLifetimePolicy:
    """Bound fresh expiry arithmetic before allocating an incoming credential."""

    MAXIMUM_SECONDS: ClassVar[int] = 2**53 - 1

    @staticmethod
    def expires_at(
        *, issued_at: datetime, lifetime_seconds: int, maximum_lifetime_seconds: int
    ) -> datetime:
        for seconds in (lifetime_seconds, maximum_lifetime_seconds):
            if (
                type(seconds) is not int
                or not 0 < seconds <= ApplicationKeyLifetimePolicy.MAXIMUM_SECONDS
            ):
                raise ValueError("Application-key lifetimes require positive exact whole seconds.")
        if lifetime_seconds > maximum_lifetime_seconds:
            raise ValueError("The application-key lifetime exceeds the configured maximum.")
        if issued_at.tzinfo is None or issued_at.utcoffset() != timedelta(0):
            raise ValueError("Application-key expiry requires the database UTC observation.")
        try:
            return issued_at + timedelta(seconds=lifetime_seconds)
        except OverflowError:
            raise ValueError("The application-key expiry cannot be represented.") from None
