from dataclasses import replace
from uuid import UUID

import pytest
from tests.support.authentication_evidence import MockAuthenticationEvidence

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
from inframeld_backend.access.application.dtos.human_oauth_credential_facts_dto import (
    HumanOAuthCredentialFactsDTO,
)
from inframeld_backend.access.application.services.principal_access_evaluation_service import (
    PrincipalAccessEvaluationService,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId

PRINCIPAL = Principal(
    id=PrincipalId(UUID(int=1)),
    organization_id=OrganizationId(UUID(int=2)),
    kind=PrincipalKind.HUMAN,
    status=PrincipalStatus.ACTIVE,
)
BROWSER = MockAuthenticationEvidence.browser()
OAUTH = MockAuthenticationEvidence.human_oauth()
APPLICATION = MockAuthenticationEvidence.application_key()


@pytest.mark.parametrize("binding_matches_actor", [False, True])
@pytest.mark.parametrize("version", [None, 1, 2])
def test_oauth_requires_a_matching_actor_and_exact_current_version(
    binding_matches_actor: bool, version: int | None
) -> None:
    """A matching version cannot make another account's credential usable."""
    result = PrincipalAccessEvaluationService.evaluate(
        access=AccessContextDTO(PRINCIPAL.id, OAUTH),
        principal=PRINCIPAL,
        has_pending_recovery=True,
        oauth_credential_facts=HumanOAuthCredentialFactsDTO(
            binding_matches_actor=binding_matches_actor,
            current_version=HumanCredentialVersion(version) if version is not None else None,
        ),
    )

    assert result.principal is PRINCIPAL
    assert result.has_pending_recovery
    assert result.credential_is_current is (binding_matches_actor and version == 1)


@pytest.mark.parametrize(
    "evidence, kind",
    [(BROWSER, PrincipalKind.HUMAN), (APPLICATION, PrincipalKind.APPLICATION)],
)
@pytest.mark.parametrize("pending_recovery", [False, True])
def test_other_families_do_not_require_an_oauth_generation(
    evidence: BrowserSessionAuthenticationDTO | ApplicationKeyAuthenticationDTO,
    kind: PrincipalKind,
    pending_recovery: bool,
) -> None:
    """Currentness is inapplicable here and does not verify the session or key."""
    principal = replace(PRINCIPAL, kind=kind, status=PrincipalStatus.SUSPENDED)

    result = PrincipalAccessEvaluationService.evaluate(
        access=AccessContextDTO(principal.id, evidence),
        principal=principal,
        has_pending_recovery=pending_recovery,
        oauth_credential_facts=None,
    )

    assert result.principal is principal
    assert result.has_pending_recovery is pending_recovery
    assert result.credential_is_current


@pytest.mark.parametrize(
    "evidence, kind",
    [
        (BROWSER, PrincipalKind.APPLICATION),
        (OAUTH, PrincipalKind.APPLICATION),
        (APPLICATION, PrincipalKind.HUMAN),
    ],
)
def test_evidence_cannot_change_the_stored_principal_kind(
    evidence: BrowserSessionAuthenticationDTO
    | HumanOAuthCredentialBindingDTO
    | ApplicationKeyAuthenticationDTO,
    kind: PrincipalKind,
) -> None:
    """Reject malformed internal contexts before they can bypass authorization checks."""
    with pytest.raises(RuntimeError, match="principal kind"):
        PrincipalAccessEvaluationService.evaluate(
            access=AccessContextDTO(PRINCIPAL.id, evidence),
            principal=replace(PRINCIPAL, kind=kind),
            has_pending_recovery=False,
            oauth_credential_facts=None,
        )


def test_oauth_cannot_silently_omit_its_current_observations() -> None:
    with pytest.raises(RuntimeError, match="OAuth.*facts"):
        PrincipalAccessEvaluationService.evaluate(
            access=AccessContextDTO(PRINCIPAL.id, OAUTH),
            principal=PRINCIPAL,
            has_pending_recovery=False,
            oauth_credential_facts=None,
        )
