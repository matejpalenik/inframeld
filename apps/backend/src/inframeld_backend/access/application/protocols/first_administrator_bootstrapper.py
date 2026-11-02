from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.commands.bootstrap_first_administrator_command import (
    BootstrapFirstAdministratorCommand,
)
from inframeld_backend.access.application.dtos.first_administrator_bootstrap_result_dto import (
    FirstAdministratorBootstrapResultDTO,
)


class FirstAdministratorBootstrapper(Protocol):
    """Claim the fixed first-administrator responsibility through host authority only."""

    @abstractmethod
    async def bootstrap(
        self, command: BootstrapFirstAdministratorCommand
    ) -> FirstAdministratorBootstrapResultDTO:
        """Verify fresh provider proof before local admission reads and own one transaction.

        Save the exact first admission, four grants, audit and original receipt
        together. Current eligibility still gates original replay, which never
        restores removed rights. This capability supplies no product endpoint.
        """
        ...
