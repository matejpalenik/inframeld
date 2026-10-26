from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.identity_recovery_association_facts_dto import (
    IdentityRecoveryAssociationFactsDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_settings_evidence_dto import (
    IdentityRecoverySettingsEvidenceDTO,
)


class IdentityRecoveryAssociationFactsReader(Protocol):
    """Read current native-flow bindings in the caller's bounded transaction.

    Acquire the trusted identity's coordination before its organization lock,
    then read one coherent projection in READ COMMITTED isolation. Return missing
    records as None, including a missing credential version. The application
    decides whether the notification is ordinary, valid recovery evidence or a
    conflict. Never create an account, initialize a version or commit.
    """

    @abstractmethod
    async def read(
        self, evidence: IdentityRecoverySettingsEvidenceDTO
    ) -> IdentityRecoveryAssociationFactsDTO:
        """Return scoped observations, failing unavailable installation state closed.

        Require an active transaction and the configured provider authority.
        Caller-supplied identity comes from an authenticated native hook.
        """
        ...
