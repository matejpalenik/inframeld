from dataclasses import replace
from uuid import UUID

import pytest
from tests.support.application_key_scenarios import current_key_facts
from tests.support.authentication_evidence import MockAuthenticationEvidence

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.application_key_authentication_dto import (
    ApplicationKeyAuthenticationDTO,
)
from inframeld_backend.access.application.dtos.browser_session_authentication_dto import (
    BrowserSessionAuthenticationDTO,
)
from inframeld_backend.access.application.dtos.human_credential_facts_dto import (
    HumanCredentialFactsDTO,
)
from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
    HumanOAuthCredentialBindingDTO,
)
from inframeld_backend.access.application.services.principal_access_evaluation_service import (
    PrincipalAccessEvaluationService,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.application_key_adapter import ApplicationKeyAdapter
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.value_objects.application_key_audience import (
    ApplicationKeyAudience,
)
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId

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
        oauth_credential_facts=HumanCredentialFactsDTO(
            binding_matches_actor=binding_matches_actor,
            current_version=HumanCredentialVersion(version) if version is not None else None,
        ),
    )

    assert result.principal is PRINCIPAL
    assert result.has_pending_recovery
    assert result.credential_is_current is (binding_matches_actor and version == 1)


@pytest.mark.parametrize(
    "evidence, kind",
    [(BROWSER, PrincipalKind.HUMAN)],
)
@pytest.mark.parametrize("pending_recovery", [False, True])
def test_current_browser_generation_does_not_replace_account_or_recovery_checks(
    evidence: BrowserSessionAuthenticationDTO | ApplicationKeyAuthenticationDTO,
    kind: PrincipalKind,
    pending_recovery: bool,
) -> None:
    """A current binding does not clear suspension or an independent recovery block."""
    principal = replace(PRINCIPAL, kind=kind, status=PrincipalStatus.SUSPENDED)

    result = PrincipalAccessEvaluationService.evaluate(
        access=AccessContextDTO(principal.id, evidence),
        principal=principal,
        has_pending_recovery=pending_recovery,
        oauth_credential_facts=HumanCredentialFactsDTO(True, HumanCredentialVersion(1)),
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


@pytest.mark.parametrize(
    "change",
    [
        {"principal_id": PrincipalId(UUID(int=99))},
        {"organization_id": OrganizationId(UUID(int=99))},
        {"installation_id": InstallationId(UUID(int=99))},
        {"audience": ApplicationKeyAudience("https://other.test")},
        {"allowed_adapters": (ApplicationKeyAdapter.MCP,)},
        {"account_binding_matches": False},
        {"principal_id": None, "expires_at": None},
    ],
)
def test_application_requires_fresh_stored_bindings(change: dict[str, object]) -> None:
    principal = replace(PRINCIPAL, kind=PrincipalKind.APPLICATION)
    facts = current_key_facts(
        key_id=APPLICATION.key_id,
        principal_id=principal.id,
        organization_id=principal.organization_id,
        project_id=ProjectId(UUID(int=5)),
    )
    facts = replace(facts, **change)
    result = PrincipalAccessEvaluationService.evaluate(
        access=AccessContextDTO(principal.id, APPLICATION),
        principal=principal,
        has_pending_recovery=False,
        oauth_credential_facts=None,
        application_key_facts=facts,
    )
    assert not result.credential_is_current


def test_application_cannot_omit_current_key_observations() -> None:
    with pytest.raises(RuntimeError, match="Application.*facts"):
        PrincipalAccessEvaluationService.evaluate(
            access=AccessContextDTO(PRINCIPAL.id, APPLICATION),
            principal=replace(PRINCIPAL, kind=PrincipalKind.APPLICATION),
            has_pending_recovery=False,
            oauth_credential_facts=None,
        )


def test_application_expiry_equality_is_not_current() -> None:
    principal = replace(PRINCIPAL, kind=PrincipalKind.APPLICATION)
    facts = current_key_facts(
        key_id=APPLICATION.key_id,
        principal_id=principal.id,
        organization_id=principal.organization_id,
        project_id=ProjectId(UUID(int=5)),
    )
    result = PrincipalAccessEvaluationService.evaluate(
        access=AccessContextDTO(principal.id, APPLICATION),
        principal=principal,
        has_pending_recovery=False,
        oauth_credential_facts=None,
        application_key_facts=replace(facts, expires_at=facts.checked_at),
    )
    assert not result.credential_is_current


@pytest.mark.parametrize("matches", [False, True])
@pytest.mark.parametrize("version", [None, 1, 2])
def test_restoration_browser_requires_current_actor_version(
    matches: bool, version: int | None
) -> None:
    result = PrincipalAccessEvaluationService.evaluate(
        access=AccessContextDTO(PRINCIPAL.id, BROWSER),
        principal=PRINCIPAL,
        has_pending_recovery=False,
        oauth_credential_facts=HumanCredentialFactsDTO(
            matches, HumanCredentialVersion(version) if version is not None else None
        ),
    )
    assert result.credential_is_current is (matches and version == 1)


def test_restoration_browser_missing_current_facts_is_not_current() -> None:
    with pytest.raises(RuntimeError, match="Browser.*facts"):
        PrincipalAccessEvaluationService.evaluate(
            access=AccessContextDTO(PRINCIPAL.id, BROWSER),
            principal=PRINCIPAL,
            has_pending_recovery=False,
            oauth_credential_facts=None,
        )


def test_restoration_stale_browser_has_no_oauth_error_family() -> None:
    from inframeld_backend.access.domain.policy_inputs.principal_access_policy_input import (
        PrincipalAccessPolicyInput,
    )
    from inframeld_backend.shared.application.errors.application_errors import (
        AuthenticationRequiredError,
    )

    with pytest.raises(AuthenticationRequiredError) as caught:
        PrincipalAccessEvaluationService.require_current_credential(
            access=AccessContextDTO(PRINCIPAL.id, BROWSER),
            principal_access=PrincipalAccessPolicyInput(PRINCIPAL, False, False),
        )
    assert type(caught.value) is AuthenticationRequiredError
