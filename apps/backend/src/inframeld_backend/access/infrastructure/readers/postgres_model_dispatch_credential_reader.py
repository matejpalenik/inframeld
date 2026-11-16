import asyncio
from typing import override

from sqlalchemy import ColumnElement, String, and_, exists, func, select
from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.admitted_work_authority_dto import (
    AdmittedWorkAuthorityDTO,
)
from inframeld_backend.access.application.dtos.encrypted_provider_credential_dto import (
    EncryptedProviderCredentialDTO,
)
from inframeld_backend.access.application.dtos.model_connection_access_dto import (
    ModelConnectionAccessDTO,
)
from inframeld_backend.access.application.dtos.provider_credential_binding_dto import (
    ProviderCredentialBindingDTO,
)
from inframeld_backend.access.application.protocols.model_dispatch_credential_reader import (
    ModelDispatchCredentialReader,
)
from inframeld_backend.access.domain.enums.model_connection_action import ModelConnectionAction
from inframeld_backend.access.domain.enums.model_connection_authentication import (
    ModelConnectionAuthentication,
)
from inframeld_backend.access.domain.enums.model_connection_provider import ModelConnectionProvider
from inframeld_backend.access.infrastructure.rows.model_connection_action_grant_row import (
    ModelConnectionActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.model_connection_credential_row import (
    ModelConnectionCredentialRow,
)
from inframeld_backend.access.infrastructure.rows.model_connection_row import ModelConnectionRow
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.application.value_objects.model_connection_id import ModelConnectionId

_UNAVAILABLE = "The stored provider credential is unavailable."


class PostgresModelDispatchCredentialReader(ModelDispatchCredentialReader):
    """Read current facts after the caller has acquired its Project and job locks."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def read_access(
        self, authority: AdmittedWorkAuthorityDTO, connection_id: ModelConnectionId
    ) -> tuple[ModelConnectionAccessDTO, int] | None:
        try:
            async with asyncio.timeout(5):
                await self._require_read_committed()
                row = await self._session.scalar(
                    select(ModelConnectionRow)
                    .where(self._exact_use(authority, connection_id))
                    .execution_options(populate_existing=True, autoflush=False)
                )
        except (InterfaceError, OperationalError, SqlAlchemyTimeoutError, TimeoutError):
            raise DependencyUnavailableError(_UNAVAILABLE) from None
        if row is None:
            return None
        try:
            access = ModelConnectionAccessDTO(
                ModelConnectionProvider(row.provider),
                row.base_url,
                row.api_version,
                ModelConnectionAuthentication(row.authentication),
            )
        except ValueError:
            raise DependencyUnavailableError(_UNAVAILABLE) from None
        return access, row.access_revision

    @override
    async def read_sealed(
        self,
        authority: AdmittedWorkAuthorityDTO,
        connection_id: ModelConnectionId,
        access_revision: int,
    ) -> tuple[ProviderCredentialBindingDTO, EncryptedProviderCredentialDTO] | None:
        slot = ModelConnectionCredentialRow
        connection = ModelConnectionRow
        try:
            async with asyncio.timeout(5):
                await self._require_read_committed()
                row = await self._session.scalar(
                    select(slot)
                    .join(
                        connection,
                        and_(
                            slot.model_connection_id == connection.id,
                            slot.project_id == connection.project_id,
                            slot.organization_id == connection.organization_id,
                        ),
                    )
                    .where(
                        self._exact_use(authority, connection_id),
                        connection.access_revision == access_revision,
                        connection.authentication == ModelConnectionAuthentication.API_KEY.value,
                    )
                    .execution_options(populate_existing=True, autoflush=False)
                )
        except (InterfaceError, OperationalError, SqlAlchemyTimeoutError, TimeoutError):
            raise DependencyUnavailableError(_UNAVAILABLE) from None
        if row is None:
            return None
        version, algorithm, key_id, ciphertext = (
            row.format_version,
            row.algorithm,
            row.key_id,
            row.ciphertext,
        )
        # The schema enforces the v1 envelope shape and retains all-null tombstones.
        if version is None and algorithm is None and key_id is None and ciphertext is None:
            return None
        if version is None or algorithm is None or key_id is None or ciphertext is None:
            raise DependencyUnavailableError(_UNAVAILABLE)
        return (
            ProviderCredentialBindingDTO(
                authority.organization_id,
                authority.project_id,
                connection_id,
                row.credential_id,
                row.revision,
            ),
            EncryptedProviderCredentialDTO(version, algorithm, key_id, ciphertext),
        )

    async def _require_read_committed(self) -> None:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("A model dispatch credential requires its caller transaction.")
        isolation = await self._session.scalar(
            select(func.current_setting("transaction_isolation", type_=String()))
        )
        if isolation != "read committed":
            raise RuntimeError("A model dispatch credential requires READ COMMITTED isolation.")

    @staticmethod
    def _exact_use(
        authority: AdmittedWorkAuthorityDTO, connection_id: ModelConnectionId
    ) -> ColumnElement[bool]:
        connection = ModelConnectionRow
        grant = ModelConnectionActionGrantRow
        return and_(
            connection.id == connection_id.value,
            connection.organization_id == authority.organization_id.value,
            connection.project_id == authority.project_id.value,
            connection.retired_at.is_(None),
            exists()
            .where(
                grant.project_id == connection.project_id,
                grant.model_connection_id == connection.id,
                grant.recipient_principal_id == authority.principal_id.value,
                grant.recipient_kind == authority.principal_kind,
                grant.action == ModelConnectionAction.USE.value,
            )
            .correlate(connection),
        )
