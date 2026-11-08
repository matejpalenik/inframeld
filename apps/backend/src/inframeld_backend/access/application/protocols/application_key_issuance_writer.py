from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.application_key_creation_dto import (
    ApplicationKeyCreationDTO,
)


class ApplicationKeyIssuanceWriter(Protocol):
    """Save the key, safe original, one revision and audit without committing.

    The caller owns the coordinated transaction and operation reservation.
    Neither a failed acknowledgment nor this capability may retry issuance.
    """

    @abstractmethod
    async def create(
        self, *, key: ApplicationKeyCreationDTO, expected_project_revision: int
    ) -> None: ...
