from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.commands.set_project_upload_default_command import (
    SetProjectUploadDefaultCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_upload_default_facts_dto import (
    ProjectUploadDefaultFactsDTO,
)
from inframeld_backend.access.domain.value_objects.project_id import ProjectId


class ProjectUploadDefaultFactsReader(Protocol):
    """Observe exact current facts under caller-owned Organization then Project coordination."""

    @abstractmethod
    async def read(
        self, *, access: AccessContextDTO, project_id: ProjectId
    ) -> ProjectUploadDefaultFactsDTO | None:
        """Use Project SHARE and return every saved group's facts, including absence."""
        ...

    @abstractmethod
    async def lock_for_change(
        self, *, access: AccessContextDTO, command: SetProjectUploadDefaultCommand
    ) -> ProjectUploadDefaultFactsDTO | None:
        """Use Project UPDATE and observe every current/proposed group after waits.

        Require active READ COMMITTED. Include exact current human credential and
        recovery facts. Missing facts are never a filtered or unconfigured audience.
        The caller retains locks through commit. No provider waits or positive cache.
        """
        ...
