import asyncio
from typing import final, override

from sqlalchemy import BigInteger, Nullable, and_, exists, literal, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
    HumanOAuthCredentialBindingDTO,
)
from inframeld_backend.access.application.dtos.human_oauth_credential_facts_dto import (
    HumanOAuthCredentialFactsDTO,
)
from inframeld_backend.access.application.dtos.project_grant_change_facts_dto import (
    ProjectGrantChangeFactsDTO,
)
from inframeld_backend.access.application.protocols.project_grant_change_facts_reader import (
    ProjectGrantChangeFactsReader,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.readers.human_credential_state_queries import (
    HumanCredentialStateQueries,
)
from inframeld_backend.access.infrastructure.rows.human_identity_link_row import (
    HumanIdentityLinkRow,
)
from inframeld_backend.access.infrastructure.rows.identity_recovery_admission_row import (
    IdentityRecoveryAdmissionRow,
)
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.project_membership_row import (
    ProjectMembershipRow,
)
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.infrastructure.rows.installation_identity_row import (
    InstallationIdentityRow,
)

_GRANT_FACTS_TIMEOUT_SECONDS = 5.0


def _to_principal(row: PrincipalRow) -> Principal:
    return Principal(
        id=PrincipalId(row.id),
        organization_id=OrganizationId(row.organization_id),
        kind=row.kind,
        status=row.status,
    )


@final
class PostgresProjectGrantChangeFactsReader(ProjectGrantChangeFactsReader):
    """Acquire Access locks and load facts within one five-second database deadline.

    The caller owns the transaction and retains acquired locks until commit or
    rollback. Deadline expiry requires the caller to roll back.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def read_for_change(
        self,
        *,
        access: AccessContextDTO,
        project_id: ProjectId,
        recipient_principal_id: PrincipalId,
        action_id: ActionId,
    ) -> ProjectGrantChangeFactsDTO | None:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + _GRANT_FACTS_TIMEOUT_SECONDS
        try:
            async with asyncio.timeout_at(deadline):
                facts = await self._read_for_change(
                    access=access,
                    project_id=project_id,
                    recipient_principal_id=recipient_principal_id,
                    action_id=action_id,
                )
                if loop.time() >= deadline:
                    raise TimeoutError()
                return facts
        except TimeoutError as error:
            raise DependencyUnavailableError(
                "Grant authorization exceeded its database deadline."
            ) from error

    async def _read_for_change(
        self,
        *,
        access: AccessContextDTO,
        project_id: ProjectId,
        recipient_principal_id: PrincipalId,
        action_id: ActionId,
    ) -> ProjectGrantChangeFactsDTO | None:
        actor_organization_id = await self._session.scalar(
            select(PrincipalRow.organization_id).where(
                PrincipalRow.id == access.actor_principal_id.value
            )
        )
        if actor_organization_id is None:
            return None

        # Acquire the organization lock before the project lock.
        locked_organization_id = await self._session.scalar(
            select(OrganizationRow.id)
            .where(OrganizationRow.id == actor_organization_id)
            .with_for_update(read=True)
        )
        if locked_organization_id is None:
            return None

        locked_project_id = await self._session.scalar(
            select(ProjectRow.id)
            .where(
                ProjectRow.id == project_id.value,
                ProjectRow.organization_id == locked_organization_id,
            )
            .with_for_update()
        )
        if locked_project_id is None:
            return None

        recipient = aliased(PrincipalRow, name="recipient")

        actor_is_member = exists().where(
            ProjectMembershipRow.project_id == ProjectRow.id,
            ProjectMembershipRow.principal_id == PrincipalRow.id,
        )
        recipient_is_member = exists().where(
            ProjectMembershipRow.project_id == ProjectRow.id,
            ProjectMembershipRow.principal_id == recipient.id,
        )
        actor_can_grant = exists().where(
            ProjectActionGrantRow.project_id == ProjectRow.id,
            ProjectActionGrantRow.recipient_principal_id == PrincipalRow.id,
            ProjectActionGrantRow.action == action_id.value,
            ProjectActionGrantRow.can_grant.is_(True),
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

        evidence = access.authentication_evidence
        if isinstance(evidence, HumanOAuthCredentialBindingDTO):
            binding_matches_actor = HumanCredentialStateQueries.binding_matches_actor(evidence)
            credential_version = Nullable(HumanCredentialStateQueries.version_for_actor(evidence))
        else:
            binding_matches_actor = literal(False)
            credential_version = Nullable(literal(None, BigInteger))

        statement = (
            select(
                PrincipalRow,
                Nullable(recipient),
                ProjectRow,
                actor_is_member,
                recipient_is_member,
                actor_can_grant,
                installation_available,
                has_pending_recovery,
                binding_matches_actor,
                credential_version,
            )
            .select_from(PrincipalRow)
            .join(
                ProjectRow,
                and_(
                    ProjectRow.id == locked_project_id,
                    ProjectRow.organization_id == PrincipalRow.organization_id,
                ),
            )
            .outerjoin(
                recipient,
                and_(
                    recipient.id == recipient_principal_id.value,
                    recipient.organization_id == PrincipalRow.organization_id,
                ),
            )
            .where(
                PrincipalRow.id == access.actor_principal_id.value,
                PrincipalRow.organization_id == locked_organization_id,
            )
            .execution_options(populate_existing=True)
        )

        result = await self._session.execute(statement)
        row = result.tuples().one_or_none()
        if row is None:
            return None

        (
            actor_row,
            recipient_row,
            project_row,
            actor_member,
            recipient_member,
            can_grant,
            has_installation,
            pending_recovery,
            matches_actor,
            current_credential_version,
        ) = row

        if not has_installation:
            raise DependencyUnavailableError("The installation identity is not available.")

        return ProjectGrantChangeFactsDTO(
            actor=_to_principal(actor_row),
            has_pending_recovery=pending_recovery,
            oauth_credential_facts=(
                HumanOAuthCredentialFactsDTO(
                    binding_matches_actor=matches_actor,
                    current_version=HumanCredentialVersion(current_credential_version)
                    if current_credential_version is not None
                    else None,
                )
                if isinstance(evidence, HumanOAuthCredentialBindingDTO)
                else None
            ),
            recipient=(_to_principal(recipient_row) if recipient_row is not None else None),
            project_status=project_row.status,
            project_access_revision=project_row.access_revision,
            actor_is_project_member=actor_member,
            recipient_is_project_member=recipient_member,
            actor_can_grant_action=can_grant,
        )
