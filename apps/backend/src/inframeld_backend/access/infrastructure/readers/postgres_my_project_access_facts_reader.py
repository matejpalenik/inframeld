from typing import override
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    ColumnElement,
    Integer,
    Nullable,
    String,
    and_,
    exists,
    literal,
    select,
    true,
    tuple_,
    union_all,
)
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.access_group_grant_target_dto import (
    AccessGroupGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.application_account_grant_target_dto import (
    ApplicationAccountGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
    HumanOAuthCredentialBindingDTO,
)
from inframeld_backend.access.application.dtos.human_oauth_credential_facts_dto import (
    HumanOAuthCredentialFactsDTO,
)
from inframeld_backend.access.application.dtos.my_project_access_facts_dto import (
    MyProjectAccessFactsDTO,
)
from inframeld_backend.access.application.dtos.my_project_access_grant_dto import (
    MyProjectAccessGrantDTO,
)
from inframeld_backend.access.application.dtos.my_project_access_relationship_dto import (
    MyProjectAccessRelationshipDTO,
)
from inframeld_backend.access.application.dtos.project_grant_target_dto import ProjectGrantTargetDTO
from inframeld_backend.access.application.protocols.my_project_access_facts_reader import (
    MyProjectAccessFactsReader,
)
from inframeld_backend.access.application.value_objects.my_project_access_position import (
    MyProjectAccessPosition,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
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
from inframeld_backend.access.infrastructure.rows.access_group_row import AccessGroupRow
from inframeld_backend.access.infrastructure.rows.application_account_row import (
    ApplicationAccountRow,
)
from inframeld_backend.access.infrastructure.rows.application_action_grant_row import (
    ApplicationActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.group_action_grant_row import GroupActionGrantRow
from inframeld_backend.access.infrastructure.rows.group_manager_row import GroupManagerRow
from inframeld_backend.access.infrastructure.rows.group_membership_row import GroupMembershipRow
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
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.infrastructure.rows.installation_identity_row import (
    InstallationIdentityRow,
)


class PostgresMyProjectAccessFactsReader(MyProjectAccessFactsReader):
    """Observe current actor, revision and all own relationship kinds in one snapshot."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def read_page(
        self,
        *,
        access: AccessContextDTO,
        project_id: ProjectId,
        after: MyProjectAccessPosition | None,
        limit: int,
    ) -> MyProjectAccessFactsDTO | None:
        relationships = union_all(
            select(
                literal(0, Integer).label("kind_order"),
                literal("project", String).label("target_kind"),
                ProjectActionGrantRow.project_id.label("target_id"),
                ProjectActionGrantRow.action.label("action_id"),
                ProjectActionGrantRow.can_grant.label("can_grant"),
            )
            .where(
                ProjectActionGrantRow.project_id == ProjectRow.id,
                ProjectActionGrantRow.recipient_principal_id == PrincipalRow.id,
                ProjectActionGrantRow.recipient_kind == PrincipalRow.kind,
            )
            .correlate(PrincipalRow, ProjectRow),
            select(
                literal(0, Integer),
                literal("access_group", String),
                GroupActionGrantRow.group_id,
                GroupActionGrantRow.action,
                GroupActionGrantRow.can_grant,
            )
            .join(
                AccessGroupRow,
                and_(
                    AccessGroupRow.id == GroupActionGrantRow.group_id,
                    AccessGroupRow.project_id == GroupActionGrantRow.project_id,
                ),
            )
            .where(
                GroupActionGrantRow.project_id == ProjectRow.id,
                GroupActionGrantRow.recipient_principal_id == PrincipalRow.id,
                GroupActionGrantRow.recipient_kind == PrincipalRow.kind,
            )
            .correlate(PrincipalRow, ProjectRow),
            select(
                literal(0, Integer),
                literal("application_account", String),
                ApplicationActionGrantRow.application_principal_id,
                ApplicationActionGrantRow.action,
                ApplicationActionGrantRow.can_grant,
            )
            .join(
                ApplicationAccountRow,
                and_(
                    ApplicationAccountRow.principal_id
                    == ApplicationActionGrantRow.application_principal_id,
                    ApplicationAccountRow.project_id == ApplicationActionGrantRow.project_id,
                    ApplicationAccountRow.organization_id == PrincipalRow.organization_id,
                ),
            )
            .where(
                ApplicationActionGrantRow.project_id == ProjectRow.id,
                ApplicationActionGrantRow.recipient_principal_id == PrincipalRow.id,
                ApplicationActionGrantRow.recipient_kind == PrincipalRow.kind,
            )
            .correlate(PrincipalRow, ProjectRow),
            select(
                literal(1, Integer),
                literal("access_group", String),
                GroupMembershipRow.group_id,
                literal("", String),
                literal(None, Boolean),
            )
            .join(
                AccessGroupRow,
                and_(
                    AccessGroupRow.id == GroupMembershipRow.group_id,
                    AccessGroupRow.project_id == GroupMembershipRow.project_id,
                ),
            )
            .where(
                GroupMembershipRow.project_id == ProjectRow.id,
                GroupMembershipRow.principal_id == PrincipalRow.id,
            )
            .correlate(PrincipalRow, ProjectRow),
            select(
                literal(2, Integer),
                literal("access_group", String),
                GroupManagerRow.group_id,
                literal("", String),
                literal(None, Boolean),
            )
            .join(
                AccessGroupRow,
                and_(
                    AccessGroupRow.id == GroupManagerRow.group_id,
                    AccessGroupRow.project_id == GroupManagerRow.project_id,
                ),
            )
            .where(
                GroupManagerRow.project_id == ProjectRow.id,
                GroupManagerRow.principal_id == PrincipalRow.id,
                GroupManagerRow.principal_kind == PrincipalRow.kind,
            )
            .correlate(PrincipalRow, ProjectRow),
        ).subquery("own_relationships")
        # SQLAlchemy compound projections expose their columns dynamically.
        kind: ColumnElement[int] = relationships.c.kind_order
        target: ColumnElement[str] = relationships.c.target_kind
        target_id: ColumnElement[UUID] = relationships.c.target_id
        action: ColumnElement[str] = relationships.c.action_id
        can_grant: ColumnElement[bool | None] = relationships.c.can_grant
        page = select(kind, target, target_id, action, can_grant)
        if after is not None:
            page = page.where(
                tuple_(kind, target_id, action)
                > (
                    after.sort_key[0],
                    after.target_id,
                    after.action_id.value if after.action_id else "",
                )
            )
        bounded = (
            page.order_by(kind, target_id, action)
            .limit(limit + 1)
            .correlate(PrincipalRow, ProjectRow)
            .lateral("own_access_page")
        )
        page_kind: ColumnElement[int] = bounded.c.kind_order
        page_target: ColumnElement[str] = bounded.c.target_kind
        page_target_id: ColumnElement[UUID] = bounded.c.target_id
        page_action: ColumnElement[str] = bounded.c.action_id
        page_can_grant: ColumnElement[bool | None] = bounded.c.can_grant
        member = (
            exists()
            .where(
                ProjectMembershipRow.project_id == ProjectRow.id,
                ProjectMembershipRow.principal_id == PrincipalRow.id,
                ProjectMembershipRow.organization_id == PrincipalRow.organization_id,
            )
            .correlate(PrincipalRow, ProjectRow)
        )
        pending = (
            select(IdentityRecoveryAdmissionRow.operation_id)
            .join(
                HumanIdentityLinkRow,
                and_(
                    HumanIdentityLinkRow.authority == IdentityRecoveryAdmissionRow.authority,
                    HumanIdentityLinkRow.subject == IdentityRecoveryAdmissionRow.subject,
                ),
            )
            .where(
                IdentityRecoveryAdmissionRow.installation_id
                == InstallationIdentityRow.installation_id,
                HumanIdentityLinkRow.principal_id == PrincipalRow.id,
                IdentityRecoveryAdmissionRow.released_at.is_(None),
            )
            .exists()
            .correlate(PrincipalRow, InstallationIdentityRow)
        )
        evidence = access.authentication_evidence
        matches = (
            HumanCredentialStateQueries.binding_matches_actor(evidence)
            if isinstance(evidence, HumanOAuthCredentialBindingDTO)
            else literal(False)
        )
        version = (
            Nullable(HumanCredentialStateQueries.version_for_actor(evidence))
            if isinstance(evidence, HumanOAuthCredentialBindingDTO)
            else Nullable(literal(None, BigInteger))
        )
        statement = (
            select(
                PrincipalRow,
                ProjectRow,
                Nullable(InstallationIdentityRow.installation_id),
                member.label("actor_is_project_member"),
                pending.label("actor_pending_recovery"),
                matches,
                version,
                Nullable(page_kind),
                Nullable(page_target),
                Nullable(page_target_id),
                Nullable(page_action),
                page_can_grant,
            )
            .select_from(PrincipalRow)
            .join(
                ProjectRow,
                and_(
                    ProjectRow.id == project_id.value,
                    ProjectRow.organization_id == PrincipalRow.organization_id,
                ),
            )
        )
        statement = (
            statement.outerjoin(InstallationIdentityRow, InstallationIdentityRow.singleton_key == 1)
            .outerjoin(bounded, true())
            .where(PrincipalRow.id == access.actor_principal_id.value)
            .order_by(page_kind, page_target_id, page_action)
            .execution_options(populate_existing=True, autoflush=False)
        )
        try:
            rows = (await self._session.execute(statement)).tuples().all()
        except (OperationalError, SqlAlchemyTimeoutError) as error:
            raise DependencyUnavailableError() from error
        if not rows:
            return None
        principal, project, installation, membership, recovering, linked, credential_version, *_ = (
            rows[0]
        )
        if installation is None:
            raise DependencyUnavailableError("The installation identity is not available.")
        items: list[MyProjectAccessGrantDTO | MyProjectAccessRelationshipDTO] = []
        for _, _, _, _, _, _, _, item_kind, item_target, item_id, item_action, item_level in rows:
            if item_kind is None:
                continue
            if item_id is None:
                raise RuntimeError("The own-access observation lost its target.")
            if item_kind == 0:
                if item_action is None or item_level is None:
                    raise RuntimeError("The own grant observation lost its action or level.")
                if item_target == "project":
                    concrete_target = ProjectGrantTargetDTO(ProjectId(item_id))
                elif item_target == "access_group":
                    concrete_target = AccessGroupGrantTargetDTO(project_id, AccessGroupId(item_id))
                elif item_target == "application_account":
                    concrete_target = ApplicationAccountGrantTargetDTO(
                        project_id, PrincipalId(item_id)
                    )
                else:
                    raise RuntimeError("The own grant observation has an unsupported target.")
                items.append(
                    MyProjectAccessGrantDTO(concrete_target, ActionId(item_action), item_level)
                )
            elif item_kind in (1, 2) and item_target == "access_group":
                items.append(
                    MyProjectAccessRelationshipDTO(
                        "membership" if item_kind == 1 else "management",
                        project_id,
                        AccessGroupId(item_id),
                    )
                )
            else:
                raise RuntimeError("The own relationship observation has an unsupported kind.")
        return MyProjectAccessFactsDTO(
            InstallationId(installation),
            OrganizationId(principal.organization_id),
            project_id,
            project.access_revision,
            Principal(
                PrincipalId(principal.id),
                OrganizationId(principal.organization_id),
                principal.kind,
                principal.status,
            ),
            recovering,
            HumanOAuthCredentialFactsDTO(
                linked,
                HumanCredentialVersion(credential_version)
                if credential_version is not None
                else None,
            )
            if isinstance(evidence, HumanOAuthCredentialBindingDTO)
            else None,
            project.status,
            membership,
            tuple(items),
        )
