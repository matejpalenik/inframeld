from typing import Protocol

from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId


class AuthorizedOperationScope[ProjectScope: ProjectId | None](Protocol):
    """Expose the organization and optional project checked by an authorizer.

    Use this result in the transaction that performed authorization. For project
    work, match its project to the requested target before using it downstream.
    Implementing the interface alone proves no permission. Its fields do not
    express read-only access, although concrete result records remain frozen.

    Attributes:
        organization_id: Organization established by current authorization.
        project_id: Exact authorized project, or None for organization-scoped work.
    """

    __slots__ = ()

    organization_id: OrganizationId
    project_id: ProjectScope
