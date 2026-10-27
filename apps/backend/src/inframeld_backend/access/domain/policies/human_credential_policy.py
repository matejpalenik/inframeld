from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


class HumanCredentialPolicy:
    """Decide whether a CLI credential still belongs to the identity's current generation."""

    @staticmethod
    def is_current_for_actor(
        *,
        binding_matches_actor: bool,
        presented_version: HumanCredentialVersion,
        current_version: HumanCredentialVersion | None,
    ) -> bool:
        """Require the checked actor/installation binding and its exact current version."""
        return (
            binding_matches_actor
            and current_version is not None
            and presented_version == current_version
        )

    @staticmethod
    def is_current(
        *,
        installation_id: InstallationId,
        authority: IdentityAuthority,
        subject: IdentitySubject,
        version: HumanCredentialVersion,
        current_installation_id: InstallationId,
        current_authority: IdentityAuthority,
        current_subject: IdentitySubject,
        current_version: HumanCredentialVersion | None,
    ) -> bool:
        return (
            installation_id == current_installation_id
            and authority == current_authority
            and subject == current_subject
            and version == current_version
        )
