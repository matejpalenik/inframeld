from typing import Annotated

from fastapi import Security
from fastapi.security import APIKeyCookie
from starlette.requests import Request

from inframeld_backend.access.application.dtos.invitation_browser_proof_dto import (
    InvitationBrowserProofDTO,
)
from inframeld_backend.access.application.protocols.invitation_session_verifier import (
    InvitationSessionVerifier,
)
from inframeld_backend.access.application.value_objects.browser_session_credential import (
    BrowserSessionCredential,
)
from inframeld_backend.access.http.dependencies.csrf_protection_dependency import (
    CSRFProtectionDependency,
)
from inframeld_backend.access.http.mappers.incoming_credential_mapper import (
    IncomingCredentialMapper,
)
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)

_COOKIE_SECURITY = APIKeyCookie(
    name="ory_kratos_session", scheme_name="KratosSession", auto_error=False
)


class InvitationBrowserDependency:
    """Verify a protected recipient browser without requiring local admission."""

    def __init__(
        self,
        verifier: InvitationSessionVerifier | None,
        csrf: CSRFProtectionDependency,
        *,
        observe_password_completion: bool = False,
    ) -> None:
        self._verifier = verifier
        self._csrf = csrf
        self._observe_password_completion = observe_password_completion

    async def __call__(
        self,
        request: Request,
        _cookie_schema: Annotated[str | None, Security(_COOKIE_SECURITY)],
    ) -> InvitationBrowserProofDTO:
        credential = IncomingCredentialMapper.select(
            authorization_headers=request.headers.getlist("Authorization"), cookies=request.cookies
        )
        if not isinstance(credential, BrowserSessionCredential):
            raise IncomingCredentialMapper.unauthorized()
        self._csrf(request)
        if self._verifier is None:
            raise DependencyUnavailableError()
        proof = await self._verifier.verify(
            credential, observe_password_completion=self._observe_password_completion
        )
        if proof is None:
            raise IncomingCredentialMapper.unauthorized(invalid_token=True)
        return proof
