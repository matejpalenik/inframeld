import asyncio
from typing import override

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.application_authentication_facts_dto import (
    ApplicationAuthenticationFactsDTO,
)
from inframeld_backend.access.application.dtos.application_key_verification_profile_dto import (
    ApplicationKeyVerificationProfileDTO,
)
from inframeld_backend.access.application.protocols.application_authentication_facts_reader import (
    ApplicationAuthenticationFactsReader,
)
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId


class MockApplicationAuthenticationFactsReader(ApplicationAuthenticationFactsReader):
    """Control current account/key facts without performing PostgreSQL reads."""

    def __init__(self, result: ApplicationAuthenticationFactsDTO | None) -> None:
        self.result = result
        self.principal_ids: list[PrincipalId] = []
        self.current_profiles: list[ApplicationKeyVerificationProfileDTO] = []
        self.failure: BaseException | None = None
        self.stall = False

    @override
    async def read(self, principal_id: PrincipalId) -> ApplicationAuthenticationFactsDTO | None:
        self.principal_ids.append(principal_id)
        return self.result

    @override
    async def read_current(
        self, *, access: AccessContextDTO, profile: ApplicationKeyVerificationProfileDTO
    ) -> ApplicationAuthenticationFactsDTO | None:
        self.current_profiles.append(profile)
        if self.failure is not None:
            raise self.failure
        if self.stall:
            await asyncio.Event().wait()
        return self.result
