from typing import override

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_creation_authorization_dto import (
    ProjectCreationAuthorizationDTO,
)
from inframeld_backend.access.application.errors.human_oauth_credential_rejected_error import (
    HumanOAuthCredentialRejectedError,
)
from inframeld_backend.access.application.protocols.organization_access_facts_reader import (
    OrganizationAccessFactsReader,
)
from inframeld_backend.access.application.protocols.project_creation_authorizer import (
    ProjectCreationAuthorizer,
)
from inframeld_backend.access.application.services.principal_access_evaluation_service import (
    PrincipalAccessEvaluationService,
)
from inframeld_backend.access.domain.enums.organization_action import OrganizationAction
from inframeld_backend.access.domain.policies.project_creation_policy import ProjectCreationPolicy
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ResourceNotFoundError,
)


class ProjectCreationAuthorizationService(ProjectCreationAuthorizer):
    def __init__(self, organization_access_facts_reader: OrganizationAccessFactsReader) -> None:
        self._organization_access_facts_reader = organization_access_facts_reader

    @override
    async def require_creation(
        self, *, access: AccessContextDTO, organization_id: OrganizationId
    ) -> ProjectCreationAuthorizationDTO:
        facts = await self._organization_access_facts_reader.read_for_creation(
            access=access, organization_id=organization_id
        )
        if facts is None:
            raise ResourceNotFoundError()
        if facts.principal.id != access.actor_principal_id:
            raise RuntimeError("Creation facts changed the authenticated actor.")
        if facts.principal.organization_id != organization_id:
            raise ResourceNotFoundError()

        eligibility = PrincipalAccessEvaluationService.evaluate(
            access=access,
            principal=facts.principal,
            has_pending_recovery=facts.has_pending_recovery,
            oauth_credential_facts=facts.oauth_credential_facts,
        )
        if not eligibility.credential_is_current:
            raise HumanOAuthCredentialRejectedError()
        if not ProjectCreationPolicy.may_create(
            eligibility,
            has_create_projects=any(
                grant.action_id.value == OrganizationAction.CREATE_PROJECTS.value
                for grant in facts.grants
            ),
        ):
            raise AccessDeniedError()

        return ProjectCreationAuthorizationDTO(organization_id, facts.access_revision)
