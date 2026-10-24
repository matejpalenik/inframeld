from uuid import UUID

import pytest

from inframeld_backend.access.domain.policies.human_credential_policy import HumanCredentialPolicy
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


@pytest.mark.parametrize("binding_matches_actor", [False, True])
@pytest.mark.parametrize("version", [None, 6, 7, 8])
def test_actor_credentials_require_a_matching_binding_and_current_version(
    binding_matches_actor: bool, version: int | None
) -> None:
    assert HumanCredentialPolicy.is_current_for_actor(
        binding_matches_actor=binding_matches_actor,
        presented_version=HumanCredentialVersion(7),
        current_version=HumanCredentialVersion(version) if version is not None else None,
    ) is (binding_matches_actor and version == 7)


@pytest.mark.parametrize(
    "difference", [None, "installation", "authority", "subject", "old", "future", "missing"]
)
def test_only_the_exact_current_binding_is_accepted(difference: str | None) -> None:
    """A version number alone cannot bind a token to this installation and human."""
    assert HumanCredentialPolicy.is_current(
        installation_id=InstallationId(UUID(int=1)),
        authority=IdentityAuthority("kratos:test"),
        subject=IdentitySubject("alice"),
        version=HumanCredentialVersion(6),
        current_installation_id=InstallationId(UUID(int=2 if difference == "installation" else 1)),
        current_authority=IdentityAuthority(
            "other" if difference == "authority" else "kratos:test"
        ),
        current_subject=IdentitySubject("bob" if difference == "subject" else "alice"),
        current_version=None
        if difference == "missing"
        else HumanCredentialVersion(
            7 if difference == "old" else 5 if difference == "future" else 6
        ),
    ) is (difference is None)
