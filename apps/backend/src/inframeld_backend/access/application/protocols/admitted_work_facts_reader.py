from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.admitted_work_authority_dto import (
    AdmittedWorkAuthorityDTO,
)
from inframeld_backend.access.application.dtos.admitted_work_facts_dto import AdmittedWorkFactsDTO


class AdmittedWorkFactsReader(Protocol):
    """Read coherent current authority under the caller's short transaction."""

    @abstractmethod
    async def read(self, authority: AdmittedWorkAuthorityDTO) -> AdmittedWorkFactsDTO | None: ...
