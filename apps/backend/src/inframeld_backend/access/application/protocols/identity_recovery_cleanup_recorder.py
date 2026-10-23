from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.identity_recovery_cleanup_result_dto import (
    IdentityRecoveryCleanupResultDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_event_dto import (
    IdentityRecoveryEventDTO,
)
from inframeld_backend.access.domain.enums.identity_recovery_cleanup_state import (
    IdentityRecoveryCleanupState,
)


class IdentityRecoveryCleanupRecorder(Protocol):
    """Record trusted cleanup results and finish the original recovery when eligible.

    Authenticate and validate provider evidence before calling. Typed event and
    outcome values alone establish no trust. Provider calls happen separately.
    """

    @abstractmethod
    async def record_cleanup(
        self,
        *,
        event: IdentityRecoveryEventDTO,
        kratos_outcome: IdentityRecoveryCleanupState | None = None,
        hydra_outcome: IdentityRecoveryCleanupState | None = None,
    ) -> IdentityRecoveryCleanupResultDTO:
        """Commit supplied outcomes and release only this eligible checklist.

        Supply at least one outcome. Omit a provider to preserve its result.
        A released duplicate returns recorded state without another save.
        An unreleased repeat also rechecks current local eligibility.

        Raises:
            InvalidInputError: No outcome is supplied, or an outcome is pending.
            ConflictError: Admission is missing, the event binding conflicts,
                or the result would regress confirmed cleanup.
            DependencyUnavailableError: Current facts cannot be established.
            RuntimeError: Dependencies return inconsistent scope or identity.
        """
        ...
