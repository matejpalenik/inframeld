"""Validate discovery configuration without rewriting its public identities."""

import re
from contextlib import suppress
from urllib.parse import unquote, urlsplit

from pydantic import AnyHttpUrl

_INVALID_URL = "Expected a canonical public HTTPS URL without credentials, query or fragment."


class PydanticDiscoveryURLVerifier:
    """Check discovery URLs and endpoint equivalence using the maintained URL parser.

    Parsed values are temporary observations. Callers retain the original identity
    strings, and these checks perform no DNS lookup or network request.
    """

    @staticmethod
    def require_public(value: str, *, managed_local: bool = False) -> None:
        """Reject unsafe identifiers before parser normalization can repair their syntax."""
        if len(value.encode("utf-8")) > 8192:
            raise ValueError(_INVALID_URL)

        raw = None
        decoded_path = ""
        try:
            raw = urlsplit(value)
            _ = raw.port
            decoded_path = unquote(raw.path, errors="strict")
        except ValueError:
            raw = None

        scheme, separator, _ = value.partition("://")
        if (
            raw is None
            or separator != "://"
            or scheme.lower() not in {"http", "https"}
            or re.search(r"%(?![0-9A-Fa-f]{2})", raw.path) is not None
            or not raw.hostname
            or any(
                character.isspace() or ord(character) < 32 or 127 <= ord(character) <= 159
                for character in value
            )
            or raw.username is not None
            or raw.password is not None
            or "?" in value
            or "#" in value
            or "\\" in value
            or any(
                ord(character) < 32 or 127 <= ord(character) <= 159 or character == "\\"
                for character in decoded_path
            )
            or any(part in {".", ".."} for part in decoded_path.split("/"))
        ):
            raise ValueError(_INVALID_URL)

        parsed = PydanticDiscoveryURLVerifier._parse(value)
        if managed_local:
            if not value.startswith("http://") or raw.hostname != "127.0.0.1":
                raise ValueError("Managed discovery requires literal IPv4 loopback HTTP.")
        elif parsed.scheme != "https":
            raise ValueError(_INVALID_URL)

    @staticmethod
    def require_not_admin(public: str, private: str) -> None:
        """Reject equivalent configured admin endpoints without banning their whole origin."""
        exposed = PydanticDiscoveryURLVerifier._parse(public)
        admin = PydanticDiscoveryURLVerifier._parse(private)
        if (
            exposed.scheme == admin.scheme
            and exposed.host == admin.host
            and exposed.port == admin.port
            and (exposed.path or "").rstrip("/") == (admin.path or "").rstrip("/")
        ):
            raise ValueError(
                "Public discovery cannot advertise a provider administration endpoint."
            )

    @staticmethod
    def _parse(value: str) -> AnyHttpUrl:
        """Discard parser exceptions that can retain the supplied operator input."""
        parsed = None
        with suppress(ValueError):
            parsed = AnyHttpUrl(value)

        if parsed is None or parsed.host is None:
            raise ValueError(_INVALID_URL)

        return parsed
