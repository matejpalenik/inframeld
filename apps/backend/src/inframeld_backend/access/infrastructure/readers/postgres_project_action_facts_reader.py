from typing import final, override

from sqlalchemy import and_, exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_action_facts_dto import ProjectActionFactsDTO
from inframeld_backend.access.application.dtos.project_action_target_dto import (
    ProjectActionTargetDTO,
)
from inframeld_backend.access.application.protocols.project_action_facts_reader import (
    ProjectActionFactsReader,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.policy_inputs.principal_access_policy_input import (
    PrincipalAccessPolicyInput,
)
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.infrastructure.rows.human_identity_link_row import (
    HumanIdentityLinkRow,
)
from inframeld_backend.access.infrastructure.rows.identity_recovery_admission_row import (
    IdentityRecoveryAdmissionRow,
)
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.project_membership_row import ProjectMembershipRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.infrastructure.rows.installation_identity_row import (
    InstallationIdentityRow,
)


@final
class PostgresProjectActionFactsReader(ProjectActionFactsReader):
    """Load current authorization facts in one statement using the caller's session.

    The caller owns the transaction. Missing installation metadata fails closed
    because recovery eligibility cannot be established without it.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def read_action_facts(
        self, *, access: AccessContextDTO, action_id: ActionId, target: ProjectActionTargetDTO
    ) -> ProjectActionFactsDTO | None:
        is_project_member = exists().where(
            ProjectMembershipRow.project_id == ProjectRow.id,
            ProjectMembershipRow.principal_id == PrincipalRow.id,
        )

        has_exact_action_grant = exists().where(
            ProjectActionGrantRow.project_id == ProjectRow.id,
            ProjectActionGrantRow.recipient_principal_id == PrincipalRow.id,
            ProjectActionGrantRow.action == action_id.value,
        )

        installation_available = exists().where(
            InstallationIdentityRow.singleton_key == 1,
        )

        has_pending_recovery = (
            select(IdentityRecoveryAdmissionRow.operation_id)
            .join(
                HumanIdentityLinkRow,
                and_(
                    HumanIdentityLinkRow.authority == IdentityRecoveryAdmissionRow.authority,
                    HumanIdentityLinkRow.subject == IdentityRecoveryAdmissionRow.subject,
                ),
            )
            .join(
                InstallationIdentityRow,
                InstallationIdentityRow.installation_id
                == IdentityRecoveryAdmissionRow.installation_id,
            )
            .where(
                InstallationIdentityRow.singleton_key == 1,
                HumanIdentityLinkRow.principal_id == PrincipalRow.id,
                IdentityRecoveryAdmissionRow.released_at.is_(None),
            )
            .exists()
            .correlate(PrincipalRow)
        )

        statement = (
            select(
                PrincipalRow.id,
                ProjectRow.organization_id,
                PrincipalRow.kind,
                PrincipalRow.status,
                ProjectRow.status,
                is_project_member,
                has_exact_action_grant,
                installation_available,
                has_pending_recovery,
            )
            .select_from(PrincipalRow)
            .join(
                ProjectRow,
                and_(
                    ProjectRow.id == target.project_id.value,
                    ProjectRow.organization_id == PrincipalRow.organization_id,
                ),
            )
            .where(PrincipalRow.id == access.actor_principal_id.value)
        )

        result = await self._session.execute(statement)
        row = result.tuples().one_or_none()

        if row is None:
            return None

        (
            principal_id,
            organization_id,
            principal_kind,
            principal_status,
            project_status,
            member,
            granted,
            has_installation,
            pending_recovery,
        ) = row

        if not has_installation:
            raise DependencyUnavailableError("The installation identity is not available.")

        principal = Principal(
            id=PrincipalId(principal_id),
            organization_id=OrganizationId(organization_id),
            kind=principal_kind,
            status=principal_status,
        )

        return ProjectActionFactsDTO(
            principal_access=PrincipalAccessPolicyInput(
                principal=principal,
                has_pending_recovery=pending_recovery,
            ),
            project_status=project_status,
            is_project_member=member,
            has_exact_action_grant=granted,
        )
