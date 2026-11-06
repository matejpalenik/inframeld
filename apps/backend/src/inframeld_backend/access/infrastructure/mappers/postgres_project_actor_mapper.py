from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
    HumanOAuthCredentialBindingDTO,
)
from inframeld_backend.access.application.dtos.human_oauth_credential_facts_dto import (
    HumanOAuthCredentialFactsDTO,
)
from inframeld_backend.access.application.dtos.project_action_facts_dto import ProjectActionFactsDTO
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow


class PostgresProjectActorMapper:
    @staticmethod
    def action(
        *,
        access: AccessContextDTO,
        principal: PrincipalRow,
        project: ProjectRow,
        member: bool,
        recovering: bool,
        linked: bool,
        version: int | None,
        granted: bool,
    ) -> ProjectActionFactsDTO:
        return ProjectActionFactsDTO(
            principal=Principal(
                PrincipalId(principal.id),
                OrganizationId(principal.organization_id),
                principal.kind,
                principal.status,
            ),
            has_pending_recovery=recovering,
            oauth_credential_facts=HumanOAuthCredentialFactsDTO(
                linked, HumanCredentialVersion(version) if version is not None else None
            )
            if isinstance(access.authentication_evidence, HumanOAuthCredentialBindingDTO)
            else None,
            project_status=project.status,
            is_project_member=member,
            has_exact_action_grant=granted,
        )
