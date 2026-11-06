from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.created_application_account_dto import (
    CreatedApplicationAccountDTO,
)


class ApplicationAccountCreationWriter(Protocol):
    @abstractmethod
    async def create(
        self, *, account: CreatedApplicationAccountDTO, expected_project_revision: int
    ) -> None:
        """Persist checked creation, audit and original facts without committing.

        Require the matching original reservation and checked Project revision.
        Allocate the exact Project-scoped Name without replacing a reservation.
        Seed only the application membership and three creator administration
        grants. A failure propagates for the caller to roll back every record.
        """
        ...
