from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.identity_recovery_event_dto import (
    IdentityRecoveryEventDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_notification_result_dto import (
    IdentityRecoveryNotificationResultDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_settings_evidence_dto import (
    IdentityRecoverySettingsEvidenceDTO,
)


class IdentityRecoveryNotificationHandler(Protocol):
    """Save trusted Kratos evidence before acknowledging its delivery.

    Only the private, authenticated native hooks may call these operations.
    Each operation owns its transaction. Repeats preserve the original operation,
    while conflicting identity or association raises ConflictError. A receipt
    confirms persistence, not Hydra cleanup or restored product access.
    """

    @abstractmethod
    async def admit(
        self, event: IdentityRecoveryEventDTO
    ) -> IdentityRecoveryNotificationResultDTO: ...

    @abstractmethod
    async def associate_settings(
        self, evidence: IdentityRecoverySettingsEvidenceDTO
    ) -> IdentityRecoveryNotificationResultDTO | None:
        """Bind native settings to recovery, or ignore ordinary unassociated settings."""
        ...

    @abstractmethod
    async def record_password_saved(
        self, evidence: IdentityRecoverySettingsEvidenceDTO
    ) -> IdentityRecoveryNotificationResultDTO | None:
        """Record native password/session cleanup and its durable handoff, without release."""
        ...
