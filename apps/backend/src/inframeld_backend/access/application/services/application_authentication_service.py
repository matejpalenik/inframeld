import asyncio
import math
from typing import override

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.application_key_authentication_dto import (
    ApplicationKeyAuthenticationDTO,
)
from inframeld_backend.access.application.dtos.application_key_verification_profile_dto import (
    ApplicationKeyVerificationProfileDTO,
)
from inframeld_backend.access.application.protocols.application_authentication_facts_reader import (
    ApplicationAuthenticationFactsReader,
)
from inframeld_backend.access.application.protocols.application_authenticator import (
    ApplicationAuthenticator,
)
from inframeld_backend.access.application.protocols.application_key_verifier import (
    ApplicationKeyVerifier,
)
from inframeld_backend.access.application.value_objects.application_key_credential import (
    ApplicationKeyCredential,
)
from inframeld_backend.access.domain.policies.application_authentication_policy import (
    ApplicationAuthenticationPolicy,
)
from inframeld_backend.access.domain.policy_inputs.principal_access_policy_input import (
    PrincipalAccessPolicyInput,
)
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    AuthenticationRequiredError,
    DependencyUnavailableError,
)


class ApplicationAuthenticationService(ApplicationAuthenticator):
    """Verify a key before separately admitting its existing local account."""

    def __init__(
        self,
        *,
        key_verifier: ApplicationKeyVerifier,
        authentication_facts_reader: ApplicationAuthenticationFactsReader,
        verification_profile: ApplicationKeyVerificationProfileDTO | None,
        total_timeout_seconds: float = 10.0,
    ) -> None:
        if (
            isinstance(total_timeout_seconds, bool)
            or not math.isfinite(total_timeout_seconds)
            or total_timeout_seconds <= 0
        ):
            raise ValueError("Authentication timeout must be finite and positive.")
        self._key_verifier = key_verifier
        self._authentication_facts_reader = authentication_facts_reader
        self._verification_profile = verification_profile
        self._total_timeout_seconds = total_timeout_seconds

    @override
    async def authenticate(self, credential: ApplicationKeyCredential) -> AccessContextDTO:
        profile = self._verification_profile
        if profile is None:
            raise DependencyUnavailableError()

        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._total_timeout_seconds
        try:
            async with asyncio.timeout_at(deadline):
                verified = await self._key_verifier.verify(credential, profile=profile)
                if loop.time() >= deadline:
                    raise TimeoutError()
                if verified is None:
                    raise AuthenticationRequiredError()

                facts = await self._authentication_facts_reader.read(verified.principal_id)
                if loop.time() >= deadline:
                    raise TimeoutError()
                if facts is None:
                    raise AccessDeniedError()
                if facts.principal.id != verified.principal_id:
                    raise RuntimeError("Application admission returned another actor.")

                principal_access = PrincipalAccessPolicyInput(
                    principal=facts.principal,
                    has_pending_recovery=False,
                    credential_is_current=True,
                )
                if not ApplicationAuthenticationPolicy.may_authenticate(
                    principal_access=principal_access,
                    project_status=facts.project_status,
                    is_project_member=facts.is_project_member,
                    has_coherent_binding=facts.has_coherent_binding,
                ):
                    raise AccessDeniedError()

                return AccessContextDTO(
                    verified.principal_id, ApplicationKeyAuthenticationDTO(verified.key_id)
                )
        except TimeoutError as error:
            raise DependencyUnavailableError() from error
