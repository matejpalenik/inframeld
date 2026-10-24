from dataclasses import replace
from uuid import UUID

import pytest

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
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
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId

IDENTITY = VerifiedHumanIdentityDTO(IdentityAuthority("kratos:test"), IdentitySubject("alice"))
ACTOR = PrincipalId(UUID(int=1))


@pytest.mark.parametrize(
    "evidence",
    [
        BrowserSessionAuthenticationDTO(IDENTITY),
        HumanOAuthCredentialBindingDTO(
            IDENTITY, InstallationId(UUID(int=2)), HumanCredentialVersion(7)
        ),
        ApplicationKeyAuthenticationDTO(ApplicationKeyId(UUID(int=3))),
    ],
)
def test_context_preserves_complete_authentication_evidence(
    evidence: BrowserSessionAuthenticationDTO
    | HumanOAuthCredentialBindingDTO
    | ApplicationKeyAuthenticationDTO,
) -> None:
    """Keep the exact evidence supplied by authentication for later current-state checks."""
    context = AccessContextDTO(ACTOR, authentication_evidence=evidence)
    assert context.actor_principal_id == ACTOR
    assert context.authentication_evidence is evidence


@pytest.mark.parametrize("invalid", [None, object(), IDENTITY])
def test_context_rejects_missing_or_unrecognized_evidence(invalid: object) -> None:
    """An absent binding cannot silently turn a CLI caller into a browser caller."""
    context = AccessContextDTO(
        ACTOR, authentication_evidence=BrowserSessionAuthenticationDTO(IDENTITY)
    )
    with pytest.raises(TypeError, match="authentication evidence"):
        replace(context, authentication_evidence=invalid)
