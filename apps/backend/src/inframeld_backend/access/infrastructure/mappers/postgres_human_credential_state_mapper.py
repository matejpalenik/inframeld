from uuid import UUID

from inframeld_backend.access.application.dtos.human_credential_state_dto import (
    HumanCredentialStateDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
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
