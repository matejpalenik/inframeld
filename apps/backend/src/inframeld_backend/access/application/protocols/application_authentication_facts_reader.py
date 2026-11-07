from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.application_authentication_facts_dto import (
    ApplicationAuthenticationFactsDTO,
)
from inframeld_backend.access.application.dtos.application_key_verification_profile_dto import (
    ApplicationKeyVerificationProfileDTO,
)
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId


class ApplicationAuthenticationFactsReader(Protocol):
    """Use short independent sessions for current account admission and identity disclosure."""

    @abstractmethod
    async def read(self, principal_id: PrincipalId) -> ApplicationAuthenticationFactsDTO | None: ...

    @abstractmethod
    async def read_current(
        self, *, access: AccessContextDTO, profile: ApplicationKeyVerificationProfileDTO
    ) -> ApplicationAuthenticationFactsDTO | None:
        """Read current account and key observations immediately before session disclosure."""
        ...
