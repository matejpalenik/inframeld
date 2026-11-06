from dataclasses import dataclass
from datetime import datetime

from inframeld_backend.access.domain.enums.application_key_adapter import ApplicationKeyAdapter
from inframeld_backend.access.domain.value_objects.application_key_id import ApplicationKeyId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId


@dataclass(frozen=True, slots=True)
class ApplicationKeyMetadataDTO:
    """Expose lifecycle observations, never the verifier or original key."""

    key_id: ApplicationKeyId
    application_principal_id: PrincipalId
    project_id: ProjectId
    allowed_adapters: tuple[ApplicationKeyAdapter, ...]
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None
