from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.first_administrator_bootstrap_facts_dto import (
    FirstAdministratorBootstrapFactsDTO,
)
from inframeld_backend.access.application.dtos.first_administrator_bootstrap_receipt_dto import (
    FirstAdministratorBootstrapReceiptDTO,
)


class FirstAdministratorBootstrapWriter(Protocol):
    @abstractmethod
    async def bootstrap(
        self,
        *,
        facts: FirstAdministratorBootstrapFactsDTO,
        receipt: FirstAdministratorBootstrapReceiptDTO,
    ) -> bool:
        """Save one checked pristine claim, exact grants and required audit atomically.

        Use the facts reader's coordinated session and caller-owned transaction.
        Return False for an already reserved host operation. Never commit, retry,
        initialize credential state or mutate an existing Organization.
        """
        ...
