from datetime import datetime
from typing import cast, override
from uuid import UUID

from sqlalchemy import ColumnElement, Nullable, and_, exists, select, true
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from sqlalchemy.sql import Select

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.application_account_metadata_dto import (
    ApplicationAccountMetadataDTO,
)
from inframeld_backend.access.application.dtos.application_account_read_facts_dto import (
    ApplicationAccountReadFactsDTO,
)
from inframeld_backend.access.application.dtos.application_key_metadata_dto import (
    ApplicationKeyMetadataDTO,
)
from inframeld_backend.access.application.dtos.application_keys_facts_dto import (
    ApplicationKeysFactsDTO,
)
from inframeld_backend.access.application.protocols.application_account_facts_reader import (
    ApplicationAccountFactsReader,
)
from inframeld_backend.access.domain.enums.application_account_action import (
    ApplicationAccountAction,
)
from inframeld_backend.access.domain.enums.application_key_adapter import ApplicationKeyAdapter
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
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
from inframeld_backend.access.infrastructure.rows.application_account_name_reservation_row import (
    ApplicationAccountNameReservationRow,
)
from inframeld_backend.access.infrastructure.rows.application_account_row import (
    ApplicationAccountRow,
)
from inframeld_backend.access.infrastructure.rows.application_action_grant_row import (
    ApplicationActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.application_key_row import ApplicationKeyRow
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

_AccountProjection = tuple[
    PrincipalRow,
    ProjectRow,
    UUID | None,
    bool,
    bool,
    bool,
    int | None,
    PrincipalRow,
    str | None,
    bool,
    bool,
]


class PostgresApplicationAccountFactsReader(ApplicationAccountFactsReader):
    """Observe exact authority and safe metadata together, even for an empty key page."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def read_account(
        self,
        *,
        access: AccessContextDTO,
        project_id: ProjectId,
        selector: PrincipalId | ResourceName,
    ) -> ApplicationAccountReadFactsDTO | None:
        try:
            row = (
                (await self._session.execute(self._account_statement(access, project_id, selector)))
                .tuples()
                .one_or_none()
            )
        except (OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None
        return self._facts(access, row) if row is not None else None

    @override
    async def read_keys(
        self,
        *,
        access: AccessContextDTO,
        project_id: ProjectId,
        application_principal_id: PrincipalId,
        key_id: ApplicationKeyId | None,
        after: ApplicationKeyId | None,
        limit: int,
    ) -> ApplicationKeysFactsDTO | None:
        key = ApplicationKeyRow
        # Select safe columns explicitly. Neither the verifier nor audience is
        # fetched into this read, including its lateral continuation projection.
        page = select(
            key.key_id,
            key.application_principal_id,
            key.project_id,
            key.allowed_adapters,
            key.created_at,
            key.expires_at,
            key.revoked_at,
        ).where(
            key.application_principal_id == ApplicationAccountRow.principal_id,
            key.project_id == ApplicationAccountRow.project_id,
            key.organization_id == ApplicationAccountRow.organization_id,
            key.installation_id == InstallationIdentityRow.installation_id,
        )
        if key_id is not None:
            page = page.where(key.key_id == key_id.value)
        if after is not None:
            page = page.where(key.key_id > after.value)
        bounded = (
            page.order_by(key.key_id)
            .limit(limit + 1)
            .correlate(ApplicationAccountRow, InstallationIdentityRow)
            .lateral("application_keys_page")
        )
        # SQLAlchemy's dynamic lateral column collection loses concrete types.
        # Restore the types of these seven explicitly selected mapped columns.
        public_id = Nullable(cast(ColumnElement[UUID], bounded.c.key_id))
        principal = Nullable(cast(ColumnElement[UUID], bounded.c.application_principal_id))
        project = Nullable(cast(ColumnElement[UUID], bounded.c.project_id))
        adapters = Nullable(cast(ColumnElement[list[str]], bounded.c.allowed_adapters))
        created = Nullable(cast(ColumnElement[datetime], bounded.c.created_at))
        expires = Nullable(cast(ColumnElement[datetime], bounded.c.expires_at))
        revoked = Nullable(cast(ColumnElement[datetime], bounded.c.revoked_at))
        statement = (
            self._account_statement(access, project_id, application_principal_id)
            .outerjoin(bounded, true())
            .add_columns(public_id, principal, project, adapters, created, expires, revoked)
            .order_by(public_id)
        )
        try:
            rows = (await self._session.execute(statement)).tuples().all()
        except (OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None
        if not rows:
            return None
        # A fixed tuple slice preserves the authorization projection above.
        facts = self._facts(access, cast(_AccountProjection, rows[0][:11]))
        keys: list[ApplicationKeyMetadataDTO] = []
        for row in rows:
            (
                stored_id,
                stored_principal,
                stored_project,
                stored_adapters,
                stored_created,
                stored_expires,
                stored_revoked,
            ) = row[11:]
            if stored_id is None:
                continue
            if (
                stored_principal is None
                or stored_project is None
                or stored_adapters is None
                or stored_created is None
                or stored_expires is None
            ):
                raise RuntimeError("The safe key metadata projection is incomplete.")
            keys.append(
                ApplicationKeyMetadataDTO(
                    ApplicationKeyId(stored_id),
                    PrincipalId(stored_principal),
                    ProjectId(stored_project),
                    tuple(ApplicationKeyAdapter(value) for value in stored_adapters),
                    stored_created,
                    stored_expires,
                    stored_revoked,
                )
            )
        return ApplicationKeysFactsDTO(facts, tuple(keys))

    @staticmethod
    def _account_statement(
        access: AccessContextDTO, project_id: ProjectId, selector: PrincipalId | ResourceName
    ) -> Select[_AccountProjection]:
        application = aliased(PrincipalRow, name="application_principal")
        grant = ApplicationActionGrantRow
        visible = (
            exists()
            .where(
                grant.project_id == ProjectRow.id,
                grant.application_principal_id == ApplicationAccountRow.principal_id,
                grant.recipient_principal_id == PrincipalRow.id,
                grant.recipient_kind == PrincipalRow.kind,
                grant.action.in_(
                    (
                        ApplicationAccountAction.ISSUE_KEYS.value,
                        ApplicationAccountAction.REVOKE_KEYS.value,
                        ApplicationAccountAction.DELETE_ACCOUNT.value,
                    )
                ),
            )
            .correlate(PrincipalRow, ProjectRow, ApplicationAccountRow)
        )
        keys = (
            exists()
            .where(
                grant.project_id == ProjectRow.id,
                grant.application_principal_id == ApplicationAccountRow.principal_id,
                grant.recipient_principal_id == PrincipalRow.id,
                grant.recipient_kind == PrincipalRow.kind,
                grant.action.in_(
                    (
                        ApplicationAccountAction.ISSUE_KEYS.value,
                        ApplicationAccountAction.REVOKE_KEYS.value,
                    )
                ),
            )
            .correlate(PrincipalRow, ProjectRow, ApplicationAccountRow)
        )
        statement = (
            ProjectActorQueries.header(access, project_id)
            .join(
                ApplicationAccountRow,
                and_(
                    ApplicationAccountRow.project_id == ProjectRow.id,
                    ApplicationAccountRow.organization_id == PrincipalRow.organization_id,
                ),
            )
            .join(
                application,
                and_(
                    application.id == ApplicationAccountRow.principal_id,
                    application.organization_id == ApplicationAccountRow.organization_id,
                    application.kind == PrincipalKind.APPLICATION,
                ),
            )
            .add_columns(application, ApplicationAccountRow.resource_name, visible, keys)
        )
        if isinstance(selector, PrincipalId):
            return statement.where(ApplicationAccountRow.principal_id == selector.value)
        reservation = ApplicationAccountNameReservationRow
        return statement.join(
            reservation,
            and_(
                reservation.project_id == ApplicationAccountRow.project_id,
                reservation.organization_id == ApplicationAccountRow.organization_id,
                reservation.application_principal_id == ApplicationAccountRow.principal_id,
                reservation.name == selector.value,
                reservation.retired.is_(False),
            ),
        ).where(
            ApplicationAccountRow.resource_name == selector.value,
            application.status != PrincipalStatus.RETIRED,
        )

    @staticmethod
    def _facts(access: AccessContextDTO, row: _AccountProjection) -> ApplicationAccountReadFactsDTO:
        (
            principal,
            project,
            installed,
            member,
            recovering,
            linked,
            version,
            application,
            name,
            visible,
            keys,
        ) = row
        if installed is None:
            raise DependencyUnavailableError("The installation identity is unavailable.")
        action = PostgresProjectActorMapper.action(
            access=access,
            principal=principal,
            project=project,
            member=member,
            recovering=recovering,
            linked=linked,
            version=version,
            granted=visible,
        )
        account = ApplicationAccountMetadataDTO(
            OrganizationId(application.organization_id),
            ProjectId(project.id),
            PrincipalId(application.id),
            ResourceName(name) if name is not None else None,
            application.display_name,
            application.status,
            application.created_at,
            project.access_revision,
        )
        return ApplicationAccountReadFactsDTO(InstallationId(installed), action, account, keys)
