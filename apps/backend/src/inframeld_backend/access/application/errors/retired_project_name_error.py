from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.errors.application_errors import ResourceNotFoundError
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName


class RetiredProjectNameError(ResourceNotFoundError):
    """Carry authorized original-ID/current-name guidance without a redirect."""

    def __init__(self, project_id: ProjectId, current_name: ResourceName | None) -> None:
        self.project_id = project_id
        self.current_name = current_name
        super().__init__("The requested Project name is retired.")
