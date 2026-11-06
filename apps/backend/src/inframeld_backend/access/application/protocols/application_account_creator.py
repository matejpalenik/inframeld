from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.commands.create_application_account_command import (
    CreateApplicationAccountCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.application_account_creation_result_dto import (
    ApplicationAccountCreationResultDTO,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO


class ApplicationAccountCreator(Protocol):
    @abstractmethod
    async def create(
        self,
        *,
        access: AccessContextDTO,
        command: CreateApplicationAccountCommand,
        context: IdempotencyContextDTO,
    ) -> ApplicationAccountCreationResultDTO:
        """Create one empty Project-bound account with three human creator grants.

        Own the short transaction. Check current human creation authority before
        reservation or replay. Save the principal, extension, membership, fixed
        grants, Project revision, audit and original result atomically. An exact
        authorized replay returns its original receipt without restoring grants.
        """
        ...
