"""Expose the supported project grant command over authenticated HTTP."""

from http import HTTPStatus
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.services.project_grant_change_fingerprint_service import (
    ProjectGrantChangeFingerprintService,
)
from inframeld_backend.access.application.services.project_grant_change_service import (
    ProjectGrantChangeService,
)
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.http.dependencies.human_session_dependency import (
    HumanSessionDependency,
)
from inframeld_backend.access.http.openapi.human_authentication_responses import (
    human_authentication_responses,
)
from inframeld_backend.access.http.requests.project_use_only_grant_request import (
    ProjectUseOnlyGrantRequest,
)
from inframeld_backend.access.http.responses.project_use_only_grant_response import (
    ProjectUseOnlyGrantResponse,
)
from inframeld_backend.access.infrastructure.readers.postgres_project_grant_change_facts_reader import (
    PostgresProjectGrantChangeFactsReader,
)
from inframeld_backend.access.infrastructure.writers.postgres_project_grant_change_writer import (
    PostgresProjectGrantChangeWriter,
)
from inframeld_backend.shared.application.dtos.project_operation_admission_request_dto import (
    ProjectOperationAdmissionRequestDTO,
)
from inframeld_backend.shared.application.errors.application_errors import ConflictError
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.http.definitions.problem_catalogue import (
    ACCESS_DENIED_PROBLEM,
    CONFLICT_PROBLEM,
    DEPENDENCY_UNAVAILABLE_PROBLEM,
    RESOURCE_NOT_FOUND_PROBLEM,
    VALIDATION_ERROR_PROBLEM,
)
from inframeld_backend.shared.http.dependencies.idempotency_key_dependency import (
    IdempotencyKeyDependency,
)
from inframeld_backend.shared.http.openapi.problem_openapi import problem_responses
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.writers.postgres_operation_reservation_writer import (
    PostgresOperationReservationWriter,
)

_GRANT_ROUTE = "/v1/projects/{project_id}/grants"

_GRANT_PROBLEM_RESPONSES = (
    human_authentication_responses()
    | problem_responses(ACCESS_DENIED_PROBLEM)
    | problem_responses(RESOURCE_NOT_FOUND_PROBLEM)
    | problem_responses(CONFLICT_PROBLEM)
    | problem_responses(VALIDATION_ERROR_PROBLEM)
    | problem_responses(DEPENDENCY_UNAVAILABLE_PROBLEM)
)
_GRANT_PROBLEM_RESPONSES[409]["description"] = (
    "Conflict: stale_revision, idempotency_key_reused, idempotency_in_progress, or conflict."
)


def create_project_grant_router(
    authenticate: HumanSessionDependency,
    database: Database,
    fingerprints: ProjectGrantChangeFingerprintService,
) -> APIRouter:
    """Register a use-only grant command with its trusted request dependencies."""
    router = APIRouter(prefix="/v1")
    key_dependency = IdempotencyKeyDependency()

    @router.post(
        "/projects/{project_id}/grants",
        tags=["access"],
        operation_id="assignProjectUseOnlyGrant",
        status_code=HTTPStatus.CREATED,
        responses=_GRANT_PROBLEM_RESPONSES,
    )
    async def assign_use_only(
        project_id: UUID,
        body: ProjectUseOnlyGrantRequest,
        idempotency_key: Annotated[IdempotencyKey, Depends(key_dependency)],
        access: Annotated[AccessContextDTO, Depends(authenticate)],
    ) -> ProjectUseOnlyGrantResponse:
        parsed_project_id = ProjectId(project_id)
        recipient_id = PrincipalId(body.recipient_principal_id)
        action_id = ActionId(body.action_id)

        command = ProjectOperationAdmissionRequestDTO(
            project_id=parsed_project_id,
            method="POST",
            requested_route=_GRANT_ROUTE,
            key=idempotency_key,
            fingerprint=fingerprints.for_assign_use_only(
                project_id=parsed_project_id,
                recipient_principal_id=recipient_id,
                action_id=action_id,
                expected_access_revision=body.expected_access_revision,
            ),
        )

        # Authentication and CSRF have completed before this short transaction.
        async with database.session() as session, session.begin():
            service = ProjectGrantChangeService(
                PostgresProjectGrantChangeFactsReader(session),
                PostgresOperationReservationWriter(session),
                PostgresProjectGrantChangeWriter(session),
            )
            result = await service.assign_use_only(
                access=access,
                request=command,
                recipient_principal_id=recipient_id,
                action_id=action_id,
                expected_access_revision=body.expected_access_revision,
            )

            if result.expires_at is None:
                raise ConflictError("The grant operation has no completed replay deadline.")

        return ProjectUseOnlyGrantResponse(
            operation_id=result.operation_id.value,
            project_id=project_id,
            recipient_principal_id=body.recipient_principal_id,
            action_id=body.action_id,
            access_revision=body.expected_access_revision + 1,
            idempotency_expires_at=result.expires_at,
        )

    return router
