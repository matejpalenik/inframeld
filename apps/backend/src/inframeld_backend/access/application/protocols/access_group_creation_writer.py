from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.created_access_group_dto import (
    CreatedAccessGroupDTO,
)


class AccessGroupCreationWriter(Protocol):
    @abstractmethod
    async def create(self, *, group: CreatedAccessGroupDTO, expected_project_revision: int) -> None:
        """Persist the group, exact Name, creator membership and management atomically.

        Include the Project revision, audit and immutable original result in the
        caller's transaction. Do not grant any document action.
        """
        ...
