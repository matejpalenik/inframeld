from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.current_application_session_dto import (
    CurrentApplicationSessionDTO,
)


class ApplicationSessionReader(Protocol):
    @abstractmethod
    async def read(self, *, access: AccessContextDTO) -> CurrentApplicationSessionDTO:
        """Recheck the current application and key before disclosing its two safe IDs."""
        ...
