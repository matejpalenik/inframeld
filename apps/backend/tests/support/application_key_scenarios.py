"""Provide controlled unit observations and real persisted-key integration setup."""

import base64
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import UUID, uuid4

from sqlalchemy import DateTime, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.commands.issue_application_key_command import (
    IssueApplicationKeyCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.application_key_current_facts_dto import (
    ApplicationKeyCurrentFactsDTO,
)
from inframeld_backend.access.application.dtos.application_key_issue_result_dto import (
    ApplicationKeyIssueResultDTO,
)
from inframeld_backend.access.application.dtos.application_key_verification_profile_dto import (
    ApplicationKeyVerificationProfileDTO,
)
from inframeld_backend.access.application.dtos.created_application_account_dto import (
    CreatedApplicationAccountDTO,
)
from inframeld_backend.access.application.services.application_authentication_service import (
    ApplicationAuthenticationService,
)
from inframeld_backend.access.application.services.application_key_issuance_fingerprint_service import (
    ApplicationKeyIssuanceFingerprintService,
)
from inframeld_backend.access.application.services.application_key_revocation_fingerprint_service import (
    ApplicationKeyRevocationFingerprintService,
)
from inframeld_backend.access.application.services.application_key_revocation_service import (
    ApplicationKeyRevocationService,
)
from inframeld_backend.access.application.value_objects.application_key_credential import (
    ApplicationKeyCredential,
)
from inframeld_backend.access.domain.enums.application_key_adapter import ApplicationKeyAdapter
from inframeld_backend.access.domain.value_objects.application_key_audience import (
    ApplicationKeyAudience,
)
from inframeld_backend.access.domain.value_objects.application_key_id import ApplicationKeyId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.readers.postgres_application_authentication_facts_reader import (
    PostgresApplicationAuthenticationFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_application_key_revocation_facts_reader import (
    PostgresApplicationKeyRevocationFactsReader,
)
from inframeld_backend.access.infrastructure.rows.application_key_row import ApplicationKeyRow
from inframeld_backend.access.infrastructure.settings.application_key_issuance_settings import (
    ApplicationKeyIssuanceSettings,
)
from inframeld_backend.access.infrastructure.verifiers.postgres_application_key_verifier import (
    PostgresApplicationKeyVerifier,
)
from inframeld_backend.access.infrastructure.writers.postgres_application_key_revocation_writer import (
    PostgresApplicationKeyRevocationWriter,
)
from inframeld_backend.bootstrap.application_key_composition import open_application_key_issuance
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.services.idempotency_service import IdempotencyService
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.request_fingerprint_key import (
    RequestFingerprintKey,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.infrastructure.readers.postgres_installation_identity_reader import (
    PostgresInstallationIdentityReader,
)
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.resources.sqlalchemy_transaction_manager import (
    SqlAlchemyTransactionManager,
)
from inframeld_backend.shared.infrastructure.writers.postgres_operation_reservation_writer import (
    PostgresOperationReservationWriter,
)
from tests.support.application_account_scenarios import create_account
from tests.support.project_creation_scenarios import create_project, seed_project_creator


def current_key_facts(
    *,
    key_id: ApplicationKeyId,
    principal_id: PrincipalId,
    organization_id: OrganizationId,
    project_id: ProjectId,
) -> ApplicationKeyCurrentFactsDTO:
    checked = datetime(2030, 1, 1, tzinfo=UTC)
    installation = InstallationId(UUID(int=19))
    profile = ApplicationKeyVerificationProfileDTO(
        ApplicationKeyAudience("https://api.test"), ApplicationKeyAdapter.HTTP
    )
    return ApplicationKeyCurrentFactsDTO(
        key_id=key_id,
        principal_id=principal_id,
        organization_id=organization_id,
        project_id=project_id,
        installation_id=installation,
        audience=profile.audience,
        allowed_adapters=(ApplicationKeyAdapter.HTTP,),
        expires_at=checked + timedelta(days=1),
        revoked_at=None,
        checked_at=checked,
        expected_installation_id=installation,
        expected_profile=profile,
        account_binding_matches=True,
    )


@dataclass(frozen=True, slots=True)
class ApplicationKeySeedDTO:
    account: CreatedApplicationAccountDTO
    credential: ApplicationKeyCredential = field(repr=False)
    creator_access: AccessContextDTO


async def seed_application_key(
    database: Database,
    *,
    audience: str = "https://api.test",
    adapters: tuple[ApplicationKeyAdapter, ...] = (ApplicationKeyAdapter.HTTP,),
) -> ApplicationKeySeedDTO:
    """Create the real account, then insert only controlled key verification material.

    This is integration setup, not public issuance or its delegation/limit guarantee.
    """
    creator = await seed_project_creator(database)
    project = (await create_project(database, creator)).project
    account = (await create_account(database, creator.access, project.project_id)).account
    credential = await store_application_key(
        database,
        principal_id=account.principal_id,
        organization_id=account.organization_id,
        project_id=account.project_id,
        issued_by=creator.access.actor_principal_id,
        audience=audience,
        adapters=adapters,
    )
    return ApplicationKeySeedDTO(account, credential, creator.access)


async def store_application_key(
    database: Database,
    *,
    principal_id: PrincipalId,
    organization_id: OrganizationId,
    project_id: ProjectId,
    issued_by: PrincipalId | None = None,
    audience: str = "https://api.test",
    adapters: tuple[ApplicationKeyAdapter, ...] = (ApplicationKeyAdapter.HTTP,),
) -> ApplicationKeyCredential:
    """Store controlled complete-key material for an existing account without public issuance."""
    installed = await PostgresInstallationIdentityReader(database).read()
    secret = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip("=")
    credential = ApplicationKeyCredential(f"ifm_app_{uuid4()}_{secret}")
    async with database.session() as session, session.begin():
        now = await session.scalar(select(func.clock_timestamp(type_=DateTime(timezone=True))))
        assert now is not None
        session.add(
            ApplicationKeyRow(
                key_id=credential.key_id.value,
                organization_id=organization_id.value,
                project_id=project_id.value,
                application_principal_id=principal_id.value,
                installation_id=installed.value,
                http_audience=audience if ApplicationKeyAdapter.HTTP in adapters else None,
                mcp_audience=audience if ApplicationKeyAdapter.MCP in adapters else None,
                allowed_adapters=[adapter.value for adapter in adapters],
                verifier=sha256(credential.value.encode("ascii")).digest(),
                expires_at=now + timedelta(days=90),
                issued_by_principal_id=issued_by.value if issued_by is not None else None,
            )
        )
    return credential


async def verified_application_access(
    database: Database,
    *,
    principal_id: PrincipalId,
    organization_id: OrganizationId,
    project_id: ProjectId,
    profile: ApplicationKeyVerificationProfileDTO,
) -> AccessContextDTO:
    """Verify a controlled full key for existing scoped rows and return only safe evidence."""
    credential = await store_application_key(
        database,
        principal_id=principal_id,
        organization_id=organization_id,
        project_id=project_id,
        audience=profile.audience.value,
        adapters=(profile.adapter,),
    )
    return await ApplicationAuthenticationService(
        key_verifier=PostgresApplicationKeyVerifier(database),
        authentication_facts_reader=PostgresApplicationAuthenticationFactsReader(database),
        verification_profile=profile,
    ).authenticate(credential)


async def issue_application_key(
    database: Database,
    *,
    adapters: tuple[ApplicationKeyAdapter, ...] = (ApplicationKeyAdapter.HTTP,),
) -> tuple[AccessContextDTO, ApplicationKeyIssueResultDTO]:
    """Create an account and issue its key through delivered services with controlled human proof."""
    creator = await seed_project_creator(database)
    project = (await create_project(database, creator)).project
    account = (await create_account(database, creator.access, project.project_id)).account
    fingerprints = RequestFingerprintService(RequestFingerprintKey(b"r" * 32))
    async with open_application_key_issuance(
        database,
        ApplicationKeyIssuanceFingerprintService(fingerprints),
        http_profile=ApplicationKeyVerificationProfileDTO(
            ApplicationKeyAudience("https://api.test"), ApplicationKeyAdapter.HTTP
        ),
        mcp_profile=ApplicationKeyVerificationProfileDTO(
            ApplicationKeyAudience("https://mcp.test/mcp"), ApplicationKeyAdapter.MCP
        ),
        settings=ApplicationKeyIssuanceSettings(),
    ) as issuer:
        issued = await issuer.issue(
            access=creator.access,
            command=IssueApplicationKeyCommand(
                account.project_id, account.principal_id, adapters, account.access_revision
            ),
            context=IdempotencyContextDTO(
                HttpMethod.POST,
                f"/v1/projects/{account.project_id.value}/application-accounts/{account.principal_id.value}/keys",
                IdempotencyKey("issue-revoke-target"),
            ),
        )
    return creator.access, issued


def revocation_service(session: AsyncSession) -> ApplicationKeyRevocationService:
    """Compose real revocation adapters on one caller session without provider I/O."""
    return ApplicationKeyRevocationService(
        transaction_manager=SqlAlchemyTransactionManager(session),
        revocation_facts_reader=PostgresApplicationKeyRevocationFactsReader(session),
        revocation_writer=PostgresApplicationKeyRevocationWriter(session),
        operation_idempotency=IdempotencyService(PostgresOperationReservationWriter(session)),
        revocation_fingerprint_service=ApplicationKeyRevocationFingerprintService(
            RequestFingerprintService(RequestFingerprintKey(b"r" * 32))
        ),
    )
