from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.deletion_status_facts_dto import (
    DeletionStatusFactsDTO,
)


class DeletionStatusFactsReader(Protocol):
    """Read current actor, installation, recovery and credential facts without history.

    Do not require a surviving Project or membership. Required state that cannot
    be established raises DependencyUnavailableError rather than an empty result.
    """

    @abstractmethod
    async def read(self, *, access: AccessContextDTO) -> DeletionStatusFactsDTO | None: ...
