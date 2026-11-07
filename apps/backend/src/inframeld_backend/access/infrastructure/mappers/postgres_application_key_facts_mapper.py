from datetime import datetime
from uuid import UUID

from inframeld_backend.access.application.dtos.application_key_authentication_dto import (
    ApplicationKeyAuthenticationDTO,
)
from inframeld_backend.access.application.dtos.application_key_current_facts_dto import (
    ApplicationKeyCurrentFactsDTO,
)
from inframeld_backend.access.application.dtos.application_key_verification_profile_dto import (
    ApplicationKeyVerificationProfileDTO,
)
from inframeld_backend.access.domain.enums.application_key_adapter import ApplicationKeyAdapter
from inframeld_backend.access.domain.value_objects.application_key_audience import (
    ApplicationKeyAudience,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


class PostgresApplicationKeyFactsMapper:
    """Convert safe stored bindings without copying verifier material or permissions."""

    @staticmethod
    def to_facts(
        row: tuple[
            UUID,
            UUID | None,
            UUID | None,
            UUID | None,
            UUID | None,
            str | None,
            list[str] | None,
            datetime | None,
            datetime | None,
            datetime,
            bool,
        ]
        | None,
        *,
        evidence: ApplicationKeyAuthenticationDTO,
        profile: ApplicationKeyVerificationProfileDTO,
    ) -> ApplicationKeyCurrentFactsDTO:
        if row is None:
            raise DependencyUnavailableError("The installation identity is unavailable.")
        (
            installed,
            principal,
            organization,
            project,
            installation,
            audience,
            adapters,
            expires_at,
            revoked_at,
            checked_at,
            account_matches,
        ) = row
        return ApplicationKeyCurrentFactsDTO(
            key_id=evidence.key_id,
            principal_id=PrincipalId(principal) if principal is not None else None,
            organization_id=OrganizationId(organization) if organization is not None else None,
            project_id=ProjectId(project) if project is not None else None,
            installation_id=InstallationId(installation) if installation is not None else None,
            audience=ApplicationKeyAudience(audience) if audience is not None else None,
            allowed_adapters=tuple(ApplicationKeyAdapter(adapter) for adapter in adapters or ()),
            expires_at=expires_at,
            revoked_at=revoked_at,
            checked_at=checked_at,
            expected_installation_id=InstallationId(installed),
            expected_profile=profile,
            account_binding_matches=account_matches,
        )
