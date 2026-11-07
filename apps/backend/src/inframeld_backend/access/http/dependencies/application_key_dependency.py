from typing import Annotated

from fastapi import Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.requests import Request

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.protocols.application_authenticator import (
    ApplicationAuthenticator,
)
from inframeld_backend.access.application.value_objects.application_key_credential import (
    ApplicationKeyCredential,
)
from inframeld_backend.access.http.mappers.incoming_credential_mapper import (
    IncomingCredentialMapper,
)
from inframeld_backend.shared.application.errors.application_errors import (
    AuthenticationRequiredError,
)

_BEARER_SECURITY = HTTPBearer(
    scheme_name="ApplicationKeyBearer",
    description="Complete Inframeld application key for this HTTP resource.",
    auto_error=False,
)


class ApplicationKeyDependency:
    """Keep application identity checks exclusive to the application credential family."""

    def __init__(self, authenticator: ApplicationAuthenticator) -> None:
        self._authenticator = authenticator

    async def __call__(
        self,
        request: Request,
        _bearer_schema: Annotated[HTTPAuthorizationCredentials | None, Security(_BEARER_SECURITY)],
    ) -> AccessContextDTO:
        credential = IncomingCredentialMapper.select(
            authorization_headers=request.headers.getlist("Authorization"), cookies=request.cookies
        )
        if not isinstance(credential, ApplicationKeyCredential):
            raise IncomingCredentialMapper.unauthorized(
                invalid_token=bool(request.headers.getlist("Authorization"))
            )
        try:
            return await self._authenticator.authenticate(credential)
        except AuthenticationRequiredError:
            raise IncomingCredentialMapper.unauthorized(invalid_token=True) from None
