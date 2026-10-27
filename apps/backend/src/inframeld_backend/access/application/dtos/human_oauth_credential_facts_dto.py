from dataclasses import dataclass

from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)


@dataclass(frozen=True, slots=True)
class HumanOAuthCredentialFactsDTO:
    """Observe the caller's stored identity link and credential version together.

    The binding match includes the current installation and exact provider identity.
    These observations do not establish permission or credential currentness.
    """

    binding_matches_actor: bool
    current_version: HumanCredentialVersion | None
