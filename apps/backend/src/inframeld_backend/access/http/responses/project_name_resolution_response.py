from inframeld_backend.access.http.responses.project_metadata_response import (
    ProjectMetadataResponse,
)


class ProjectNameResolutionResponse(ProjectMetadataResponse):
    """Expose the currently authorized Project identified by an exact scoped Name."""
