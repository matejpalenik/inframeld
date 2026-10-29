from typing import override

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.operation_lookup_authorization_dto import (
    OperationLookupAuthorizationDTO,
)
from inframeld_backend.access.application.errors.human_oauth_credential_rejected_error import (
    HumanOAuthCredentialRejectedError,
)
from inframeld_backend.access.application.protocols.operation_lookup_authorizer import (
    OperationLookupAuthorizer,
)
from inframeld_backend.access.application.protocols.operation_lookup_facts_reader import (
    OperationLookupFactsReader,
)
from inframeld_backend.access.application.services.principal_access_evaluation_service import (
    PrincipalAccessEvaluationService,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.policies.principal_access_policy import PrincipalAccessPolicy
from inframeld_backend.access.domain.policies.project_visibility_policy import (
    ProjectVisibilityPolicy,
)
from inframeld_backend.shared.application.enums.operation_lookup_authority_family import (
    OperationLookupAuthorityFamily,
)
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ResourceNotFoundError,
)
from inframeld_backend.shared.application.queries.lookup_original_operation_query import (
    LookupOriginalOperationQuery,
)


class OperationLookupAuthorizationService(OperationLookupAuthorizer):
    def __init__(self, reader: OperationLookupFactsReader) -> None:
        self._reader = reader

    @override
    async def require_authorization(
        self, *, access: AccessContextDTO, request: LookupOriginalOperationQuery
    ) -> OperationLookupAuthorizationDTO:
        request.expected_authority.require_supported_scope(
            project_id=request.project_id,
            method=request.method,
            requested_route=request.requested_route,
        )
        facts = await self._reader.read(access=access, query=request)
        if facts is None:
            raise ResourceNotFoundError()
        if facts.principal.id != access.actor_principal_id:
            raise RuntimeError("Lookup facts returned another principal.")
        if (
            facts.installation_id != request.installation_id
            or facts.principal.organization_id != request.organization_id
        ):
            raise ResourceNotFoundError()

        eligibility = PrincipalAccessEvaluationService.evaluate(
            access=access,
            principal=facts.principal,
            has_pending_recovery=facts.has_pending_recovery,
            oauth_credential_facts=facts.oauth_credential_facts,
        )
        if not eligibility.credential_is_current:
            raise HumanOAuthCredentialRejectedError()

        if request.project_id is not None:
            if facts.project_status is None:
                raise ResourceNotFoundError()
            if not ProjectVisibilityPolicy.may_view_project(
                principal_status=facts.principal.status,
                project_status=facts.project_status,
                is_project_member=facts.is_project_member,
            ):
                raise ResourceNotFoundError()

        if (
            facts.principal.kind is not PrincipalKind.HUMAN
            or not PrincipalAccessPolicy.may_use_product(eligibility)
        ):
            raise AccessDeniedError()
        required_grant = (
            facts.can_grant_action
            if request.expected_authority.family
            is OperationLookupAuthorityFamily.PROJECT_GRANT_READ
            else facts.has_exact_action_grant
        )
        if not required_grant:
            raise AccessDeniedError()
        return OperationLookupAuthorizationDTO(facts.principal.organization_id, request.project_id)
