import asyncio
from typing import override

from sqlalchemy import DateTime, String, exists, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from inframeld_backend.access.application.commands.revoke_application_key_command import (
    RevokeApplicationKeyCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.application_key_metadata_dto import (
    ApplicationKeyMetadataDTO,
)
from inframeld_backend.access.application.dtos.application_key_revocation_facts_dto import (
    ApplicationKeyRevocationFactsDTO,
)
from inframeld_backend.access.application.dtos.application_key_revocation_record_dto import (
    ApplicationKeyRevocationRecordDTO,
)
from inframeld_backend.access.application.protocols.application_key_revocation_facts_reader import (
    ApplicationKeyRevocationFactsReader,
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
from inframeld_backend.access.infrastructure.rows.application_key_revocation_result_row import (
    ApplicationKeyRevocationResultRow,
)
from inframeld_backend.access.infrastructure.rows.application_key_row import ApplicationKeyRow
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
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


class PostgresApplicationKeyRevocationFactsReader(ApplicationKeyRevocationFactsReader):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def lock_for_revoke(
        self, *, access: AccessContextDTO, command: RevokeApplicationKeyCommand
    ) -> ApplicationKeyRevocationFactsDTO | None:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Key revocation requires the active caller transaction.")
        try:
            async with asyncio.timeout(5):
                with self._session.no_autoflush:
                    isolation = await self._session.scalar(
                        select(func.current_setting("transaction_isolation", type_=String()))
                    )
                    if isolation != "read committed":
                        raise RuntimeError("Key revocation requires READ COMMITTED isolation.")

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
                                ProjectRow.id == command.project_id.value,
                                ProjectRow.organization_id == organization,
                            )
                            .with_for_update()
                        )
                        is None
                    ):
                        return None

                    # Scope before taking the target lock. A mismatched account
                    # or key never resolves or locks another bound Project.
                    if (
                        await self._session.scalar(
                            select(ApplicationKeyRow.key_id)
                            .where(
                                ApplicationKeyRow.key_id == command.key_id.value,
                                ApplicationKeyRow.organization_id == organization,
                                ApplicationKeyRow.project_id == command.project_id.value,
                                ApplicationKeyRow.application_principal_id
                                == command.application_principal_id.value,
                            )
                            .with_for_update()
                        )
                        is None
                    ):
                        return None
                    now = await self._session.scalar(
                        select(func.clock_timestamp(type_=DateTime(timezone=True)))
                    )
                    if now is None:
                        raise DependencyUnavailableError()

                    application = aliased(PrincipalRow)
                    granted = (
                        exists()
                        .where(
                            ApplicationActionGrantRow.project_id == ProjectRow.id,
                            ApplicationActionGrantRow.application_principal_id
                            == command.application_principal_id.value,
                            ApplicationActionGrantRow.recipient_principal_id == PrincipalRow.id,
                            ApplicationActionGrantRow.recipient_kind == PrincipalRow.kind,
                            ApplicationActionGrantRow.action
                            == ApplicationAccountAction.REVOKE_KEYS.value,
                        )
                        .correlate(PrincipalRow, ProjectRow)
                    )
                    row = (
                        (
                            await self._session.execute(
                                ProjectActorQueries.header(access, command.project_id)
                                .join(
                                    application,
                                    application.organization_id == ProjectRow.organization_id,
                                )
                                .join(
                                    ApplicationAccountRow,
                                    ApplicationAccountRow.principal_id == application.id,
                                )
                                .join(
                                    ApplicationKeyRow,
                                    ApplicationKeyRow.application_principal_id == application.id,
                                )
                                .where(
                                    application.id == command.application_principal_id.value,
                                    application.kind == PrincipalKind.APPLICATION,
                                    ApplicationAccountRow.organization_id == organization,
                                    ApplicationAccountRow.project_id == command.project_id.value,
                                    ApplicationAccountRow.principal_kind
                                    == PrincipalKind.APPLICATION,
                                    ApplicationKeyRow.key_id == command.key_id.value,
                                    ApplicationKeyRow.organization_id == organization,
                                    ApplicationKeyRow.project_id == command.project_id.value,
                                )
                                .add_columns(
                                    application,
                                    granted,
                                    ApplicationKeyRow.installation_id,
                                    ApplicationKeyRow.key_id,
                                    ApplicationKeyRow.allowed_adapters,
                                    ApplicationKeyRow.created_at,
                                    ApplicationKeyRow.expires_at,
                                    ApplicationKeyRow.revoked_at,
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
                        member,
                        recovering,
                        linked,
                        version,
                        application_row,
                        can_revoke,
                        key_installation,
                        key_id,
                        adapters,
                        created_at,
                        expires_at,
                        revoked_at,
                    ) = row
                    if installed is None:
                        raise DependencyUnavailableError()
                    if key_installation != installed:
                        raise RuntimeError("Revocation facts changed the key installation binding.")

                    return ApplicationKeyRevocationFactsDTO(
                        organization_id=OrganizationId(organization),
                        project_id=command.project_id,
                        installation_id=InstallationId(installed),
                        actor=PostgresProjectActorMapper.action(
                            access=access,
                            principal=principal,
                            project=project,
                            member=member,
                            recovering=recovering,
                            linked=linked,
                            version=version,
                            granted=can_revoke,
                        ),
                        application_principal=Principal(
                            PrincipalId(application_row.id),
                            OrganizationId(application_row.organization_id),
                            application_row.kind,
                            application_row.status,
                        ),
                        metadata=ApplicationKeyMetadataDTO(
                            key_id=ApplicationKeyId(key_id),
                            application_principal_id=command.application_principal_id,
                            project_id=command.project_id,
                            allowed_adapters=tuple(
                                ApplicationKeyAdapter(value) for value in adapters
                            ),
                            created_at=created_at,
                            expires_at=expires_at,
                            revoked_at=revoked_at,
                        ),
                        access_revision=project.access_revision,
                        checked_at=now,
                    )
        except (TimeoutError, OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None

    @override
    async def read_original(
        self,
        *,
        organization_id: OrganizationId,
        project_id: ProjectId,
        actor_principal_id: PrincipalId,
        operation_id: OperationId,
    ) -> ApplicationKeyRevocationRecordDTO | None:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Key replay requires the active caller transaction.")
        try:
            async with asyncio.timeout(5):
                isolation = await self._session.scalar(
                    select(func.current_setting("transaction_isolation", type_=String()))
                )
                if isolation != "read committed":
                    raise RuntimeError("Key replay requires READ COMMITTED isolation.")
                original, parent = ApplicationKeyRevocationResultRow, IdempotencyReservationRow
                result = (
                    (
                        await self._session.execute(
                            select(original, parent.requested_route)
                            .join(parent, parent.operation_id == original.operation_id)
                            .where(
                                original.operation_id == operation_id.value,
                                original.organization_id == organization_id.value,
                                original.project_id == project_id.value,
                                original.actor_principal_id == actor_principal_id.value,
                                parent.organization_id == original.organization_id,
                                parent.project_id == original.project_id,
                                parent.principal_id == original.actor_principal_id,
                                parent.method == "POST",
                                parent.lookup_authority_family.is_(None),
                                parent.lookup_action_id.is_(None),
                                parent.state == OperationReservationState.REPLAYABLE,
                                parent.replay_kind == OperationReplayKind.SAFE_RESULT,
                                parent.expires_at > func.clock_timestamp(),
                            )
                            .execution_options(populate_existing=True, autoflush=False)
                        )
                    )
                    .tuples()
                    .one_or_none()
                )
        except (TimeoutError, OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None
        if result is None:
            return None
        row, saved_route = result
        route = (
            f"/v1/projects/{project_id.value}/application-accounts/"
            f"{row.application_principal_id}/keys/{row.key_id}/revoke"
        )
        try:
            RevisionValidation.require(row.before_revision)
            RevisionValidation.require(row.access_revision)
            adapters = tuple(ApplicationKeyAdapter(value) for value in row.allowed_adapters)
            if (
                saved_route != route
                or row.access_revision not in (row.before_revision, row.before_revision + 1)
                or row.expires_at <= row.created_at
                or row.revoked_at < row.created_at
                or not 1 <= len(adapters) <= 2
                or len(set(adapters)) != len(adapters)
            ):
                raise ValueError("Incoherent original metadata.")
            return ApplicationKeyRevocationRecordDTO(
                operation_id=operation_id,
                organization_id=organization_id,
                installation_id=InstallationId(row.installation_id),
                actor_principal_id=actor_principal_id,
                access_revision=row.access_revision,
                metadata=ApplicationKeyMetadataDTO(
                    key_id=ApplicationKeyId(row.key_id),
                    application_principal_id=PrincipalId(row.application_principal_id),
                    project_id=project_id,
                    allowed_adapters=adapters,
                    created_at=row.created_at,
                    expires_at=row.expires_at,
                    revoked_at=row.revoked_at,
                ),
            )
        except (ValueError, TypeError):
            raise ConflictError("The original application-key result is incoherent.") from None
