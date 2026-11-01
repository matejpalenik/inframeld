from inframeld_backend.access.domain.entities.project_metadata import ProjectMetadata
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName


class PostgresProjectMetadataMapper:
    @staticmethod
    def from_row(row: ProjectRow) -> ProjectMetadata:
        return ProjectMetadata(
            project_id=ProjectId(row.id),
            organization_id=OrganizationId(row.organization_id),
            name=None if row.resource_name is None else ResourceName(row.resource_name),
            display_name=row.name,
            revision=row.metadata_revision,
        )
