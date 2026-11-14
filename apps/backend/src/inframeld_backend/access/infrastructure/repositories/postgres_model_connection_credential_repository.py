from typing import override
from uuid import uuid4

from sqlalchemy import Nullable, String, and_, exists, func, select, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.encrypted_provider_credential_dto import (
    EncryptedProviderCredentialDTO,
)
from inframeld_backend.access.application.dtos.model_connection_access_dto import (
    ModelConnectionAccessDTO,
)
from inframeld_backend.access.application.dtos.model_connection_credential_dto import (
    ModelConnectionCredentialDTO,
)
from inframeld_backend.access.application.dtos.model_connection_credential_facts_dto import (
    ModelConnectionCredentialFactsDTO,
)
from inframeld_backend.access.application.dtos.model_connection_credential_result_dto import (
    ModelConnectionCredentialResultDTO,
)
from inframeld_backend.access.application.protocols.model_connection_credential_repository import (
    ModelConnectionCredentialRepository,
)
from inframeld_backend.access.domain.enums.model_connection_action import ModelConnectionAction
from inframeld_backend.access.domain.enums.model_connection_authentication import (
    ModelConnectionAuthentication,
)
from inframeld_backend.access.domain.enums.model_connection_provider import ModelConnectionProvider
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.mappers.postgres_project_actor_mapper import (
    PostgresProjectActorMapper,
)
from inframeld_backend.access.infrastructure.readers.project_actor_queries import (
    ProjectActorQueries,
)
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.access.infrastructure.rows.model_connection_action_grant_row import (
    ModelConnectionActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.model_connection_credential_result_row import (
    ModelConnectionCredentialResultRow,
)
from inframeld_backend.access.infrastructure.rows.model_connection_credential_row import (
    ModelConnectionCredentialRow,
)
from inframeld_backend.access.infrastructure.rows.model_connection_row import ModelConnectionRow
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_membership_row import ProjectMembershipRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.errors.application_errors import (
    ConflictError,
    DependencyUnavailableError,
    StaleRevisionError,
)
from inframeld_backend.shared.application.value_objects.model_connection_id import ModelConnectionId
from inframeld_backend.shared.application.value_objects.operation_id import OperationId


class PostgresModelConnectionCredentialRepository(ModelConnectionCredentialRepository):
    """Coordinate credential management with current Access changes through the same Project turn."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def inspect(
        self,
        access: AccessContextDTO,
        project_id: ProjectId,
        connection_id: ModelConnectionId,
        *,
        for_write: bool,
    ) -> ModelConnectionCredentialFactsDTO | None:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Credential facts require the caller's transaction.")
        connection, slot, grant = (
            ModelConnectionRow,
            ModelConnectionCredentialRow,
            ModelConnectionActionGrantRow,
        )
        try:
            if not await self._lock_scope(access, project_id, connection_id, for_write=for_write):
                return None
            granted = (
                exists()
                .where(
                    grant.project_id == ProjectRow.id,
                    grant.model_connection_id == connection.id,
                    grant.recipient_principal_id == PrincipalRow.id,
                    grant.recipient_kind == PrincipalRow.kind,
                    grant.action == ModelConnectionAction.MANAGE.value,
                )
                .correlate(PrincipalRow, ProjectRow, connection)
            )
            result = await self._session.execute(
                ProjectActorQueries.header(access, project_id)
                .join(
                    connection,
                    and_(
                        connection.id == connection_id.value,
                        connection.project_id == ProjectRow.id,
                        connection.organization_id == ProjectRow.organization_id,
                        connection.retired_at.is_(None),
                    ),
                )
                .outerjoin(
                    slot,
                    and_(
                        slot.model_connection_id == connection.id,
                        slot.project_id == connection.project_id,
                        slot.organization_id == connection.organization_id,
                    ),
                )
                .add_columns(
                    granted,
                    connection,
                    Nullable(slot.credential_id),
                    Nullable(slot.revision),
                    Nullable(slot.changed_at),
                    Nullable(slot.key_id),
                )
            )
            row = result.tuples().one_or_none()
        except (OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None
        if row is None:
            return None
        (
            principal,
            project,
            installation,
            member,
            recovering,
            linked,
            version,
            has_grant,
            target,
            credential_id,
            revision,
            changed_at,
            key_id,
        ) = row
        if installation is None:
            raise DependencyUnavailableError("The installation identity is unavailable.")
        return ModelConnectionCredentialFactsDTO(
            OrganizationId(project.organization_id),
            project_id,
            PostgresProjectActorMapper.action(
                access=access,
                principal=principal,
                project=project,
                member=member,
                recovering=recovering,
                linked=linked,
                version=version,
                granted=has_grant,
            ),
            ModelConnectionAccessDTO(
                ModelConnectionProvider(target.provider),
                target.base_url,
                target.api_version,
                ModelConnectionAuthentication(target.authentication),
            ),
            ModelConnectionCredentialDTO(
                project_id,
                connection_id,
                credential_id,
                revision or 0,
                key_id is not None,
                changed_at,
            ),
            key_id,
        )

    async def _lock_scope(
        self,
        access: AccessContextDTO,
        project_id: ProjectId,
        connection_id: ModelConnectionId,
        *,
        for_write: bool,
    ) -> bool:
        if (
            await self._session.scalar(
                select(func.current_setting("transaction_isolation", type_=String()))
            )
            != "read committed"
        ):
            raise RuntimeError("Credential management requires READ COMMITTED isolation.")
        member, connection = ProjectMembershipRow, ModelConnectionRow
        # Reject guessed foreign targets before acquiring either ownership lock.
        organization = await self._session.scalar(
            select(connection.organization_id).where(
                connection.id == connection_id.value,
                connection.project_id == project_id.value,
                connection.retired_at.is_(None),
                exists()
                .where(
                    member.principal_id == access.actor_principal_id.value,
                    member.project_id == project_id.value,
                    member.organization_id == connection.organization_id,
                )
                .correlate(connection),
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
            return False
        project = await self._session.scalar(
            select(ProjectRow.id)
            .where(ProjectRow.id == project_id.value, ProjectRow.organization_id == organization)
            .with_for_update(read=not for_write)
        )
        return project is not None

    @override
    async def original(
        self, facts: ModelConnectionCredentialFactsDTO, operation: CompletedSynchronousOperationDTO
    ) -> ModelConnectionCredentialResultDTO:
        result = ModelConnectionCredentialResultRow
        try:
            row = await self._session.scalar(
                select(result).where(
                    result.operation_id == operation.operation_id.value,
                    result.organization_id == facts.organization_id.value,
                    result.project_id == facts.project_id.value,
                    result.model_connection_id == facts.credential.connection_id.value,
                    result.actor_principal_id == facts.action.principal.id.value,
                )
            )
        except (OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None
        if row is None:
            raise ConflictError("The original credential result is unavailable.")
        return ModelConnectionCredentialResultDTO(
            ModelConnectionCredentialDTO(
                facts.project_id,
                facts.credential.connection_id,
                row.credential_id,
                row.revision,
                row.present,
                row.credential_changed_at,
            ),
            row.changed,
            operation,
        )

    @override
    async def save(
        self,
        facts: ModelConnectionCredentialFactsDTO,
        credential: ModelConnectionCredentialDTO,
        envelope: EncryptedProviderCredentialDTO | None,
        operation_id: OperationId,
    ) -> None:
        old = facts.credential
        if (
            credential.credential_id is None
            or credential.changed_at is None
            or credential.revision != old.revision + 1
            or (credential.project_id, credential.connection_id)
            != (old.project_id, old.connection_id)
            or credential.present != (envelope is not None)
            or (old.credential_id is not None and old.credential_id != credential.credential_id)
            or (old.credential_id is None and envelope is None)
        ):
            raise ConflictError("The checked credential change is inconsistent.")
        slot = ModelConnectionCredentialRow
        format_version = envelope.format_version if envelope is not None else None
        algorithm = envelope.algorithm if envelope is not None else None
        key_id = envelope.key_id if envelope is not None else None
        ciphertext = envelope.message if envelope is not None else None
        if old.credential_id is None:
            self._session.add(
                slot(
                    credential_id=credential.credential_id,
                    organization_id=facts.organization_id.value,
                    project_id=facts.project_id.value,
                    model_connection_id=old.connection_id.value,
                    revision=credential.revision,
                    changed_at=credential.changed_at,
                    format_version=format_version,
                    algorithm=algorithm,
                    key_id=key_id,
                    ciphertext=ciphertext,
                )
            )
        else:
            updated = await self._session.scalar(
                update(slot)
                .where(
                    slot.credential_id == old.credential_id,
                    slot.model_connection_id == old.connection_id.value,
                    slot.organization_id == facts.organization_id.value,
                    slot.project_id == facts.project_id.value,
                    slot.revision == old.revision,
                    slot.key_id.is_not_distinct_from(facts.key_id),
                )
                .values(
                    revision=credential.revision,
                    changed_at=credential.changed_at,
                    format_version=format_version,
                    algorithm=algorithm,
                    key_id=key_id,
                    ciphertext=ciphertext,
                )
                .returning(slot.credential_id)
            )
            if updated != credential.credential_id:
                raise StaleRevisionError()
        self._session.add(
            AccessAuditEventRow(
                id=uuid4(),
                organization_id=facts.organization_id.value,
                project_id=facts.project_id.value,
                actor_kind="human",
                actor_principal_id=facts.action.principal.id.value,
                event_type="model_connection_credential_changed",
                target_kind="model_connection",
                target_id=credential.connection_id.value,
                action=ModelConnectionAction.MANAGE.value,
                before_values={"revision": old.revision, "present": old.present},
                after_values={"revision": credential.revision, "present": credential.present},
                correlation_id=operation_id.value,
            )
        )
        await self._session.flush()

    @override
    async def save_result(
        self, facts: ModelConnectionCredentialFactsDTO, result: ModelConnectionCredentialResultDTO
    ) -> None:
        credential, operation = result.credential, result.operation
        if (
            not operation.created
            or operation.replay_kind is not OperationReplayKind.SAFE_RESULT
            or (credential.project_id, credential.connection_id)
            != (facts.project_id, facts.credential.connection_id)
        ):
            raise ConflictError("Credential completion has no safe original operation.")
        self._session.add(
            ModelConnectionCredentialResultRow(
                operation_id=operation.operation_id.value,
                organization_id=facts.organization_id.value,
                project_id=facts.project_id.value,
                model_connection_id=credential.connection_id.value,
                actor_principal_id=facts.action.principal.id.value,
                credential_id=credential.credential_id,
                revision=credential.revision,
                present=credential.present,
                changed=result.changed,
                credential_changed_at=credential.changed_at,
            )
        )
        await self._session.flush()
