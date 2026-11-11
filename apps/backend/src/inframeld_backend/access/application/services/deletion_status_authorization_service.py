from typing import override

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.browser_session_authentication_dto import (
    BrowserSessionAuthenticationDTO,
)
from inframeld_backend.access.application.dtos.deletion_recovery_authorization_dto import (
    DeletionRecoveryAuthorizationDTO,
)
from inframeld_backend.access.application.dtos.deletion_status_authorization_dto import (
    DeletionStatusAuthorizationDTO,
)
from inframeld_backend.access.application.dtos.deletion_status_authorization_request_dto import (
    DeletionStatusAuthorizationRequestDTO,
)
from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
    HumanOAuthCredentialBindingDTO,
)
from inframeld_backend.access.application.protocols.deletion_recovery_authorizer import (
    DeletionRecoveryAuthorizer,
)
from inframeld_backend.access.application.protocols.deletion_status_authorizer import (
    DeletionStatusAuthorizer,
)
from inframeld_backend.access.application.protocols.deletion_status_facts_reader import (
    DeletionStatusFactsReader,
)
from inframeld_backend.access.application.services.principal_access_evaluation_service import (
    PrincipalAccessEvaluationService,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.policies.principal_access_policy import PrincipalAccessPolicy
from inframeld_backend.shared.application.errors.application_errors import AccessDeniedError


class DeletionStatusAuthorizationService(DeletionStatusAuthorizer, DeletionRecoveryAuthorizer):
    """Check current human eligibility before permitting original-initiator matching."""

    def __init__(self, deletion_status_facts_reader: DeletionStatusFactsReader) -> None:
        self._deletion_status_facts_reader = deletion_status_facts_reader

    @override
    async def require_authorization(
        self, *, access: AccessContextDTO, request: DeletionStatusAuthorizationRequestDTO
    ) -> DeletionStatusAuthorizationDTO:
        current = await self.require_current_human(access=access)
        return DeletionStatusAuthorizationDTO(
            request.operation_id,
            current.installation_id,
            current.organization_id,
            current.principal_id,
        )

    @override
    async def require_current_human(
        self, *, access: AccessContextDTO
    ) -> DeletionRecoveryAuthorizationDTO:
        facts = await self._deletion_status_facts_reader.read(access=access)
        if facts is None:
            raise AccessDeniedError()
        if facts.principal.id != access.actor_principal_id:
            raise RuntimeError("Deletion status facts returned a different principal.")
        if facts.principal.kind is not PrincipalKind.HUMAN or not isinstance(
            access.authentication_evidence,
            BrowserSessionAuthenticationDTO | HumanOAuthCredentialBindingDTO,
        ):
            raise AccessDeniedError()

        eligibility = PrincipalAccessEvaluationService.evaluate(
            access=access,
            principal=facts.principal,
            has_pending_recovery=facts.has_pending_recovery,
            oauth_credential_facts=facts.oauth_credential_facts,
        )
        PrincipalAccessEvaluationService.require_current_credential(
            access=access, principal_access=eligibility
        )
        if not PrincipalAccessPolicy.may_use_product(eligibility):
            raise AccessDeniedError()

        return DeletionRecoveryAuthorizationDTO(
            facts.installation_id,
            facts.principal.organization_id,
            facts.principal.id,
        )
