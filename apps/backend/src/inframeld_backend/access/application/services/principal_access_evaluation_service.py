from typing import assert_never

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
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.policies.human_credential_policy import HumanCredentialPolicy
from inframeld_backend.access.domain.policy_inputs.principal_access_policy_input import (
    PrincipalAccessPolicyInput,
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
        oauth_credential_facts: HumanOAuthCredentialFactsDTO | None,
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

        if isinstance(evidence, HumanOAuthCredentialBindingDTO):
            if oauth_credential_facts is None:
                raise RuntimeError("Human OAuth evidence requires current credential facts.")
            credential_is_current = HumanCredentialPolicy.is_current_for_actor(
                binding_matches_actor=oauth_credential_facts.binding_matches_actor,
                presented_version=evidence.version,
                current_version=oauth_credential_facts.current_version,
            )
        else:
            credential_is_current = True

        return PrincipalAccessPolicyInput(
            principal=principal,
            has_pending_recovery=has_pending_recovery,
            credential_is_current=credential_is_current,
        )
