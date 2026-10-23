from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.project_use_only_grant_assigned_audit_event_dto import (
    ProjectUseOnlyGrantAssignedAuditEventDTO,
)


class AuditEventWriter(Protocol):
    """Record who assigned a project permission and which operation caused it.

    The required audit event belongs to the same transaction as the grant and
    its permission revision, so they become durable together.
    """

    @abstractmethod
    async def append(self, event: ProjectUseOnlyGrantAssignedAuditEventDTO) -> None:
        """Append the assignment event and send its pending write to the database.

        Flushing does not commit. Use the owning change's session and let
        persistence errors propagate so its caller can roll back the whole
        change. Do not authorize the assignment or change the grant here.

        Args:
            event: Checked scope, caller, recipient and assigned action, with
                the original operation ID for audit correlation.
        """
        ...
