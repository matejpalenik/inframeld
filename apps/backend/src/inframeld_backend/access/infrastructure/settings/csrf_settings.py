"""Configure which browser origin may make cookie-authenticated writes"""

from pydantic import BaseModel, HttpUrl, field_validator


class CSRFSettings(BaseModel):
    """Hold trusted browser origins - an empty list denies all writes"""

    trusted_origins: tuple[HttpUrl, ...] = ()

    @field_validator("trusted_origins")
    @classmethod
    def _require_origins(cls, origins: tuple[HttpUrl, ...]) -> tuple[HttpUrl, ...]:
        """Reject page URLs and credentials from the origin allowlist."""

        for origin in origins:
            if (
                origin.path not in ("", "/")
                or origin.query is not None
                or origin.fragment is not None
                or origin.username is not None
                or origin.password is not None
            ):
                raise ValueError(
                    "A trusted CSRF origin must contain only a scheme, host, and optional port."
                )

        return origins
