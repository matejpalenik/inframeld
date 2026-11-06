"""Construct the HTTP application and connect its concrete resources and services."""

from contextlib import ExitStack
from functools import partial

from fastapi import FastAPI
from ory_kratos_client.api.identity_api import IdentityApi

from inframeld_backend.access.application.services.application_account_creation_fingerprint_service import (
    ApplicationAccountCreationFingerprintService,
)
from inframeld_backend.access.application.services.human_admission_fingerprint_service import (
    HumanAdmissionFingerprintService,
)
from inframeld_backend.access.application.services.project_creation_fingerprint_service import (
    ProjectCreationFingerprintService,
)
from inframeld_backend.access.application.services.project_grant_change_fingerprint_service import (
    ProjectGrantChangeFingerprintService,
)
from inframeld_backend.access.application.services.project_membership_change_fingerprint_service import (
    ProjectMembershipChangeFingerprintService,
)
from inframeld_backend.access.application.services.project_metadata_fingerprint_service import (
    ProjectMetadataFingerprintService,
)
from inframeld_backend.access.http.dependencies.csrf_protection_dependency import (
    CSRFProtectionDependency,
)
from inframeld_backend.access.http.dependencies.human_session_dependency import (
    HumanSessionDependency,
)
from inframeld_backend.access.http.handlers.human_oauth_credential_error_handler import (
    register_human_oauth_credential_error_handler,
)
from inframeld_backend.access.http.requests.application_account_creation_request import (
    ApplicationAccountCreationRequest,
)
from inframeld_backend.access.http.requests.human_admission_request import HumanAdmissionRequest
from inframeld_backend.access.http.requests.project_action_grant_request import (
    ProjectActionGrantRequest,
)
from inframeld_backend.access.http.requests.project_creation_request import ProjectCreationRequest
from inframeld_backend.access.http.requests.project_membership_request import (
    ProjectMembershipRequest,
)
from inframeld_backend.access.http.requests.project_metadata_update_request import (
    ProjectMetadataUpdateRequest,
)
from inframeld_backend.access.http.responses.application_account_creation_response import (
    ApplicationAccountCreationResponse,
)
from inframeld_backend.access.http.responses.application_account_metadata_response import (
    ApplicationAccountMetadataResponse,
)
from inframeld_backend.access.http.responses.my_organization_access_response import (
    MyOrganizationAccessResponse,
)
from inframeld_backend.access.http.responses.my_project_access_response import (
    MyProjectAccessResponse,
)
from inframeld_backend.access.http.responses.project_action_grant_removal_response import (
    ProjectActionGrantRemovalResponse,
)
from inframeld_backend.access.http.responses.project_action_grant_response import (
    ProjectActionGrantResponse,
)
from inframeld_backend.access.http.routes.application_account_routes import (
    create_application_account_router,
)
from inframeld_backend.access.http.routes.current_session_routes import create_session_router
from inframeld_backend.access.http.routes.discovery_routes import create_discovery_router
from inframeld_backend.access.http.routes.human_admission_routes import (
    create_human_admission_router,
)
from inframeld_backend.access.http.routes.human_oauth_consent_routes import (
    create_human_oauth_consent_router,
)
from inframeld_backend.access.http.routes.my_project_access_routes import (
    create_my_project_access_router,
)
from inframeld_backend.access.http.routes.organization_access_routes import (
    create_organization_access_router,
)
from inframeld_backend.access.http.routes.project_action_grant_change_routes import (
    create_project_action_grant_change_router,
)
from inframeld_backend.access.http.routes.project_action_grant_routes import (
    create_project_action_grant_router,
)
from inframeld_backend.access.http.routes.project_creation_routes import (
    create_project_creation_router,
)
from inframeld_backend.access.http.routes.project_grant_routes import (
    create_project_grant_router,
)
from inframeld_backend.access.http.routes.project_members_routes import (
    create_project_members_router,
)
from inframeld_backend.access.http.routes.project_membership_routes import (
    create_project_membership_router,
)
from inframeld_backend.access.http.routes.project_metadata_routes import (
    create_project_metadata_router,
)
from inframeld_backend.access.infrastructure.resources.installation_discovery_resource import (
    InstallationDiscoveryResource,
)
from inframeld_backend.access.infrastructure.verifiers.kratos_human_identity_verifier import (
    KratosHumanIdentityVerifier,
)
from inframeld_backend.bootstrap.access_composition import create_access_components
from inframeld_backend.bootstrap.application_account_composition import (
    open_application_account_creation,
    open_application_account_read,
)
from inframeld_backend.bootstrap.application_lifespan import application_lifespan
from inframeld_backend.bootstrap.application_resources import ApplicationResources
from inframeld_backend.bootstrap.application_settings import ApplicationSettings, get_settings
from inframeld_backend.bootstrap.deletion_status_composition import open_deletion_status_lookup
from inframeld_backend.bootstrap.human_admission_composition import open_human_admission
from inframeld_backend.bootstrap.my_project_access_composition import open_my_project_access
from inframeld_backend.bootstrap.organization_access_composition import open_my_organization_access
from inframeld_backend.bootstrap.original_operation_lookup_composition import (
    open_original_operation_lookup,
)
from inframeld_backend.bootstrap.postgres_project_membership_change_service_factory import (
    PostgresProjectMembershipChangeServiceFactory,
)
from inframeld_backend.bootstrap.project_action_grants_composition import open_project_action_grants
from inframeld_backend.bootstrap.project_creation_composition import open_project_creation
from inframeld_backend.bootstrap.project_grant_composition import open_project_grant_change
from inframeld_backend.bootstrap.project_members_composition import open_project_members
from inframeld_backend.bootstrap.project_metadata_composition import (
    open_project_metadata,
    open_project_name_resolution,
)
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.http.handlers.error_handlers import register_error_handlers
from inframeld_backend.shared.http.middleware.request_context_middleware import (
    RequestContextMiddleware,
)
from inframeld_backend.shared.http.openapi.problem_openapi import configure_problem_openapi
from inframeld_backend.shared.http.routes.deletion_status_routes import (
    create_deletion_status_router,
)
from inframeld_backend.shared.http.routes.health_routes import router as health_router
from inframeld_backend.shared.http.routes.original_operation_lookup_routes import (
    create_original_operation_lookup_router,
)
from inframeld_backend.shared.infrastructure.logging.logging_configuration import configure_logging
from inframeld_backend.shared.infrastructure.readers.file_request_fingerprint_key_reader import (
    FileRequestFingerprintKeyReader,
)
from inframeld_backend.shared.infrastructure.resources.database import Database

API_TITLE = "Inframeld API"
API_VERSION = "0.1.0"


def create_app(settings: ApplicationSettings | None = None) -> FastAPI:
    """Construct resources, wire application services, and register HTTP behavior.

    Construction performs no network I/O. Release provider clients if assembly
    fails; otherwise transfer their ownership to the application lifespan.
    """
    resolved_settings = settings if settings is not None else get_settings()

    configure_logging(level=resolved_settings.log_level, log_format=resolved_settings.log_format)

    database = Database(resolved_settings.database)

    with ExitStack() as provider_cleanup:
        access = create_access_components(
            resolved_settings.kratos,
            resolved_settings.hydra,
            database,
            human_authentication_settings=resolved_settings.human_authentication,
        )
        for client in (
            access.kratos_client,
            access.kratos_admin_client,
            access.hydra_client,
        ):
            if client is not None:
                provider_cleanup.callback(client.rest_client.pool_manager.clear)

        request_fingerprints = RequestFingerprintService(
            FileRequestFingerprintKeyReader(resolved_settings.request_fingerprint.key_file).read()
        )
        fingerprints = ProjectGrantChangeFingerprintService(request_fingerprints)
        metadata_fingerprints = ProjectMetadataFingerprintService(request_fingerprints)
        creation_fingerprints = ProjectCreationFingerprintService(request_fingerprints)
        account_fingerprints = ApplicationAccountCreationFingerprintService(request_fingerprints)
        admission_fingerprints = HumanAdmissionFingerprintService(request_fingerprints)
        membership_fingerprints = ProjectMembershipChangeFingerprintService(request_fingerprints)
        admission_authority = (
            resolved_settings.kratos.authority if resolved_settings.kratos is not None else None
        )
        admission_verifier = (
            KratosHumanIdentityVerifier(
                IdentityApi(access.kratos_admin_client), admission_authority
            )
            if access.kratos_admin_client is not None and admission_authority is not None
            else None
        )

        discovery = (
            InstallationDiscoveryResource(resolved_settings.discovery, resolved_settings.hydra)
            if resolved_settings.discovery is not None and resolved_settings.hydra is not None
            else None
        )
        resources = ApplicationResources(
            discovery=discovery,
            database=database,
            kratos_client=access.kratos_client,
            kratos_admin_client=access.kratos_admin_client,
            hydra_client=access.hydra_client,
        )

        application = FastAPI(
            debug=False,
            title=API_TITLE,
            version=API_VERSION,
            description="Governed retrieval and release workflows.",
            openapi_url="/v1/openapi.json",
            docs_url="/docs",
            redoc_url="/redoc",
            lifespan=partial(application_lifespan, resources),
        )

        register_error_handlers(application)
        register_human_oauth_credential_error_handler(application)
        configure_problem_openapi(
            application,
            validation_models=(
                ApplicationAccountCreationRequest,
                HumanAdmissionRequest,
                ProjectCreationRequest,
                ProjectMembershipRequest,
                ProjectMetadataUpdateRequest,
                ProjectActionGrantRequest,
            ),
            serialization_models=(
                ApplicationAccountCreationResponse,
                ApplicationAccountMetadataResponse,
                MyOrganizationAccessResponse,
                MyProjectAccessResponse,
                ProjectActionGrantResponse,
                ProjectActionGrantRemovalResponse,
            ),
        )
        application.include_router(health_router)
        application.include_router(
            create_discovery_router(discovery.read if discovery else lambda: None)
        )

        human_session = HumanSessionDependency(
            access.authenticator,
            CSRFProtectionDependency(resolved_settings.csrf.trusted_origins),
            access_token_authenticator=access.access_token_authenticator,
        )

        application.include_router(create_session_router(human_session))
        application.include_router(
            create_human_admission_router(
                human_session,
                partial(
                    open_human_admission,
                    database,
                    admission_fingerprints,
                    admission_verifier,
                    admission_authority,
                    min(
                        resolved_settings.human_authentication.provider_timeout_seconds,
                        resolved_settings.human_authentication.total_timeout_seconds,
                    ),
                ),
            )
        )
        application.include_router(
            create_organization_access_router(
                human_session, partial(open_my_organization_access, database)
            )
        )
        application.include_router(
            create_project_creation_router(
                human_session, partial(open_project_creation, database, creation_fingerprints)
            )
        )
        application.include_router(
            create_application_account_router(
                human_session,
                partial(open_application_account_creation, database, account_fingerprints),
                partial(open_application_account_read, database),
            )
        )
        application.include_router(
            create_project_members_router(human_session, partial(open_project_members, database))
        )
        application.include_router(
            create_project_membership_router(
                human_session,
                PostgresProjectMembershipChangeServiceFactory(database, membership_fingerprints),
            )
        )
        application.include_router(
            create_human_oauth_consent_router(
                access.oauth_consent_handler,
                CSRFProtectionDependency(resolved_settings.csrf.trusted_origins),
            )
        )
        application.include_router(
            create_project_grant_router(
                human_session, partial(open_project_grant_change, database, fingerprints)
            )
        )
        application.include_router(
            create_project_action_grant_router(
                human_session, partial(open_project_action_grants, database)
            )
        )
        application.include_router(
            create_project_action_grant_change_router(
                human_session, partial(open_project_grant_change, database, fingerprints)
            )
        )
        application.include_router(
            create_my_project_access_router(
                human_session, partial(open_my_project_access, database)
            )
        )

        application.include_router(
            create_project_metadata_router(
                human_session,
                partial(open_project_metadata, database, metadata_fingerprints),
                partial(open_project_metadata, database, metadata_fingerprints),
                partial(open_project_name_resolution, database),
            )
        )

        application.include_router(
            create_original_operation_lookup_router(
                human_session, partial(open_original_operation_lookup, database)
            )
        )
        application.include_router(
            create_deletion_status_router(
                human_session, partial(open_deletion_status_lookup, database)
            )
        )

        application.add_middleware(RequestContextMiddleware)

        provider_cleanup.pop_all()
        return application
