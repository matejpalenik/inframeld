from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.deletion_recovery_authorization_dto import (
    DeletionRecoveryAuthorizationDTO,
)


class DeletionRecoveryAuthorizer(Protocol):
    @abstractmethod
    async def require_current_human(
        self, *, access: AccessContextDTO
    ) -> DeletionRecoveryAuthorizationDTO:
        """Require current human credential and recovery eligibility without searching history.

        Surviving Project membership is unnecessary. This grants no authority to
        inspect another initiator's operation or any resource content.
        """
        ...
