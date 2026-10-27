import pytest

from inframeld_backend.access.domain.enums.human_oauth_scope import HumanOAuthScope
from inframeld_backend.access.domain.policies.human_oauth_consent_policy import (
    HumanOAuthConsentPolicy,
)
from inframeld_backend.access.domain.value_objects.human_api_audience import HumanAPIAudience

AUDIENCE = HumanAPIAudience("https://api.example.test")


@pytest.mark.parametrize(
    "client,scopes,audiences,expected",
    [
        ("inframeld-cli", (HumanOAuthScope.API,), (AUDIENCE,), True),
        ("inframeld-cli", tuple(HumanOAuthScope), (AUDIENCE,), True),
        ("other", (HumanOAuthScope.API,), (AUDIENCE,), False),
        ("inframeld-cli", (), (AUDIENCE,), False),
        ("inframeld-cli", (HumanOAuthScope.OPENID,), (AUDIENCE,), False),
        ("inframeld-cli", (HumanOAuthScope.API,), (), False),
        (
            "inframeld-cli",
            (HumanOAuthScope.API,),
            (AUDIENCE, HumanAPIAudience("https://other.test")),
            False,
        ),
    ],
)
def test_supported_access_does_not_depend_on_browser_or_recovery_state(
    client: str,
    scopes: tuple[HumanOAuthScope, ...],
    audiences: tuple[HumanAPIAudience, ...],
    expected: bool,
) -> None:
    assert (
        HumanOAuthConsentPolicy.supports_requested_access(
            client_id=client,
            scopes=scopes,
            audiences=audiences,
            expected_audience=AUDIENCE,
        )
        is expected
    )


@pytest.mark.parametrize(
    "client,scopes,audiences,blocked,expected",
    [
        ("inframeld-cli", (HumanOAuthScope.API,), (AUDIENCE,), False, True),
        ("inframeld-cli", tuple(HumanOAuthScope), (AUDIENCE,), False, True),
        ("other", (HumanOAuthScope.API,), (AUDIENCE,), False, False),
        ("inframeld-cli", (), (AUDIENCE,), False, False),
        ("inframeld-cli", (HumanOAuthScope.OPENID,), (AUDIENCE,), False, False),
        ("inframeld-cli", (HumanOAuthScope.API,), (), False, False),
        (
            "inframeld-cli",
            (HumanOAuthScope.API,),
            (AUDIENCE, HumanAPIAudience("https://other.test")),
            False,
            False,
        ),
        ("inframeld-cli", (HumanOAuthScope.API,), (AUDIENCE,), True, False),
    ],
)
def test_consent_is_limited_to_this_installations_api(
    client: str,
    scopes: tuple[HumanOAuthScope, ...],
    audiences: tuple[HumanAPIAudience, ...],
    blocked: bool,
    expected: bool,
) -> None:
    assert (
        HumanOAuthConsentPolicy.may_approve(
            client_id=client,
            scopes=scopes,
            audiences=audiences,
            expected_audience=AUDIENCE,
            has_pending_recovery=blocked,
        )
        is expected
    )
