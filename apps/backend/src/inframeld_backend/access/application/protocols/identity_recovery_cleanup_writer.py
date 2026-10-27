from abc import abstractmethod
from datetime import datetime
from typing import Protocol

from inframeld_backend.access.application.dtos.human_oauth_cleanup_outcome_dto import (
    HumanOAuthCleanupOutcomeDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_cleanup_claim_dto import (
    IdentityRecoveryCleanupClaimDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_cleanup_work_dto import (
    IdentityRecoveryCleanupWorkDTO,
)
from inframeld_backend.access.application.enums.identity_recovery_cleanup_step import (
    IdentityRecoveryCleanupStep,
)


class IdentityRecoveryCleanupWriter(Protocol):
    """Persist checked execution decisions without committing or calling Hydra.

    All writes require the coordinated caller transaction. Conditional ownership
    checks reject stale workers. Retain attempts and confirmed provenance.
    """

    @abstractmethod
    async def claim(
        self,
        work: IdentityRecoveryCleanupWorkDTO,
        claim: IdentityRecoveryCleanupClaimDTO,
        *,
        at: datetime,
    ) -> None: ...

    @abstractmethod
    async def admit_step(
        self,
        claim: IdentityRecoveryCleanupClaimDTO,
        step: IdentityRecoveryCleanupStep,
        *,
        at: datetime,
    ) -> None: ...

    @abstractmethod
    async def checkpoint(
        self,
        claim: IdentityRecoveryCleanupClaimDTO,
        step: IdentityRecoveryCleanupStep,
        outcome: HumanOAuthCleanupOutcomeDTO,
        *,
        at: datetime,
    ) -> None: ...

    @abstractmethod
    async def finish(
        self,
        work: IdentityRecoveryCleanupWorkDTO,
        *,
        at: datetime,
        terminal_reason: str | None,
        next_attempt_at: datetime | None = None,
    ) -> None: ...

    @abstractmethod
    async def save_complete_proof(
        self, work: IdentityRecoveryCleanupWorkDTO, *, at: datetime
    ) -> None: ...
