from dataclasses import dataclass
from ipaddress import IPv4Address, IPv6Address, ip_address
from re import fullmatch
from urllib.parse import urlsplit

from inframeld_backend.access.domain.enums.model_connection_authentication import (
    ModelConnectionAuthentication,
)
from inframeld_backend.access.domain.enums.model_connection_provider import ModelConnectionProvider

_METADATA_HOSTS = frozenset(
    {"metadata", "metadata.google.internal", "instance-data", "instance-data.ec2.internal"}
)
_METADATA_ADDRESSES = frozenset(
    {ip_address("100.100.100.200"), ip_address("168.63.129.16"), ip_address("fd00:ec2::254")}
)


@dataclass(frozen=True, slots=True)
class ModelConnectionDestinationPolicy:
    """Apply deployment approval at save time without resolving or contacting the destination."""

    https_base_urls: frozenset[str] = frozenset()
    local_ollama_base_urls: frozenset[str] = frozenset()

    def permits(
        self,
        *,
        provider: ModelConnectionProvider,
        base_url: str,
        api_version: str | None,
        authentication: ModelConnectionAuthentication,
    ) -> bool:
        if api_version is not None:
            return False
        if provider is ModelConnectionProvider.OLLAMA:
            return (
                authentication is ModelConnectionAuthentication.NONE
                and base_url in self.local_ollama_base_urls
                and self.is_supported_base_url(base_url, scheme="http", loopback=True)
            )
        if authentication is not ModelConnectionAuthentication.API_KEY:
            return False
        if provider is ModelConnectionProvider.OPENAI and base_url != "https://api.openai.com/v1":
            return False
        return base_url in self.https_base_urls and self.is_supported_base_url(
            base_url, scheme="https"
        )

    @staticmethod
    def is_supported_base_url(value: str, *, scheme: str, loopback: bool = False) -> bool:
        if (
            not 1 <= len(value) <= 2048
            or not value.startswith(f"{scheme}://")
            or any(not 33 <= ord(character) <= 126 or character in "?#%\\" for character in value)
        ):
            return False
        try:
            parts = urlsplit(value)
            host, port = parts.hostname, parts.port
        except ValueError:
            return False
        if (
            host is None
            or parts.username is not None
            or parts.password is not None
            or port == 0
            or parts.netloc.endswith(":")
            or not ModelConnectionDestinationPolicy._valid_path(parts.path)
        ):
            return False
        authority = f"[{host}]" if ":" in host else host
        if port is not None:
            authority = f"{authority}:{port}"
        if parts.netloc.lower() != authority:
            return False
        return ModelConnectionDestinationPolicy._valid_host(host, loopback=loopback)

    @staticmethod
    def _valid_host(host: str, *, loopback: bool) -> bool:
        try:
            address: IPv4Address | IPv6Address = ip_address(host)
        except ValueError:
            labels = host.split(".")
            return (
                not loopback
                and len(host) <= 253
                and host not in _METADATA_HOSTS
                and all(
                    fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) is not None
                    for label in labels
                )
                and fullmatch(r"(?:[0-9]+|0x[0-9a-f]+)", labels[-1]) is None
            )
        if isinstance(address, IPv6Address) and address.ipv4_mapped is not None:
            address = address.ipv4_mapped
        if address.is_loopback:
            return True
        return (
            not address.is_link_local
            and not address.is_unspecified
            and not address.is_multicast
            and not address.is_reserved
            and address not in _METADATA_ADDRESSES
            and not loopback
        )

    @staticmethod
    def _valid_path(path: str) -> bool:
        if path in ("", "/"):
            return True
        return all(
            part not in (".", "..") and fullmatch(r"[A-Za-z0-9._~!$&'()+,=@-]+", part) is not None
            for part in path[1:].removesuffix("/").split("/")
        )
