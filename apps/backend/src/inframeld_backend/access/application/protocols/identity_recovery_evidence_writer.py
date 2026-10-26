from abc import abstractmethod
from datetime import datetime
from typing import Protocol

from inframeld_backend.access.application.dtos.identity_recovery_admission_dto import (
    IdentityRecoveryAdmissionDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_event_dto import (
    IdentityRecoveryEventDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_settings_evidence_dto import (
    IdentityRecoverySettingsEvidenceDTO,
)
from inframeld_backend.access.application.value_objects.identity_recovery_cleanup_run_budget import (
    IdentityRecoveryCleanupRunBudget,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId


class IdentityRecoveryEvidenceWriter(Protocol):
    """Persist checked native evidence in the caller's active, coordinated transaction.

    The application matches the original admission before writing. Preserve event
    meaning and immutable associations on replay. Conflicts raise ConflictError.
    Do not acquire locks, choose a recovery or budget, commit, or call providers.
    """

    @abstractmethod
    async def record_admission(
        self, event: IdentityRecoveryEventDTO, operation_id: OperationId
    ) -> None: ...

    @abstractmethod
    async def record_settings_association(
        self, evidence: IdentityRecoverySettingsEvidenceDTO, admission: IdentityRecoveryAdmissionDTO
    ) -> None: ...

    @abstractmethod
    async def record_password_saved(
        self, evidence: IdentityRecoverySettingsEvidenceDTO, admission: IdentityRecoveryAdmissionDTO
    ) -> datetime:
        """Return the original database receipt time, pending the caller's commit."""
        ...

    @abstractmethod
    async def ensure_initial_cleanup_handoff(
        self,
        evidence: IdentityRecoverySettingsEvidenceDTO,
        admission: IdentityRecoveryAdmissionDTO,
        *,
        budget: IdentityRecoveryCleanupRunBudget,
    ) -> None:
        """Save one initial job/run for the recorded password receipt.

        Use that receipt's original time for the supplied budget. Existing work
        retains its identity, budget and progress. This initiates no dispatch.
        """
        ...
