from inframeld_backend.access.domain.enums.human_oauth_scope import HumanOAuthScope
from inframeld_backend.access.domain.value_objects.human_api_audience import HumanAPIAudience


class HumanOAuthConsentPolicy:
    """Limit CLI consent to this installation's supported human API access."""

    @staticmethod
    def supports_requested_access(
        *,
        client_id: str,
        scopes: tuple[HumanOAuthScope, ...],
        audiences: tuple[HumanAPIAudience, ...],
        expected_audience: HumanAPIAudience,
    ) -> bool:
        return (
            client_id == "inframeld-cli"
            and HumanOAuthScope.API in scopes
            and audiences == (expected_audience,)
        )

    @staticmethod
    def may_approve(
        *,
        client_id: str,
        scopes: tuple[HumanOAuthScope, ...],
        audiences: tuple[HumanAPIAudience, ...],
        expected_audience: HumanAPIAudience,
        has_pending_recovery: bool,
    ) -> bool:
        return (
            HumanOAuthConsentPolicy.supports_requested_access(
                client_id=client_id,
                scopes=scopes,
                audiences=audiences,
                expected_audience=expected_audience,
            )
            and not has_pending_recovery
        )
