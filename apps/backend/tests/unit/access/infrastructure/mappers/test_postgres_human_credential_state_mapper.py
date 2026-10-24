from uuid import UUID

import pytest

from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.infrastructure.mappers.postgres_human_credential_state_mapper import (
    PostgresHumanCredentialStateMapper,
)
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId

IDENTITY = VerifiedHumanIdentityDTO(IdentityAuthority("kratos:test"), IdentitySubject("alice"))
INSTALLATION = UUID(int=1)


@pytest.mark.parametrize("version", [None, 7])
@pytest.mark.parametrize("pending", [False, True])
@pytest.mark.parametrize("history", [False, True])
def test_maps_the_observed_state_without_initializing_or_deciding_access(
    version: int | None, pending: bool, history: bool
) -> None:
    """Missing version state stays missing, even when a recovery has been recorded."""
    state = PostgresHumanCredentialStateMapper.to_state(
        IDENTITY, (INSTALLATION, version, pending, history)
    )

    assert state.installation_id == InstallationId(INSTALLATION)
    assert state.identity is IDENTITY
    assert state.version == (HumanCredentialVersion(version) if version is not None else None)
    assert state.has_pending_recovery is pending


def test_missing_installation_does_not_look_like_an_uninitialized_identity() -> None:
    with pytest.raises(DependencyUnavailableError, match="installation identity"):
        PostgresHumanCredentialStateMapper.to_state(IDENTITY, None)


@pytest.mark.parametrize("version", [0, -1, 2**63])
def test_invalid_stored_versions_are_not_converted_to_valid_state(version: int) -> None:
    with pytest.raises(ValueError, match="positive BIGINT"):
        PostgresHumanCredentialStateMapper.to_state(IDENTITY, (INSTALLATION, version, False, False))
