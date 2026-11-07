import asyncio
from hashlib import sha256
from hmac import compare_digest
from typing import override

from sqlalchemy import DateTime, Nullable, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError

from inframeld_backend.access.application.dtos.application_key_verification_profile_dto import (
    ApplicationKeyVerificationProfileDTO,
)
from inframeld_backend.access.application.dtos.verified_application_key_dto import (
    VerifiedApplicationKeyDTO,
)
from inframeld_backend.access.application.protocols.application_key_verifier import (
    ApplicationKeyVerifier,
)
from inframeld_backend.access.application.value_objects.application_key_credential import (
    ApplicationKeyCredential,
)
from inframeld_backend.access.domain.policies.application_key_credential_policy import (
    ApplicationKeyCredentialPolicy,
)
from inframeld_backend.access.domain.value_objects.application_key_id import ApplicationKeyId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.infrastructure.rows.application_key_row import ApplicationKeyRow
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.rows.installation_identity_row import (
    InstallationIdentityRow,
)


class PostgresApplicationKeyVerifier(ApplicationKeyVerifier):
    """Verify the complete secret in one independent, bounded local read.

    The stored account association is protected by its scoped foreign key. Current
    local account eligibility remains a separate authentication-service decision.
    """

    def __init__(self, database: Database) -> None:
        self._database = database

    @override
    async def verify(
        self, credential: ApplicationKeyCredential, *, profile: ApplicationKeyVerificationProfileDTO
    ) -> VerifiedApplicationKeyDTO | None:
        statement = (
            select(
                InstallationIdentityRow.installation_id,
                Nullable(ApplicationKeyRow),
                func.clock_timestamp(type_=DateTime(timezone=True)),
            )
            .select_from(InstallationIdentityRow)
            .outerjoin(ApplicationKeyRow, ApplicationKeyRow.key_id == credential.key_id.value)
            .where(InstallationIdentityRow.singleton_key == 1)
            .execution_options(populate_existing=True)
        )
        try:
            async with asyncio.timeout(5.0), self._database.session() as session:
                observed = (await session.execute(statement)).tuples().one_or_none()
                if observed is None:
                    raise DependencyUnavailableError("The installation identity is unavailable.")
                installation, key, checked_at = observed
                if key is None:
                    return None

                matches = (
                    compare_digest(key.verifier, sha256(credential.value.encode("ascii")).digest())
                    and key.installation_id == installation
                    and key.audience == profile.audience.value
                    and profile.adapter.value in key.allowed_adapters
                )
                if not ApplicationKeyCredentialPolicy.is_current(
                    binding_matches=matches,
                    checked_at=checked_at,
                    expires_at=key.expires_at,
                    revoked_at=key.revoked_at,
                ):
                    return None
                return VerifiedApplicationKeyDTO(
                    ApplicationKeyId(key.key_id), PrincipalId(key.application_principal_id)
                )
        except (TimeoutError, OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None
