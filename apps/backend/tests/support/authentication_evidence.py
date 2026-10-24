"""Simulate completed authentication for tests that exercise later application steps."""

from uuid import UUID

from inframeld_backend.access.application.dtos.application_key_authentication_dto import (
    ApplicationKeyAuthenticationDTO,
)
from inframeld_backend.access.application.dtos.browser_session_authentication_dto import (
    BrowserSessionAuthenticationDTO,
)
from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
    HumanOAuthCredentialBindingDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.domain.value_objects.application_key_id import ApplicationKeyId
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId

_IDENTITY = VerifiedHumanIdentityDTO(IdentityAuthority("kratos:test"), IdentitySubject("alice"))


class MockAuthenticationEvidence:
    """Build explicit evidence without issuing credentials or verifying a provider/key."""

    @staticmethod
    def browser(identity: VerifiedHumanIdentityDTO = _IDENTITY) -> BrowserSessionAuthenticationDTO:
        return BrowserSessionAuthenticationDTO(identity)

    @staticmethod
    def human_oauth(
        identity: VerifiedHumanIdentityDTO = _IDENTITY,
    ) -> HumanOAuthCredentialBindingDTO:
        return HumanOAuthCredentialBindingDTO(
            identity, InstallationId(UUID(int=123)), HumanCredentialVersion(1)
        )

    @staticmethod
    def application_key() -> ApplicationKeyAuthenticationDTO:
        return ApplicationKeyAuthenticationDTO(
            ApplicationKeyId(UUID("00000000-0000-4000-8000-000000000003"))
        )
