from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from inframeld_backend.access.application.protocols.identity_recovery_notification_handler import (
    IdentityRecoveryNotificationHandler,
)
from inframeld_backend.access.http.dependencies.recovery_hook_authentication_dependency import (
    RecoveryHookAuthenticationDependency,
)
from inframeld_backend.access.http.middleware.recovery_notification_response_middleware import (
    RecoveryNotificationResponseMiddleware,
)
from inframeld_backend.access.http.routes.identity_recovery_notification_routes import (
    create_recovery_notification_router,
)
from inframeld_backend.access.infrastructure.readers.file_recovery_hook_credentials_reader import (
    FileRecoveryHookCredentialsReader,
)
from inframeld_backend.bootstrap.recovery_application_settings import RecoveryApplicationSettings
from inframeld_backend.bootstrap.recovery_composition import open_recovery_notifications
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.http.handlers.error_handlers import register_error_handlers
from inframeld_backend.shared.http.middleware.request_context_middleware import (
    RequestContextMiddleware,
)
from inframeld_backend.shared.http.routes.health_routes import router as health_router
from inframeld_backend.shared.infrastructure.logging.logging_configuration import configure_logging
from inframeld_backend.shared.infrastructure.readers.postgres_installation_identity_reader import (
    PostgresInstallationIdentityReader,
)
from inframeld_backend.shared.infrastructure.resources.database import Database


def create_recovery_app(settings: RecoveryApplicationSettings | None = None) -> FastAPI:
    resolved = settings if settings is not None else RecoveryApplicationSettings.model_validate({})
    configure_logging(level=resolved.log_level, log_format=resolved.log_format)
    credentials = FileRecoveryHookCredentialsReader(resolved.recovery).read()
    database = Database(resolved.database)
    installation_id: InstallationId | None = None

    @asynccontextmanager
    async def lifespan(_application: FastAPI) -> AsyncGenerator[None]:
        nonlocal installation_id
        try:
            await database.startup()
            installation_id = await PostgresInstallationIdentityReader(database).read()
            yield
        finally:
            installation_id = None
            await database.shutdown()

    @asynccontextmanager
    async def open_handler() -> AsyncGenerator[IdentityRecoveryNotificationHandler]:
        if installation_id is None:
            raise DependencyUnavailableError()
        async with open_recovery_notifications(
            database,
            installation_id=installation_id,
            authority=resolved.recovery.authority,
            database_timeout_seconds=resolved.recovery.database_timeout_seconds,
        ) as handler:
            yield handler

    application = FastAPI(
        debug=False, docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan
    )
    register_error_handlers(application)
    application.include_router(health_router)
    application.include_router(
        create_recovery_notification_router(
            RecoveryHookAuthenticationDependency(
                current=credentials.current,
                retiring=credentials.retiring,
                retiring_accept_until=credentials.retiring_accept_until,
            ),
            open_handler,
            authority=resolved.recovery.authority,
            request_timeout_seconds=resolved.recovery.request_timeout_seconds,
            event_kind=resolved.recovery.event_kind,
        )
    )

    application.add_middleware(RecoveryNotificationResponseMiddleware)
    application.add_middleware(RequestContextMiddleware)
    return application
