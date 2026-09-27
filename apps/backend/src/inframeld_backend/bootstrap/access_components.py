from dataclasses import dataclass

from ory_kratos_client.api_client import ApiClient

from inframeld_backend.access.application.protocols.human_session_authenticator import (
    HumanSessionAuthenticator,
)


@dataclass(frozen=True, slots=True)
class AccessComponents:
    """Expose the authentication operation and its optional owned provider resource."""

    authenticator: HumanSessionAuthenticator
    kratos_client: ApiClient | None
