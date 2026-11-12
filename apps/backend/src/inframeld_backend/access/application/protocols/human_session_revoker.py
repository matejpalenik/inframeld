from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.human_session_cleanup_outcome_dto import (
    HumanSessionCleanupOutcomeDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)


class HumanSessionRevoker(Protocol):
    """Observe one bounded Kratos session invalidation for an exact trusted identity.

    The caller establishes original installation/provider scope and permission
    outside this capability. Results never authorize retry, dispatch or restoration.
    Cancellation propagates and does not establish that the SDK thread stopped.
    """

    @abstractmethod
    async def revoke_sessions(
        self, identity: VerifiedHumanIdentityDTO, *, timeout_seconds: float
    ) -> HumanSessionCleanupOutcomeDTO: ...
