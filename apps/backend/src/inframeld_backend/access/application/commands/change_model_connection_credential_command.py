from dataclasses import dataclass, field

from inframeld_backend.access.application.value_objects.provider_credential_value import (
    ProviderCredentialValue,
)
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.value_objects.model_connection_id import ModelConnectionId


@dataclass(frozen=True, slots=True)
class ChangeModelConnectionCredentialCommand:
    project_id: ProjectId
    connection_id: ModelConnectionId
    expected_revision: int
    value: ProviderCredentialValue | None = field(repr=False)
