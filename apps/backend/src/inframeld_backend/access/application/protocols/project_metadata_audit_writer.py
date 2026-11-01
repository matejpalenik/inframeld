from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.project_metadata_authority_repaired_audit_event_dto import (
    ProjectMetadataAuthorityRepairedAuditEventDTO,
)
from inframeld_backend.access.application.dtos.project_metadata_changed_audit_event_dto import (
    ProjectMetadataChangedAuditEventDTO,
)


class ProjectMetadataAuditWriter(Protocol):
    """Flush bounded metadata audit in the caller transaction, never committing.

    Host operator attribution stays separate from the recipient of a repaired grant.
    """

    @abstractmethod
    async def changed(self, event: ProjectMetadataChangedAuditEventDTO) -> None: ...

    @abstractmethod
    async def repaired(self, event: ProjectMetadataAuthorityRepairedAuditEventDTO) -> None: ...
