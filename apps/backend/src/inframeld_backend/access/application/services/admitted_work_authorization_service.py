from typing import override

from inframeld_backend.access.application.dtos.admitted_work_authority_dto import (
    AdmittedWorkAuthorityDTO,
)
from inframeld_backend.access.application.protocols.admitted_work_authorizer import (
    AdmittedWorkAuthorizer,
)
from inframeld_backend.access.application.protocols.admitted_work_facts_reader import (
    AdmittedWorkFactsReader,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.policies.human_credential_policy import HumanCredentialPolicy
from inframeld_backend.access.domain.policies.principal_access_policy import PrincipalAccessPolicy
from inframeld_backend.access.domain.policy_inputs.principal_access_policy_input import (
    PrincipalAccessPolicyInput,
)
from inframeld_backend.shared.application.errors.application_errors import AccessDeniedError


class AdmittedWorkAuthorizationService(AdmittedWorkAuthorizer):
    def __init__(self, facts: AdmittedWorkFactsReader) -> None:
        self._facts = facts

    @override
    async def require_current(self, authority: AdmittedWorkAuthorityDTO) -> None:
        facts = await self._facts.read(authority)
        if facts is None or (
            facts.principal.id != authority.principal_id
            or facts.principal.organization_id != authority.organization_id
            or facts.principal.kind is not authority.principal_kind
            or facts.installation_id != authority.installation_id
        ):
            raise AccessDeniedError("The admitted work no longer has its original authority.")

        generation_current = True
        if authority.principal_kind is PrincipalKind.HUMAN:
            binding = authority.human_binding
            generation = facts.human_generation
            if binding is None or generation is None:
                raise AccessDeniedError("The admitted human security generation is unavailable.")
            generation_current = HumanCredentialPolicy.is_current_for_actor(
                binding_matches_actor=generation.binding_matches_actor,
                presented_version=binding.version,
                current_version=generation.current_version,
            )
        elif authority.human_binding is not None:
            raise AccessDeniedError("The admitted authority has an incompatible identity.")

        eligibility = PrincipalAccessPolicyInput(
            facts.principal, facts.has_pending_recovery, generation_current
        )
        if not (
            PrincipalAccessPolicy.may_use_product(eligibility)
            and facts.project_status is ProjectStatus.ACTIVE
            and facts.is_project_member
            and facts.has_exact_action_grant
        ):
            raise AccessDeniedError("The admitted work no longer has current authority.")
