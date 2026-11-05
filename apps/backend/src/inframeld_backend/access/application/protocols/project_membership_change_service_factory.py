from abc import abstractmethod
from contextlib import AbstractAsyncContextManager
from typing import Protocol

from inframeld_backend.access.application.protocols.project_membership_changer import (
    ProjectMembershipChanger,
)


class ProjectMembershipChangeServiceFactory(Protocol):
    """Provide one membership service with request-local resources for each operation."""

    @abstractmethod
    def open(self) -> AbstractAsyncContextManager[ProjectMembershipChanger]:
        """Close the operation's resources on exit while the service owns its transaction."""
        ...
