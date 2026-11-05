from dataclasses import dataclass

from inframeld_backend.access.application.dtos.project_action_facts_dto import ProjectActionFactsDTO
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.errors.application_errors import ResourceNotFoundError
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


@dataclass(frozen=True, slots=True)
class ProjectMembershipObservationDTO:
    """Bind membership observations to their actor, Project and Access revision.

    Scope validation establishes coherence, without deciding current permission.
    """

    installation_id: InstallationId
    organization_id: OrganizationId
    project_id: ProjectId
    access_revision: int
    action: ProjectActionFactsDTO

    @staticmethod
    def require_requested_scope[Observation: ProjectMembershipObservationDTO](
        *,
        observation: Observation | None,
        actor_principal_id: PrincipalId,
        project_id: ProjectId,
    ) -> Observation:
        """Reject absent or substituted facts before authorization or protected use."""
        if observation is None:
            raise ResourceNotFoundError()
        if (
            observation.project_id != project_id
            or observation.action.principal.id != actor_principal_id
            or observation.action.principal.organization_id != observation.organization_id
            or observation.access_revision < 0
        ):
            raise RuntimeError("The Project membership observation changed its actor or scope.")

        return observation
