from dataclasses import dataclass
from datetime import datetime

from inframeld_backend.access.application.dtos.application_key_verification_profile_dto import (
    ApplicationKeyVerificationProfileDTO,
)
from inframeld_backend.access.domain.enums.application_key_adapter import ApplicationKeyAdapter
from inframeld_backend.access.domain.value_objects.application_key_audience import (
    ApplicationKeyAudience,
)
from inframeld_backend.access.domain.value_objects.application_key_id import ApplicationKeyId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


@dataclass(frozen=True, slots=True)
class ApplicationKeyCurrentFactsDTO:
    """Observe current non-secret key bindings after the owning coordination waits."""

    key_id: ApplicationKeyId
    principal_id: PrincipalId | None
    organization_id: OrganizationId | None
    project_id: ProjectId | None
    installation_id: InstallationId | None
    audience: ApplicationKeyAudience | None
    allowed_adapters: tuple[ApplicationKeyAdapter, ...]
    expires_at: datetime | None
    revoked_at: datetime | None
    checked_at: datetime
    expected_installation_id: InstallationId
    expected_profile: ApplicationKeyVerificationProfileDTO
    account_binding_matches: bool
