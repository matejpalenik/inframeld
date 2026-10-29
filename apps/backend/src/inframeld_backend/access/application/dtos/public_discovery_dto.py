from dataclasses import dataclass

from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


@dataclass(frozen=True, slots=True)
class PublicDiscoveryDTO:
    """Public identity facts without authority or provider secrets."""

    resource: str
    issuer: str
    installation_id: InstallationId
