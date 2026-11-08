import asyncio
from typing import override

from sqlalchemy import ColumnElement, DateTime, String, exists, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.application_key_issuance_facts_dto import (
    ApplicationKeyIssuanceFactsDTO,
)
from inframeld_backend.access.application.dtos.application_key_issuance_record_dto import (
    ApplicationKeyIssuanceRecordDTO,
)
from inframeld_backend.access.application.dtos.application_key_metadata_dto import (
    ApplicationKeyMetadataDTO,
)
from inframeld_backend.access.application.protocols.application_key_issuance_facts_reader import (
    ApplicationKeyIssuanceFactsReader,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.application_account_action import (
    ApplicationAccountAction,
)
from inframeld_backend.access.domain.enums.application_key_adapter import ApplicationKeyAdapter
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.value_objects.application_key_id import ApplicationKeyId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.mappers.postgres_project_actor_mapper import (
    PostgresProjectActorMapper,
)
from inframeld_backend.access.infrastructure.readers.project_actor_queries import (
    ProjectActorQueries,
)
from inframeld_backend.access.infrastructure.rows.application_account_row import (
    ApplicationAccountRow,
)
from inframeld_backend.access.infrastructure.rows.application_action_grant_row import (
    ApplicationActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.application_key_issuance_result_row import (
    ApplicationKeyIssuanceResultRow,
)
from inframeld_backend.access.infrastructure.rows.application_key_row import ApplicationKeyRow
from inframeld_backend.access.infrastructure.rows.group_action_grant_row import GroupActionGrantRow
from inframeld_backend.access.infrastructure.rows.group_manager_row import GroupManagerRow
from inframeld_backend.access.infrastructure.rows.group_membership_row import GroupMembershipRow
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.project_membership_row import ProjectMembershipRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.enums.operation_reservation_state import (
    OperationReservationState,
)
from inframeld_backend.shared.application.errors.application_errors import (
    ConflictError,
    DependencyUnavailableError,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)


class PostgresApplicationKeyIssuanceFactsReader(ApplicationKeyIssuanceFactsReader):
    """Keep issuance observations and safe original reads on the caller's session."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def lock_for_issue(
        self,
        *,
        access: AccessContextDTO,
        project_id: ProjectId,
        application_principal_id: PrincipalId,
    ) -> ApplicationKeyIssuanceFactsDTO | None:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Key issuance requires the active caller transaction.")
        try:
            async with asyncio.timeout(5):
                with self._session.no_autoflush:
                    isolation = await self._session.scalar(
                        select(func.current_setting("transaction_isolation", type_=String()))
                    )
                    if isolation != "read committed":
                        raise RuntimeError("Key issuance requires READ COMMITTED isolation.")
                    organization = await self._session.scalar(
                        select(PrincipalRow.organization_id).where(
                            PrincipalRow.id == access.actor_principal_id.value
                        )
                    )
                    if organization is None:
                        return None
                    if (
                        await self._session.scalar(
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
                            .with_for_update()
                        )
                        is None
                    ):
                        return None
                    account = await self._session.scalar(
                        select(ApplicationAccountRow.principal_id).where(
                            ApplicationAccountRow.principal_id == application_principal_id.value,
                            ApplicationAccountRow.project_id == project_id.value,
                            ApplicationAccountRow.organization_id == organization,
                            ApplicationAccountRow.principal_kind == PrincipalKind.APPLICATION,
                        )
                    )
                    if account is None:
                        return None

                    # Retain parent-key locks through the caller's commit. Ordinary
                    # revocation UPDATEs conflict with FOR SHARE, including non-key columns.
                    await self._session.scalars(
                        select(ApplicationKeyRow.key_id)
                        .where(
                            ApplicationKeyRow.application_principal_id == account,
                            ApplicationKeyRow.project_id == project_id.value,
                            ApplicationKeyRow.organization_id == organization,
                        )
                        .order_by(ApplicationKeyRow.key_id)
                        .with_for_update(read=True)
                    )
                    now = await self._session.scalar(
                        select(func.clock_timestamp(type_=DateTime(timezone=True)))
                    )
                    if now is None:
                        raise DependencyUnavailableError()

                    application = aliased(PrincipalRow)
                    issue = (
                        exists()
                        .where(
                            ApplicationActionGrantRow.project_id == ProjectRow.id,
                            ApplicationActionGrantRow.application_principal_id == account,
                            ApplicationActionGrantRow.recipient_principal_id == PrincipalRow.id,
                            ApplicationActionGrantRow.recipient_kind == PrincipalRow.kind,
                            ApplicationActionGrantRow.action
                            == ApplicationAccountAction.ISSUE_KEYS.value,
                        )
                        .correlate(PrincipalRow, ProjectRow)
                    )
                    member = exists().where(
                        ProjectMembershipRow.project_id == project_id.value,
                        ProjectMembershipRow.organization_id == organization,
                        ProjectMembershipRow.principal_id == account,
                        ProjectMembershipRow.principal_kind == PrincipalKind.APPLICATION,
                        ProjectMembershipRow.application_principal_id == account,
                    )
                    row = (
                        (
                            await self._session.execute(
                                ProjectActorQueries.header(access, project_id)
                                .join(
                                    application,
                                    application.organization_id == ProjectRow.organization_id,
                                )
                                .where(
                                    application.id == account,
                                    application.kind == PrincipalKind.APPLICATION,
                                )
                                .add_columns(
                                    application,
                                    issue,
                                    member,
                                    self._action_coverage(
                                        access.actor_principal_id,
                                        application_principal_id,
                                        project_id,
                                    ),
                                    self._group_coverage(
                                        access.actor_principal_id,
                                        application_principal_id,
                                        project_id,
                                    ),
                                )
                            )
                        )
                        .tuples()
                        .one_or_none()
                    )
                    if row is None:
                        return None
                    (
                        principal,
                        project,
                        installed,
                        actor_member,
                        recovering,
                        linked,
                        version,
                        application_row,
                        can_issue,
                        application_member,
                        delegated,
                        managed,
                    ) = row
                    if installed is None:
                        raise DependencyUnavailableError()
                    count = await self._session.scalar(
                        select(func.count())
                        .select_from(ApplicationKeyRow)
                        .where(
                            ApplicationKeyRow.application_principal_id == account,
                            ApplicationKeyRow.project_id == project_id.value,
                            ApplicationKeyRow.organization_id == organization,
                            ApplicationKeyRow.revoked_at.is_(None),
                            ApplicationKeyRow.expires_at > now,
                        )
                    )
                    if count is None:
                        raise DependencyUnavailableError()
                    return ApplicationKeyIssuanceFactsDTO(
                        organization_id=OrganizationId(organization),
                        project_id=project_id,
                        installation_id=InstallationId(installed),
                        actor=PostgresProjectActorMapper.action(
                            access=access,
                            principal=principal,
                            project=project,
                            member=actor_member,
                            recovering=recovering,
                            linked=linked,
                            version=version,
                            granted=can_issue,
                        ),
                        application_principal=Principal(
                            id=PrincipalId(application_row.id),
                            organization_id=OrganizationId(application_row.organization_id),
                            kind=application_row.kind,
                            status=application_row.status,
                        ),
                        is_application_project_member=application_member,
                        has_all_action_delegation=delegated,
                        manages_all_groups=managed,
                        access_revision=project.access_revision,
                        checked_at=now,
                        usable_key_count=count,
                    )
        except (TimeoutError, OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None

    @staticmethod
    def _action_coverage(
        issuer: PrincipalId, application: PrincipalId, project: ProjectId
    ) -> ColumnElement[bool]:
        held_project = aliased(ProjectActionGrantRow)
        issuer_project = aliased(ProjectActionGrantRow)
        delegated_project = exists().where(
            issuer_project.project_id == held_project.project_id,
            issuer_project.recipient_principal_id == issuer.value,
            issuer_project.recipient_kind == PrincipalKind.HUMAN,
            issuer_project.action == held_project.action,
            issuer_project.can_grant.is_(True),
        )
        uncovered_project = exists().where(
            held_project.project_id == project.value,
            held_project.recipient_principal_id == application.value,
            held_project.recipient_kind == PrincipalKind.APPLICATION,
            ~delegated_project.correlate(held_project),
        )
        held_group = aliased(GroupActionGrantRow)
        issuer_group = aliased(GroupActionGrantRow)
        delegated_group = exists().where(
            issuer_group.project_id == held_group.project_id,
            issuer_group.group_id == held_group.group_id,
            issuer_group.recipient_principal_id == issuer.value,
            issuer_group.recipient_kind == PrincipalKind.HUMAN,
            issuer_group.action == held_group.action,
            issuer_group.can_grant.is_(True),
        )
        uncovered_group = exists().where(
            held_group.project_id == project.value,
            held_group.recipient_principal_id == application.value,
            held_group.recipient_kind == PrincipalKind.APPLICATION,
            ~delegated_group.correlate(held_group),
        )
        return ~uncovered_project & ~uncovered_group

    @staticmethod
    def _group_coverage(
        issuer: PrincipalId, application: PrincipalId, project: ProjectId
    ) -> ColumnElement[bool]:
        managed = exists().where(
            GroupManagerRow.project_id == GroupMembershipRow.project_id,
            GroupManagerRow.group_id == GroupMembershipRow.group_id,
            GroupManagerRow.principal_id == issuer.value,
            GroupManagerRow.principal_kind == PrincipalKind.HUMAN,
        )
        return ~exists().where(
            GroupMembershipRow.project_id == project.value,
            GroupMembershipRow.principal_id == application.value,
            ~managed.correlate(GroupMembershipRow),
        )

    @override
    async def read_original(
        self,
        *,
        organization_id: OrganizationId,
        project_id: ProjectId,
        application_principal_id: PrincipalId,
        issuer_principal_id: PrincipalId,
        operation_id: OperationId,
    ) -> ApplicationKeyIssuanceRecordDTO | None:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Key replay requires the active caller transaction.")
        try:
            async with asyncio.timeout(5):
                isolation = await self._session.scalar(
                    select(func.current_setting("transaction_isolation", type_=String()))
                )
                if isolation != "read committed":
                    raise RuntimeError("Key replay requires READ COMMITTED isolation.")
                original, parent = ApplicationKeyIssuanceResultRow, IdempotencyReservationRow
                route = f"/v1/projects/{project_id.value}/application-accounts/{application_principal_id.value}/keys"
                row = await self._session.scalar(
                    select(original)
                    .join(parent, parent.operation_id == original.operation_id)
                    .where(
                        original.operation_id == operation_id.value,
                        original.organization_id == organization_id.value,
                        original.project_id == project_id.value,
                        original.application_principal_id == application_principal_id.value,
                        original.issuer_principal_id == issuer_principal_id.value,
                        parent.organization_id == original.organization_id,
                        parent.project_id == original.project_id,
                        parent.principal_id == original.issuer_principal_id,
                        parent.method == "POST",
                        parent.requested_route == route,
                        parent.lookup_authority_family.is_(None),
                        parent.lookup_action_id.is_(None),
                        parent.state == OperationReservationState.REPLAYABLE,
                        parent.replay_kind == OperationReplayKind.ISSUED_SECRET,
                        parent.expires_at > func.clock_timestamp(),
                    )
                    .execution_options(populate_existing=True, autoflush=False)
                )
        except (TimeoutError, OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None
        if row is None:
            return None
        try:
            RevisionValidation.require(row.before_revision)
            RevisionValidation.require(row.access_revision)
            adapters = tuple(ApplicationKeyAdapter(adapter) for adapter in row.allowed_adapters)
            if (
                row.access_revision != row.before_revision + 1
                or row.revoked_at is not None
                or row.expires_at <= row.created_at
                or not 1 <= len(adapters) <= 2
                or len(set(adapters)) != len(adapters)
            ):
                raise ValueError("Incoherent original metadata.")
            return ApplicationKeyIssuanceRecordDTO(
                operation_id=operation_id,
                organization_id=organization_id,
                installation_id=InstallationId(row.installation_id),
                issuer_principal_id=issuer_principal_id,
                access_revision=row.access_revision,
                metadata=ApplicationKeyMetadataDTO(
                    key_id=ApplicationKeyId(row.key_id),
                    application_principal_id=application_principal_id,
                    project_id=project_id,
                    allowed_adapters=adapters,
                    created_at=row.created_at,
                    expires_at=row.expires_at,
                    revoked_at=None,
                ),
            )
        except (ValueError, TypeError):
            raise ConflictError("The original application-key result is incoherent.") from None
