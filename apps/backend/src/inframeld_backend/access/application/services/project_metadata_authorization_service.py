from typing import override

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_action_authorization_dto import (
    ProjectActionAuthorizationDTO,
)
from inframeld_backend.access.application.dtos.project_metadata_authorization_facts_dto import (
    ProjectMetadataAuthorizationFactsDTO,
)
from inframeld_backend.access.application.errors.human_oauth_credential_rejected_error import (
    HumanOAuthCredentialRejectedError,
)
from inframeld_backend.access.application.protocols.project_metadata_authorizer import (
    ProjectMetadataAuthorizer,
)
from inframeld_backend.access.application.protocols.project_metadata_facts_reader import (
    ProjectMetadataFactsReader,
)
from inframeld_backend.access.application.services.principal_access_evaluation_service import (
    PrincipalAccessEvaluationService,
)
from inframeld_backend.access.domain.policies.principal_access_policy import PrincipalAccessPolicy
from inframeld_backend.access.domain.policies.project_action_eligibility_policy import (
    ProjectActionEligibilityPolicy,
)
from inframeld_backend.access.domain.policies.project_visibility_policy import (
    ProjectVisibilityPolicy,
)
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ResourceNotFoundError,
)


class ProjectMetadataAuthorizationService(ProjectMetadataAuthorizer):
    def __init__(self, facts: ProjectMetadataFactsReader) -> None:
        self._facts = facts

    @override
    async def require_read(
        self, *, access: AccessContextDTO, project_id: ProjectId
    ) -> ProjectActionAuthorizationDTO:
        facts = await self._facts.read(access=access, project_id=project_id)
        return self._require(facts, access, project_id, change=False)

    @override
    async def require_change(
        self, *, access: AccessContextDTO, project_id: ProjectId
    ) -> ProjectActionAuthorizationDTO:
        facts = await self._facts.read_for_change(access=access, project_id=project_id)
        return self._require(facts, access, project_id, change=True)

    @staticmethod
    def _require(
        facts: ProjectMetadataAuthorizationFactsDTO | None,
        access: AccessContextDTO,
        project_id: ProjectId,
        *,
        change: bool,
    ) -> ProjectActionAuthorizationDTO:
        if facts is None:
            raise ResourceNotFoundError()
        if facts.project_id != project_id or facts.action.principal.id != access.actor_principal_id:
            raise RuntimeError("Metadata authorization facts changed the requested binding.")

        action = facts.action
        eligibility = PrincipalAccessEvaluationService.evaluate(
            access=access,
            principal=action.principal,
            has_pending_recovery=action.has_pending_recovery,
            oauth_credential_facts=action.oauth_credential_facts,
        )
        if not eligibility.credential_is_current:
            raise HumanOAuthCredentialRejectedError()
        if not ProjectVisibilityPolicy.may_view_project(
            principal_status=action.principal.status,
            project_status=action.project_status,
            is_project_member=action.is_project_member,
        ):
            raise ResourceNotFoundError()
        if not PrincipalAccessPolicy.may_use_product(eligibility):
            raise AccessDeniedError()
        if change and (
            not action.has_exact_action_grant
            or not ProjectActionEligibilityPolicy.may_use(
                action_id=ActionId("edit-project-metadata"), principal_kind=action.principal.kind
            )
        ):
            raise AccessDeniedError()

        return ProjectActionAuthorizationDTO(action.principal.organization_id, project_id)
