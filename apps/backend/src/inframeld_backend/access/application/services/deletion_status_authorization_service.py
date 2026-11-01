from typing import override

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.browser_session_authentication_dto import (
    BrowserSessionAuthenticationDTO,
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
from inframeld_backend.access.application.errors.human_oauth_credential_rejected_error import (
    HumanOAuthCredentialRejectedError,
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


class DeletionStatusAuthorizationService(DeletionStatusAuthorizer):
    """Check current human eligibility before permitting original-initiator matching."""

    def __init__(self, reader: DeletionStatusFactsReader) -> None:
        self._reader = reader

    @override
    async def require_authorization(
        self, *, access: AccessContextDTO, request: DeletionStatusAuthorizationRequestDTO
    ) -> DeletionStatusAuthorizationDTO:
        facts = await self._reader.read(access=access)
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
        if not eligibility.credential_is_current:
            raise HumanOAuthCredentialRejectedError()
        if not PrincipalAccessPolicy.may_use_product(eligibility):
            raise AccessDeniedError()

        return DeletionStatusAuthorizationDTO(
            request.operation_id,
            facts.installation_id,
            facts.principal.organization_id,
            facts.principal.id,
        )
