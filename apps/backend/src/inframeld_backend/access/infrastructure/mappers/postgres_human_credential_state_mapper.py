from uuid import UUID

from inframeld_backend.access.application.dtos.human_authentication_state_dto import (
    HumanAuthenticationStateDTO,
)
from inframeld_backend.access.application.dtos.human_credential_state_dto import (
    HumanCredentialStateDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.enums.human_identity_link_state import (
    HumanIdentityLinkState,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.infrastructure.rows.human_identity_link_row import (
    HumanIdentityLinkRow,
)
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


class PostgresHumanCredentialStateMapper:
    """Convert stored credential state without initializing it or deciding eligibility."""

    @staticmethod
    def to_state(
        identity: VerifiedHumanIdentityDTO, row: tuple[UUID, int | None, bool, bool] | None
    ) -> HumanCredentialStateDTO:
        if row is None:
            raise DependencyUnavailableError("The installation identity is not available.")
        installation_id, version, pending, _history = row
        return HumanCredentialStateDTO(
            installation_id=InstallationId(installation_id),
            identity=identity,
            version=HumanCredentialVersion(version) if version is not None else None,
            has_pending_recovery=pending,
        )

    @staticmethod
    def to_authentication_state(
        identity: VerifiedHumanIdentityDTO,
        row: tuple[UUID, int | None, bool, bool, HumanIdentityLinkRow | None, PrincipalRow | None]
        | None,
    ) -> HumanAuthenticationStateDTO:
        if row is None:
            PostgresHumanCredentialStateMapper.to_state(identity, None)
            raise AssertionError("Missing installation must be rejected.")
        installation, version, pending, history, link, principal = row
        state = PostgresHumanCredentialStateMapper.to_state(
            identity, (installation, version, pending, history)
        )
        if link is None and principal is None:
            return HumanAuthenticationStateDTO(state, HumanIdentityLinkState.UNLINKED, None)
        if (
            link is None
            or principal is None
            or link.authority != identity.authority.value
            or link.subject != identity.subject.value
            or link.principal_id != principal.id
            or link.organization_id != principal.organization_id
            or link.principal_kind is not PrincipalKind.HUMAN
            or principal.kind is not PrincipalKind.HUMAN
        ):
            return HumanAuthenticationStateDTO(state, HumanIdentityLinkState.INCOHERENT, None)
        return HumanAuthenticationStateDTO(
            state,
            HumanIdentityLinkState.LINKED,
            Principal(
                PrincipalId(principal.id),
                OrganizationId(principal.organization_id),
                principal.kind,
                principal.status,
            ),
        )
