from uuid import UUID

import pytest

from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.enums.human_identity_link_state import (
    HumanIdentityLinkState,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.infrastructure.mappers.postgres_human_credential_state_mapper import (
    PostgresHumanCredentialStateMapper,
)
from inframeld_backend.access.infrastructure.rows.human_identity_link_row import (
    HumanIdentityLinkRow,
)
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
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


def _restoration_rows(
    status: PrincipalStatus = PrincipalStatus.ACTIVE,
) -> tuple[HumanIdentityLinkRow, PrincipalRow]:
    principal = PrincipalRow(
        id=UUID(int=9),
        organization_id=UUID(int=10),
        kind=PrincipalKind.HUMAN,
        status=status,
        display_name="Alice",
    )
    link = HumanIdentityLinkRow(
        authority=IDENTITY.authority.value,
        subject=IDENTITY.subject.value,
        organization_id=principal.organization_id,
        principal_id=principal.id,
        principal_kind=principal.kind,
    )
    return link, principal


@pytest.mark.parametrize("status", list(PrincipalStatus))
def test_restoration_rich_mapping_preserves_actual_linked_status(status: PrincipalStatus) -> None:
    link, principal = _restoration_rows(status)
    state = PostgresHumanCredentialStateMapper.to_authentication_state(
        IDENTITY, (INSTALLATION, 7, True, True, link, principal)
    )
    assert state.link_state is HumanIdentityLinkState.LINKED
    assert state.linked_principal is not None
    assert state.linked_principal.id.value == principal.id
    assert state.linked_principal.status is status
    assert state.credential_state.version == HumanCredentialVersion(7)
    assert state.credential_state.has_pending_recovery


@pytest.mark.parametrize("version", [None, 7])
@pytest.mark.parametrize("history", [False, True])
def test_restoration_rich_mapping_requires_authoritative_absence_for_unlinked(
    version: int | None, history: bool
) -> None:
    state = PostgresHumanCredentialStateMapper.to_authentication_state(
        IDENTITY, (INSTALLATION, version, False, history, None, None)
    )
    assert state.link_state is HumanIdentityLinkState.UNLINKED
    assert state.linked_principal is None
    assert state.credential_state.version == (
        HumanCredentialVersion(version) if version is not None else None
    )


@pytest.mark.parametrize(
    "damage",
    [
        "orphan",
        "principal-only",
        "principal-id",
        "organization",
        "principal-kind",
        "link-kind",
        "authority",
        "subject",
    ],
)
def test_restoration_rich_mapping_never_invents_a_principal_or_unlinked_state(damage: str) -> None:
    link, principal = _restoration_rows()
    observed_link: HumanIdentityLinkRow | None = link
    observed_principal: PrincipalRow | None = principal
    if damage == "orphan":
        observed_principal = None
    elif damage == "principal-only":
        observed_link = None
    elif damage == "principal-id":
        link.principal_id = UUID(int=99)
    elif damage == "organization":
        link.organization_id = UUID(int=99)
    elif damage == "principal-kind":
        principal.kind = PrincipalKind.APPLICATION
    elif damage == "link-kind":
        link.principal_kind = PrincipalKind.APPLICATION
    elif damage == "authority":
        link.authority = "other"
    else:
        link.subject = "other"
    state = PostgresHumanCredentialStateMapper.to_authentication_state(
        IDENTITY, (INSTALLATION, 7, False, False, observed_link, observed_principal)
    )
    assert state.link_state is HumanIdentityLinkState.INCOHERENT
    assert state.linked_principal is None


def test_restoration_rich_mapping_missing_installation_is_unavailable() -> None:
    with pytest.raises(DependencyUnavailableError):
        PostgresHumanCredentialStateMapper.to_authentication_state(IDENTITY, None)
