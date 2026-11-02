from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.first_administrator_bootstrap_facts_dto import (
    FirstAdministratorBootstrapFactsDTO,
)
from inframeld_backend.access.application.dtos.first_administrator_bootstrap_receipt_dto import (
    FirstAdministratorBootstrapReceiptDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


class FirstAdministratorBootstrapFactsReader(Protocol):
    @abstractmethod
    async def read(
        self, *, installation_id: InstallationId, identity: VerifiedHumanIdentityDTO
    ) -> FirstAdministratorBootstrapFactsDTO:
        """Use the caller's READ COMMITTED transaction and original database budget.

        Take the identity turn, existing installation singleton row lock and
        applicable Organization lock, then reread facts in separate statements.
        Observe credential/recovery state without initializing or resetting it.
        """
        ...

    @abstractmethod
    async def receipt(
        self, *, installation_id: InstallationId, operation_id: OperationId
    ) -> FirstAdministratorBootstrapReceiptDTO | None:
        """Read the same host-operation namespace and reject another mode's key."""
        ...
