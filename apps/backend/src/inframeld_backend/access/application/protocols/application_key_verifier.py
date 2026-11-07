from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.application_key_verification_profile_dto import (
    ApplicationKeyVerificationProfileDTO,
)
from inframeld_backend.access.application.dtos.verified_application_key_dto import (
    VerifiedApplicationKeyDTO,
)
from inframeld_backend.access.application.value_objects.application_key_credential import (
    ApplicationKeyCredential,
)


class ApplicationKeyVerifier(Protocol):
    """Verify the complete key against stored verification material and trusted bindings."""

    @abstractmethod
    async def verify(
        self, credential: ApplicationKeyCredential, *, profile: ApplicationKeyVerificationProfileDTO
    ) -> VerifiedApplicationKeyDTO | None:
        """Return two verified IDs or None, failing unavailable dependencies explicitly.

        Installation is read from authoritative local metadata. Invalid credentials
        never authorize another verifier. Unexpected failures and cancellation propagate.
        """
        ...
