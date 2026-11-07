from dataclasses import replace
from typing import override

from sqlalchemy import String, exists, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.commands.change_access_group_relationship_command import (
    ChangeAccessGroupRelationshipCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.access_group_change_facts_dto import (
    AccessGroupChangeFactsDTO,
)
from inframeld_backend.access.application.dtos.access_group_metadata_dto import (
    AccessGroupMetadataDTO,
)
from inframeld_backend.access.application.dtos.access_group_principal_dto import (
    AccessGroupPrincipalDTO,
)
from inframeld_backend.access.application.dtos.access_group_read_facts_dto import (
    AccessGroupReadFactsDTO,
)
from inframeld_backend.access.application.dtos.application_key_authentication_dto import (
    ApplicationKeyAuthenticationDTO,
)
from inframeld_backend.access.application.dtos.application_key_verification_profile_dto import (
    ApplicationKeyVerificationProfileDTO,
)
from inframeld_backend.access.application.dtos.project_departure_candidate_dto import (
    ProjectDepartureCandidateDTO,
)
from inframeld_backend.access.application.enums.access_group_collection import AccessGroupCollection
from inframeld_backend.access.application.protocols.access_group_change_facts_reader import (
    AccessGroupChangeFactsReader,
)
from inframeld_backend.access.application.protocols.access_group_deletion_facts_reader import (
    AccessGroupDeletionFactsReader,
)
from inframeld_backend.access.application.protocols.access_group_read_facts_reader import (
    AccessGroupReadFactsReader,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.access_group_action import AccessGroupAction
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
from inframeld_backend.access.domain.value_objects.access_group_relationships import (
    AccessGroupRelationships,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.mappers.postgres_application_key_facts_mapper import (
    PostgresApplicationKeyFactsMapper,
)
from inframeld_backend.access.infrastructure.mappers.postgres_project_actor_mapper import (
    PostgresProjectActorMapper,
)
from inframeld_backend.access.infrastructure.readers.application_key_state_queries import (
    ApplicationKeyStateQueries,
)
from inframeld_backend.access.infrastructure.readers.project_actor_queries import (
    ProjectActorQueries,
)
from inframeld_backend.access.infrastructure.readers.project_principal_queries import (
    ProjectPrincipalQueries,
)
from inframeld_backend.access.infrastructure.rows.access_group_name_reservation_row import (
    AccessGroupNameReservationRow,
)
from inframeld_backend.access.infrastructure.rows.access_group_row import AccessGroupRow
from inframeld_backend.access.infrastructure.rows.application_key_row import ApplicationKeyRow
from inframeld_backend.access.infrastructure.rows.group_action_grant_row import GroupActionGrantRow
from inframeld_backend.access.infrastructure.rows.group_manager_row import GroupManagerRow
from inframeld_backend.access.infrastructure.rows.group_membership_row import GroupMembershipRow
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName
from inframeld_backend.shared.infrastructure.rows.installation_identity_row import (
    InstallationIdentityRow,
)


class PostgresAccessGroupFactsReader(
    AccessGroupReadFactsReader, AccessGroupChangeFactsReader, AccessGroupDeletionFactsReader
):
    """Read current group facts under compatible Organization and Project coordination."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        application_key_profile: ApplicationKeyVerificationProfileDTO | None = None,
    ) -> None:
        self._session = session
        self._application_key_profile = application_key_profile

    @override
    async def read(
        self,
        *,
        access: AccessContextDTO,
        project_id: ProjectId,
        selector: AccessGroupId | ResourceName,
    ) -> AccessGroupReadFactsDTO | None:
        return await self._observe(access, project_id, selector, exclusive=False)

    @override
    async def lock_for_deletion(
        self, *, access: AccessContextDTO, project_id: ProjectId, group_id: AccessGroupId
    ) -> AccessGroupReadFactsDTO | None:
        return await self._observe(access, project_id, group_id, exclusive=True)

    @override
    async def lock_for_change(
        self, *, access: AccessContextDTO, command: ChangeAccessGroupRelationshipCommand
    ) -> AccessGroupChangeFactsDTO | None:
        try:
            facts = await self._observe(
                access, command.project_id, command.group_id, exclusive=True
            )
            if facts is None:
                return None
            group = facts.group
            principal = PrincipalRow
            recipient = (
                (
                    await self._session.execute(
                        select(
                            principal,
                            ProjectPrincipalQueries.pending(principal.id, facts.installation_id),
                            ProjectPrincipalQueries.membership(
                                principal.id, command.project_id, group.organization_id
                            ),
                            ProjectPrincipalQueries.coherent_identity(
                                principal.id, group.organization_id, facts.installation_id
                            ),
                        )
                        .where(
                            principal.id == command.principal_id.value,
                            principal.organization_id == group.organization_id.value,
                        )
                        .execution_options(populate_existing=True, autoflush=False)
                    )
                )
                .tuples()
                .one_or_none()
            )
            member = await self._session.get(
                GroupMembershipRow,
                (command.project_id.value, command.group_id.value, command.principal_id.value),
                populate_existing=True,
            )
            manager = await self._session.get(
                GroupManagerRow,
                (command.project_id.value, command.group_id.value, command.principal_id.value),
                populate_existing=True,
            )
            return AccessGroupChangeFactsDTO(
                organization_id=group.organization_id,
                project_id=group.project_id,
                access_revision=group.access_revision,
                group_id=group.group_id,
                action=facts.action,
                recipient=Principal(
                    PrincipalId(recipient[0].id),
                    group.organization_id,
                    recipient[0].kind,
                    recipient[0].status,
                )
                if recipient is not None
                else None,
                recipient_is_project_member=recipient[2] if recipient is not None else False,
                recipient_has_coherent_identity=recipient[3] if recipient is not None else False,
                recipient_has_pending_recovery=recipient[1] if recipient is not None else False,
                relationships=AccessGroupRelationships(
                    member=member is not None, manager=manager is not None
                ),
            )
        except (OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None

    @override
    async def remaining_managers(
        self, *, facts: AccessGroupChangeFactsDTO, command: ChangeAccessGroupRelationshipCommand
    ) -> tuple[ProjectDepartureCandidateDTO, ...]:
        try:
            installed = await self._session.scalar(
                select(InstallationIdentityRow.installation_id).where(
                    InstallationIdentityRow.singleton_key == 1
                )
            )
            if installed is None:
                raise DependencyUnavailableError()
            installation = InstallationId(installed)
            member = (
                exists()
                .where(
                    GroupMembershipRow.project_id == command.project_id.value,
                    GroupMembershipRow.group_id == command.group_id.value,
                    GroupMembershipRow.principal_id == PrincipalRow.id,
                )
                .correlate(PrincipalRow)
            )
            rows = (
                (
                    await self._session.execute(
                        select(
                            PrincipalRow,
                            ProjectPrincipalQueries.pending(PrincipalRow.id, installation),
                            ProjectPrincipalQueries.membership(
                                PrincipalRow.id, facts.project_id, facts.organization_id
                            ),
                            ProjectPrincipalQueries.coherent_identity(
                                PrincipalRow.id, facts.organization_id, installation
                            ),
                            member,
                        )
                        .join(GroupManagerRow, GroupManagerRow.principal_id == PrincipalRow.id)
                        .where(
                            GroupManagerRow.project_id == command.project_id.value,
                            GroupManagerRow.group_id == command.group_id.value,
                            PrincipalRow.organization_id == facts.organization_id.value,
                            PrincipalRow.id != command.principal_id.value,
                        )
                        .execution_options(populate_existing=True, autoflush=False)
                    )
                )
                .tuples()
                .all()
            )
            return tuple(
                ProjectDepartureCandidateDTO(
                    principal=Principal(
                        PrincipalId(row.id), facts.organization_id, row.kind, row.status
                    ),
                    has_pending_recovery=pending,
                    is_project_member=project_member,
                    has_coherent_identity=coherent,
                    can_grant=False,
                    is_group_member=group_member,
                    is_group_manager=True,
                )
                for row, pending, project_member, coherent, group_member in rows
            )
        except (OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None

    @override
    async def principals(
        self,
        *,
        facts: AccessGroupReadFactsDTO,
        collection: AccessGroupCollection,
        after: PrincipalId | None,
        limit: int,
    ) -> tuple[AccessGroupPrincipalDTO, ...]:
        try:
            relation = (
                GroupMembershipRow
                if collection is AccessGroupCollection.MEMBERS
                else GroupManagerRow
            )
            query = (
                select(PrincipalRow.id, PrincipalRow.kind, PrincipalRow.display_name)
                .join(relation, relation.principal_id == PrincipalRow.id)
                .where(
                    relation.project_id == facts.group.project_id.value,
                    relation.group_id == facts.group.group_id.value,
                    PrincipalRow.organization_id == facts.group.organization_id.value,
                )
            )
            if after is not None:
                query = query.where(PrincipalRow.id > after.value)
            rows = (
                (await self._session.execute(query.order_by(PrincipalRow.id).limit(limit + 1)))
                .tuples()
                .all()
            )
            return tuple(
                AccessGroupPrincipalDTO(PrincipalId(identifier), kind, display)
                for identifier, kind, display in rows
            )
        except (OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None

    async def _observe(
        self,
        access: AccessContextDTO,
        project_id: ProjectId,
        selector: AccessGroupId | ResourceName,
        *,
        exclusive: bool,
    ) -> AccessGroupReadFactsDTO | None:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Group facts require the active caller transaction.")
        evidence = access.authentication_evidence
        # Change and deletion services reject application actors before credential evaluation.
        application_key = (
            evidence
            if isinstance(evidence, ApplicationKeyAuthenticationDTO) and not exclusive
            else None
        )
        profile = self._application_key_profile
        if application_key is not None and profile is None:
            raise DependencyUnavailableError("The application verification profile is unavailable.")
        try:
            if (
                await self._session.scalar(
                    select(func.current_setting("transaction_isolation", type_=String()))
                )
                != "read committed"
            ):
                raise RuntimeError("Group facts require READ COMMITTED isolation.")
            if application_key is not None:
                scope = (
                    (
                        await self._session.execute(
                            ApplicationKeyStateQueries.account_scope(
                                access.actor_principal_id
                            ).execution_options(autoflush=False)
                        )
                    )
                    .tuples()
                    .one_or_none()
                )
                if scope is None:
                    principal_kind = await self._session.scalar(
                        select(PrincipalRow.kind).where(
                            PrincipalRow.id == access.actor_principal_id.value
                        )
                    )
                    if (
                        principal_kind is not None
                        and principal_kind is not PrincipalKind.APPLICATION
                    ):
                        raise RuntimeError(
                            "Authentication evidence does not match the principal kind."
                        )
                    return None
                _, bound_project = scope
                if bound_project != project_id.value:
                    return None
            organization = await self._session.scalar(
                select(PrincipalRow.organization_id).where(
                    PrincipalRow.id == access.actor_principal_id.value
                )
            )
            if (
                organization is None
                or await self._session.scalar(
                    select(OrganizationRow.id)
                    .where(OrganizationRow.id == organization)
                    .with_for_update(read=True)
                )
                is None
            ):
                return None
            if (
                await self._session.scalar(
                    select(ProjectRow.id)
                    .where(
                        ProjectRow.id == project_id.value,
                        ProjectRow.organization_id == organization,
                    )
                    .with_for_update(read=not exclusive)
                )
                is None
            ):
                return None
            if application_key is not None:
                key_scope = ApplicationKeyStateQueries.key_scope(
                    key_id=application_key.key_id,
                    principal_id=access.actor_principal_id,
                    organization_id=OrganizationId(organization),
                    project_id=project_id,
                )
                # Retain the caller's shared key lock against ordinary revocation UPDATEs.
                await self._session.scalar(
                    select(ApplicationKeyRow.key_id)
                    .where(key_scope)
                    .with_for_update(read=True)
                    .execution_options(autoflush=False)
                )
            member = (
                exists()
                .where(
                    GroupMembershipRow.project_id == ProjectRow.id,
                    GroupMembershipRow.group_id == AccessGroupRow.id,
                    GroupMembershipRow.principal_id == PrincipalRow.id,
                )
                .correlate(PrincipalRow, ProjectRow, AccessGroupRow)
            )
            manager = (
                exists()
                .where(
                    GroupManagerRow.project_id == ProjectRow.id,
                    GroupManagerRow.group_id == AccessGroupRow.id,
                    GroupManagerRow.principal_id == PrincipalRow.id,
                    GroupManagerRow.principal_kind == PrincipalRow.kind,
                )
                .correlate(PrincipalRow, ProjectRow, AccessGroupRow)
            )
            granted = (
                exists()
                .where(
                    GroupActionGrantRow.project_id == ProjectRow.id,
                    GroupActionGrantRow.group_id == AccessGroupRow.id,
                    GroupActionGrantRow.recipient_principal_id == PrincipalRow.id,
                    GroupActionGrantRow.recipient_kind == PrincipalRow.kind,
                    GroupActionGrantRow.action.in_(
                        tuple(action.value for action in AccessGroupAction)
                    ),
                )
                .correlate(PrincipalRow, ProjectRow, AccessGroupRow)
            )
            query = (
                ProjectActorQueries.header(access, project_id)
                .join(AccessGroupRow, AccessGroupRow.project_id == ProjectRow.id)
                .add_columns(AccessGroupRow, member, manager, granted)
            )
            if isinstance(selector, AccessGroupId):
                query = query.where(AccessGroupRow.id == selector.value)
            else:
                reserved = (
                    exists()
                    .where(
                        AccessGroupNameReservationRow.project_id == ProjectRow.id,
                        AccessGroupNameReservationRow.group_id == AccessGroupRow.id,
                        AccessGroupNameReservationRow.name == selector.value,
                        AccessGroupNameReservationRow.retired.is_(False),
                    )
                    .correlate(ProjectRow, AccessGroupRow)
                )
                query = query.where(AccessGroupRow.resource_name == selector.value, reserved)
            row = (await self._session.execute(query)).tuples().one_or_none()
            if row is None:
                return None
            (
                principal,
                project,
                installed,
                project_member,
                recovering,
                linked,
                version,
                group,
                is_member,
                is_manager,
                has_action,
            ) = row
            if installed is None:
                raise DependencyUnavailableError()
            action = PostgresProjectActorMapper.action(
                access=access,
                principal=principal,
                project=project,
                member=project_member,
                recovering=recovering,
                linked=linked,
                version=version,
                granted=is_manager,
            )
            if application_key is not None:
                assert profile is not None
                current_key = (
                    (
                        await self._session.execute(
                            ApplicationKeyStateQueries.current_key(
                                key_id=application_key.key_id,
                                principal_id=access.actor_principal_id,
                                organization_id=OrganizationId(organization),
                                project_id=project_id,
                            )
                        )
                    )
                    .tuples()
                    .one_or_none()
                )
                action = replace(
                    action,
                    application_key_facts=PostgresApplicationKeyFactsMapper.to_facts(
                        current_key, evidence=application_key, profile=profile
                    ),
                )
            metadata = AccessGroupMetadataDTO(
                organization_id=OrganizationId(organization),
                project_id=project_id,
                group_id=AccessGroupId(group.id),
                name=ResourceName(group.resource_name) if group.resource_name is not None else None,
                display_name=group.name,
                created_at=group.created_at,
                access_revision=project.access_revision,
            )
            return AccessGroupReadFactsDTO(
                installation_id=InstallationId(installed),
                group=metadata,
                action=action,
                is_member=is_member,
                is_manager=is_manager,
                has_group_action=has_action,
            )
        except (OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None
