"""Orchestrate provider verification and local human admission."""

from typing import override

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.protocols.browser_session_verifier import (
    BrowserSessionVerifier,
)
from inframeld_backend.access.application.protocols.human_identity_link_reader import (
    HumanIdentityLinkReader,
)
from inframeld_backend.access.application.protocols.human_session_authenticator import (
    HumanSessionAuthenticator,
)
from inframeld_backend.access.application.value_objects.browser_session_credential import (
    BrowserSessionCredential,
)
from inframeld_backend.access.domain.policies.human_authentication_policy import (
    HumanAuthenticationPolicy,
)
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    AuthenticationRequiredError,
)


class HumanSessionAuthenticationService(HumanSessionAuthenticator):
    """Verify a browser session, require an active local human, and return its caller context."""

    def __init__(self, verifier: BrowserSessionVerifier, reader: HumanIdentityLinkReader) -> None:
        """Inject provider verification and independent local principal lookup boundaries."""
        self._verifier = verifier
        self._reader = reader

    @override
    async def authenticate(self, credential: BrowserSessionCredential | None) -> AccessContextDTO:
        """Verify first, read current local state second, and admit only an active human."""
        if credential is None:
            raise AuthenticationRequiredError()

        identity = await self._verifier.verify(credential)
        if identity is None:
            raise AuthenticationRequiredError()

        principal = await self._reader.find_principal(identity)
        if principal is None or not HumanAuthenticationPolicy.may_authenticate(principal):
            raise AccessDeniedError()

        return AccessContextDTO(actor_principal_id=principal.id)
