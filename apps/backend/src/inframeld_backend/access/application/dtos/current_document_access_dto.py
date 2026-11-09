from dataclasses import dataclass

from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
from inframeld_backend.access.domain.value_objects.document_id import DocumentId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId


@dataclass(frozen=True, slots=True)
class CurrentDocumentAccessDTO:
    """Complete trusted current logical Document observation shared by all versions.

    The owning producer refreshes this observation at each protected boundary.
    Include every audience ID, including missing or foreign groups. Access validates
    their current scope before applying OR membership. This record is not authority.
    """

    document_id: DocumentId
    project_id: ProjectId
    audience: frozenset[AccessGroupId]
    is_live: bool
