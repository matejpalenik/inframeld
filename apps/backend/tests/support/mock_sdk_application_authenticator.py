"""Supply fixed synthetic credentials for application-identity SDK qualification."""

from typing import override
from uuid import UUID

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.application_key_authentication_dto import (
    ApplicationKeyAuthenticationDTO,
)
from inframeld_backend.access.application.protocols.application_authenticator import (
    ApplicationAuthenticator,
)
from inframeld_backend.access.application.value_objects.application_key_credential import (
    ApplicationKeyCredential,
)
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    AuthenticationRequiredError,
    DependencyUnavailableError,
)

_PREFIX = "ifm_app_00000000-0000-4000-8000-"
_SECRET = "A" * 43


class MockSDKApplicationAuthenticator(ApplicationAuthenticator):
    """Simulate completed verification/admission for exact private test inputs.

    These complete synthetic strings are neither issued keys nor evidence of
    persisted verification. Disclosure separately consumes controlled current facts.
    """

    @override
    async def authenticate(self, credential: ApplicationKeyCredential) -> AccessContextDTO:
        if credential.value == _PREFIX + "000000000004_" + _SECRET:
            raise AccessDeniedError()
        if credential.value == _PREFIX + "000000000005_" + _SECRET:
            raise DependencyUnavailableError()
        if credential.value not in tuple(
            _PREFIX + suffix + "_" + _SECRET
            for suffix in ("000000000003", "000000000006", "000000000007", "000000000009")
        ):
            raise AuthenticationRequiredError()
        return AccessContextDTO(
            actor_principal_id=PrincipalId(UUID("00000000-0000-4000-8000-000000000008")),
            authentication_evidence=ApplicationKeyAuthenticationDTO(key_id=credential.key_id),
        )
