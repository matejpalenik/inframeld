from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.my_organization_access_dto import (
    MyOrganizationAccessDTO,
)


class MyOrganizationAccessReader(Protocol):
    @abstractmethod
    async def read(self, *, access: AccessContextDTO) -> MyOrganizationAccessDTO:
        """Return only the current eligible human's Organization and actual grants.

        No action grant is required. Empty stored assignments remain empty, and
        successful observation confers no later permission.
        """
        ...
