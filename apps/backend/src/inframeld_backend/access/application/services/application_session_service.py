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
from inframeld_backend.access.application.dtos.current_application_session_dto import (
    CurrentApplicationSessionDTO,
)
from inframeld_backend.access.application.protocols.application_authentication_facts_reader import (
    ApplicationAuthenticationFactsReader,
)
from inframeld_backend.access.application.protocols.application_session_reader import (
    ApplicationSessionReader,
)
from inframeld_backend.access.application.services.principal_access_evaluation_service import (
    PrincipalAccessEvaluationService,
)
from inframeld_backend.access.domain.policies.application_authentication_policy import (
    ApplicationAuthenticationPolicy,
)
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    AuthenticationRequiredError,
    DependencyUnavailableError,
)


class ApplicationSessionService(ApplicationSessionReader):
    """Read an application's two safe identity fields under fresh current-key checks."""

    def __init__(
        self,
        *,
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
        self._authentication_facts_reader = authentication_facts_reader
        self._verification_profile = verification_profile
        self._total_timeout_seconds = total_timeout_seconds

    @override
    async def read(self, *, access: AccessContextDTO) -> CurrentApplicationSessionDTO:
        if not isinstance(access.authentication_evidence, ApplicationKeyAuthenticationDTO):
            raise AuthenticationRequiredError()
        profile = self._verification_profile
        if profile is None:
            raise DependencyUnavailableError()

        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._total_timeout_seconds
        try:
            async with asyncio.timeout_at(deadline):
                facts = await self._authentication_facts_reader.read_current(
                    access=access, profile=profile
                )
                if loop.time() >= deadline:
                    raise TimeoutError()
                if facts is None:
                    raise AccessDeniedError()
                if facts.principal.id != access.actor_principal_id:
                    raise RuntimeError("Application session facts returned another actor.")
                if facts.key_facts is not None and (facts.key_facts.expected_profile != profile):
                    raise RuntimeError(
                        "Application session facts changed the trusted profile or Project."
                    )

                eligibility = PrincipalAccessEvaluationService.evaluate(
                    access=access,
                    principal=facts.principal,
                    has_pending_recovery=False,
                    oauth_credential_facts=None,
                    application_key_facts=facts.key_facts,
                )
                PrincipalAccessEvaluationService.require_current_credential(
                    access=access, principal_access=eligibility
                )
                if facts.key_facts is not None and facts.key_facts.project_id != facts.project_id:
                    raise RuntimeError("Application session facts changed the bound Project.")
                if not ApplicationAuthenticationPolicy.may_authenticate(
                    principal_access=eligibility,
                    project_status=facts.project_status,
                    is_project_member=facts.is_project_member,
                    has_coherent_binding=facts.has_coherent_binding,
                ):
                    raise AccessDeniedError()
                return CurrentApplicationSessionDTO(facts.principal.id, facts.project_id)
        except TimeoutError as error:
            raise DependencyUnavailableError() from error
