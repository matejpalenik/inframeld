from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.created_project_dto import CreatedProjectDTO


class ProjectCreationWriter(Protocol):
    @abstractmethod
    async def create(
        self, *, project: CreatedProjectDTO, expected_organization_revision: int
    ) -> None:
        """Persist checked creation and required audit in the coordinated caller session.

        Require the matching Organization-scoped in-progress reservation. Allocate
        the exact Name without suffixing or overwriting another reservation. Seed
        the checked human's membership and eighteen explicit grants once, advancing
        new Project access 0 to 1 and keeping metadata/name binding at 0. Never
        change Organization revision, commit, retry or backfill another Project.
        """
        ...
