from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.organization_access_facts_dto import (
    OrganizationAccessFactsDTO,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId


class OrganizationAccessFactsReader(Protocol):
    @abstractmethod
    async def read(self, *, access: AccessContextDTO) -> OrganizationAccessFactsDTO | None:
        """Read current actor eligibility, revision and only supported stored grants.

        Observe the current installation/link/version together for OAuth evidence.
        Do not provision a principal, infer grants or return another actor's data.
        """
        ...

    @abstractmethod
    async def read_for_creation(
        self, *, access: AccessContextDTO, organization_id: OrganizationId
    ) -> OrganizationAccessFactsDTO | None:
        """Coordinate on the existing Organization in the caller's bounded transaction.

        Require READ COMMITTED. Match the actor's current Organization, take its
        shared lock and read current eligibility, grants and revision in a later
        statement. Preserve recovery's exclusive Organization coordination.
        """
        ...
