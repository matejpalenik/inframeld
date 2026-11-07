from datetime import datetime


class ApplicationKeyCredentialPolicy:
    """Reject expired or revoked credentials at the current protected boundary."""

    @staticmethod
    def is_current(
        *,
        binding_matches: bool,
        checked_at: datetime,
        expires_at: datetime | None,
        revoked_at: datetime | None,
    ) -> bool:
        return (
            binding_matches
            and expires_at is not None
            and checked_at < expires_at
            and revoked_at is None
        )
