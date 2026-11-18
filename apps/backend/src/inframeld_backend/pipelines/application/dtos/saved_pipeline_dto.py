from dataclasses import dataclass

from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.pipelines.application.value_objects.pipeline_configuration import (
    PipelineConfiguration,
)
from inframeld_backend.pipelines.domain.value_objects.pipeline_id import PipelineId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName
from inframeld_backend.shared.domain.value_objects.submitted_display_name import (
    SubmittedDisplayName,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class SavedPipelineDTO:
    """Identify the exact saved settings the caller reviewed."""

    installation_id: InstallationId
    organization_id: OrganizationId
    project_id: ProjectId
    pipeline_id: PipelineId
    revision: int
    name: ResourceName
    display_name: SubmittedDisplayName
    configuration: PipelineConfiguration
