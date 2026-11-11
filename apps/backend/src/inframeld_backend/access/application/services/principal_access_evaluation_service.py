from typing import assert_never

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.application_key_authentication_dto import (
    ApplicationKeyAuthenticationDTO,
)
from inframeld_backend.access.application.dtos.application_key_current_facts_dto import (
    ApplicationKeyCurrentFactsDTO,
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
from inframeld_backend.access.application.errors.application_key_credential_rejected_error import (
    ApplicationKeyCredentialRejectedError,
)
from inframeld_backend.access.application.errors.human_oauth_credential_rejected_error import (
    HumanOAuthCredentialRejectedError,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.policies.application_key_credential_policy import (
    ApplicationKeyCredentialPolicy,
)
from inframeld_backend.access.domain.policies.human_credential_policy import HumanCredentialPolicy
from inframeld_backend.access.domain.policy_inputs.principal_access_policy_input import (
    PrincipalAccessPolicyInput,
)
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    AuthenticationRequiredError,
)


class PrincipalAccessEvaluationService:
    """Combine authenticated evidence and current facts into an eligibility input.

    Wrong principal kinds or missing OAuth facts are internal contract failures.
    This service does not verify browser sessions or application keys.
    """

    @staticmethod
    def evaluate(
        *,
        access: AccessContextDTO,
        principal: Principal,
        has_pending_recovery: bool,
        oauth_credential_facts: HumanCredentialFactsDTO | None,
        application_key_facts: ApplicationKeyCurrentFactsDTO | None = None,
    ) -> PrincipalAccessPolicyInput:
        evidence = access.authentication_evidence
        match evidence:
            case ApplicationKeyAuthenticationDTO():
                expected_kind = PrincipalKind.APPLICATION
            case BrowserSessionAuthenticationDTO() | HumanOAuthCredentialBindingDTO():
                expected_kind = PrincipalKind.HUMAN
            case _:
                assert_never(evidence)
        if principal.kind is not expected_kind:
            raise RuntimeError("Authentication evidence does not match the principal kind.")

        if isinstance(evidence, (HumanOAuthCredentialBindingDTO, BrowserSessionAuthenticationDTO)):
            if oauth_credential_facts is None:
                family = (
                    "Browser"
                    if isinstance(evidence, BrowserSessionAuthenticationDTO)
                    else "Human OAuth"
                )
                raise RuntimeError(f"{family} evidence requires current credential facts.")
            credential_is_current = HumanCredentialPolicy.is_current_for_actor(
                binding_matches_actor=oauth_credential_facts.binding_matches_actor,
                presented_version=evidence.version,
                current_version=oauth_credential_facts.current_version,
            )
        else:
            if application_key_facts is None:
                raise RuntimeError("Application key evidence requires current key facts.")
            facts = application_key_facts
            credential_is_current = ApplicationKeyCredentialPolicy.is_current(
                binding_matches=(
                    facts.key_id == evidence.key_id
                    and facts.principal_id == principal.id == access.actor_principal_id
                    and facts.organization_id == principal.organization_id
                    and facts.installation_id == facts.expected_installation_id
                    and facts.audience == facts.expected_profile.audience
                    and facts.expected_profile.adapter in facts.allowed_adapters
                    and facts.account_binding_matches
                ),
                checked_at=facts.checked_at,
                expires_at=facts.expires_at,
                revoked_at=facts.revoked_at,
            )

        return PrincipalAccessPolicyInput(
            principal=principal,
            has_pending_recovery=has_pending_recovery,
            credential_is_current=credential_is_current,
        )

    @staticmethod
    def require_current_credential(
        *, access: AccessContextDTO, principal_access: PrincipalAccessPolicyInput
    ) -> None:
        """Preserve credential-family rejection before scope or result disclosure."""
        if not principal_access.credential_is_current:
            if isinstance(access.authentication_evidence, ApplicationKeyAuthenticationDTO):
                raise ApplicationKeyCredentialRejectedError()
            if isinstance(access.authentication_evidence, BrowserSessionAuthenticationDTO):
                raise AuthenticationRequiredError()
            raise HumanOAuthCredentialRejectedError()

    @staticmethod
    def require_human(*, access: AccessContextDTO, principal: Principal) -> None:
        """Deny a verified application at a human-only operation without missing-key facts.

        Evidence-kind mismatches still reach the evaluator's internal contract check.
        """
        if principal.kind is PrincipalKind.APPLICATION and isinstance(
            access.authentication_evidence, ApplicationKeyAuthenticationDTO
        ):
            raise AccessDeniedError()
