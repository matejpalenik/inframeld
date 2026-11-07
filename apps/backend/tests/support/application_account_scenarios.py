"""Compose real account adapters without a production identity-provider request."""

from functools import partial
from typing import override
from uuid import UUID

from fastapi import FastAPI
from pydantic import HttpUrl
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.commands.create_application_account_command import (
    CreateApplicationAccountCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.application_account_creation_result_dto import (
    ApplicationAccountCreationResultDTO,
)
from inframeld_backend.access.application.protocols.human_access_token_authenticator import (
    HumanAccessTokenAuthenticator,
)
from inframeld_backend.access.application.protocols.human_session_authenticator import (
    HumanSessionAuthenticator,
)
from inframeld_backend.access.application.services.application_account_creation_fingerprint_service import (
    ApplicationAccountCreationFingerprintService,
)
from inframeld_backend.access.application.services.application_account_creation_service import (
    ApplicationAccountCreationService,
)
from inframeld_backend.access.application.value_objects.browser_session_credential import (
    BrowserSessionCredential,
)
from inframeld_backend.access.application.value_objects.human_access_token_credential import (
    HumanAccessTokenCredential,
)
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.http.dependencies.csrf_protection_dependency import (
    CSRFProtectionDependency,
)
from inframeld_backend.access.http.dependencies.product_access_dependency import (
    ProductAccessDependency,
)
from inframeld_backend.access.http.handlers.human_oauth_credential_error_handler import (
    register_human_oauth_credential_error_handler,
)
from inframeld_backend.access.http.routes.application_account_routes import (
    create_application_account_router,
)
from inframeld_backend.access.infrastructure.readers.postgres_application_account_creation_facts_reader import (
    PostgresApplicationAccountCreationFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_application_account_creation_result_reader import (
    PostgresApplicationAccountCreationResultReader,
)
from inframeld_backend.access.infrastructure.writers.postgres_application_account_creation_writer import (
    PostgresApplicationAccountCreationWriter,
)
from inframeld_backend.bootstrap.application_account_composition import (
    open_application_account_creation,
    open_application_account_read,
)
from inframeld_backend.bootstrap.original_operation_lookup_composition import (
    open_original_operation_lookup,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.errors.application_errors import (
    AuthenticationRequiredError,
)
from inframeld_backend.shared.application.services.idempotency_service import IdempotencyService
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.request_fingerprint_key import (
    RequestFingerprintKey,
)
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName
from inframeld_backend.shared.domain.value_objects.submitted_display_name import (
    SubmittedDisplayName,
)
from inframeld_backend.shared.http.handlers.error_handlers import register_error_handlers
from inframeld_backend.shared.http.middleware.request_context_middleware import (
    RequestContextMiddleware,
)
from inframeld_backend.shared.http.openapi.problem_openapi import configure_problem_openapi
from inframeld_backend.shared.http.routes.original_operation_lookup_routes import (
    create_original_operation_lookup_router,
)
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.resources.sqlalchemy_transaction_manager import (
    SqlAlchemyTransactionManager,
)
from inframeld_backend.shared.infrastructure.writers.postgres_operation_reservation_writer import (
    PostgresOperationReservationWriter,
)
from tests.support.authentication_evidence import MockAuthenticationEvidence
from tests.support.mock_application_authenticator import MockApplicationAuthenticator


def creation_service(session: AsyncSession) -> ApplicationAccountCreationService:
    return ApplicationAccountCreationService(
        transaction_manager=SqlAlchemyTransactionManager(session),
        creation_facts_reader=PostgresApplicationAccountCreationFactsReader(session),
        creation_writer=PostgresApplicationAccountCreationWriter(session),
        creation_result_reader=PostgresApplicationAccountCreationResultReader(session),
        operation_idempotency=IdempotencyService(PostgresOperationReservationWriter(session)),
        creation_fingerprint_service=ApplicationAccountCreationFingerprintService(
            RequestFingerprintService(RequestFingerprintKey(b"K" * 32))
        ),
    )


def account_command(
    project_id: ProjectId, revision: int = 1, name: str = "support-bot"
) -> CreateApplicationAccountCommand:
    return CreateApplicationAccountCommand(
        project_id, revision, ResourceName(name), SubmittedDisplayName("SupportBot")
    )


def account_context(project_id: ProjectId, key: str = "create-bot") -> IdempotencyContextDTO:
    return IdempotencyContextDTO(
        HttpMethod.POST,
        f"/v1/projects/{project_id.value}/application-accounts",
        IdempotencyKey(key),
    )


async def create_account(
    database: Database,
    access: AccessContextDTO,
    project_id: ProjectId,
    revision: int = 1,
    name: str = "support-bot",
    key: str = "create-bot",
) -> ApplicationAccountCreationResultDTO:
    async with database.session() as session:
        return await creation_service(session).create(
            access=access,
            command=account_command(project_id, revision, name),
            context=account_context(project_id, key),
        )


def account_http_application(
    database: Database, access: AccessContextDTO, bearer_access: AccessContextDTO
) -> FastAPI:
    """Use real account and lookup operations with controlled incoming identity proof."""
    authenticator = MockApplicationAccountAuthenticator(access, bearer_access)
    authenticate = ProductAccessDependency(
        authenticator,
        CSRFProtectionDependency((HttpUrl("https://account.test"),)),
        access_token_authenticator=authenticator,
        application_authenticator=MockApplicationAuthenticator(
            AccessContextDTO(
                PrincipalId(UUID(int=900)), MockAuthenticationEvidence.application_key()
            ),
            failure=AuthenticationRequiredError(),
        ),
    )
    application = FastAPI()
    register_error_handlers(application)
    register_human_oauth_credential_error_handler(application)
    configure_problem_openapi(application)
    fingerprints = ApplicationAccountCreationFingerprintService(
        RequestFingerprintService(RequestFingerprintKey(b"K" * 32))
    )
    application.include_router(
        create_application_account_router(
            authenticate,
            partial(open_application_account_creation, database, fingerprints),
            partial(open_application_account_read, database),
        )
    )
    application.include_router(
        create_original_operation_lookup_router(
            authenticate, partial(open_original_operation_lookup, database)
        )
    )
    application.add_middleware(RequestContextMiddleware)
    return application


class MockApplicationAccountAuthenticator(HumanSessionAuthenticator, HumanAccessTokenAuthenticator):
    def __init__(self, browser: AccessContextDTO, bearer: AccessContextDTO) -> None:
        self._browser = browser
        self._bearer = bearer

    @override
    async def authenticate(
        self, credential: BrowserSessionCredential | HumanAccessTokenCredential | None
    ) -> AccessContextDTO:
        return self._bearer if isinstance(credential, HumanAccessTokenCredential) else self._browser
