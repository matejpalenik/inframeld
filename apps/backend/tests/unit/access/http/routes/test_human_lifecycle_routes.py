from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import override
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import HttpUrl, ValidationError
from tests.support.authentication_evidence import MockAuthenticationEvidence
from tests.support.mock_application_authenticator import MockApplicationAuthenticator
from tests.support.mock_human_lifecycle import (
    ACCESS,
    ASYNC,
    RESTORE,
    SUSPEND,
    SYNC,
    TARGET,
    VERSION,
    MockHumanLifecycle,
    context,
)

from inframeld_backend.access.application.commands.restore_human_command import RestoreHumanCommand
from inframeld_backend.access.application.commands.suspend_human_command import SuspendHumanCommand
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.human_restoration_result_dto import (
    HumanRestorationResultDTO,
)
from inframeld_backend.access.application.dtos.human_suspension_result_dto import (
    HumanSuspensionResultDTO,
)
from inframeld_backend.access.application.protocols.human_access_token_authenticator import (
    HumanAccessTokenAuthenticator,
)
from inframeld_backend.access.application.protocols.human_restorer import HumanRestorer
from inframeld_backend.access.application.protocols.human_session_authenticator import (
    HumanSessionAuthenticator,
)
from inframeld_backend.access.application.protocols.human_suspender import HumanSuspender
from inframeld_backend.access.application.value_objects.browser_session_credential import (
    BrowserSessionCredential,
)
from inframeld_backend.access.application.value_objects.human_access_token_credential import (
    HumanAccessTokenCredential,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.http.dependencies.csrf_protection_dependency import (
    CSRFProtectionDependency,
)
from inframeld_backend.access.http.dependencies.product_access_dependency import (
    ProductAccessDependency,
)
from inframeld_backend.access.http.handlers.human_oauth_credential_error_handler import (
    register_human_oauth_credential_error_handler,
)
from inframeld_backend.access.http.responses.human_restoration_response import (
    HumanRestorationResponse,
)
from inframeld_backend.access.http.responses.human_suspension_response import (
    HumanSuspensionResponse,
)
from inframeld_backend.access.http.routes.human_lifecycle_routes import (
    create_human_lifecycle_router,
)
from inframeld_backend.bootstrap.application_factory import create_app
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.errors.application_error import ApplicationError
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    AuthenticationRequiredError,
    ConflictError,
    DependencyUnavailableError,
    ResourceNotFoundError,
    StaleRevisionError,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.application.value_objects.request_id import RequestId
from inframeld_backend.shared.http.handlers.error_handlers import register_error_handlers
from inframeld_backend.shared.http.middleware.request_context_middleware import (
    RequestContextMiddleware,
)
from inframeld_backend.shared.http.openapi.problem_openapi import configure_problem_openapi

OAUTH_ACCESS = AccessContextDTO(ACCESS.actor_principal_id, MockAuthenticationEvidence.human_oauth())
APP_ACCESS = AccessContextDTO(
    PrincipalId(UUID(int=900)), MockAuthenticationEvidence.application_key()
)
APP_KEY = "ifm_app_00000000-0000-4000-8000-000000000003_" + "A" * 43
HEADERS = {
    "Cookie": "ory_kratos_session=controlled-cookie",
    "Origin": "https://account.test",
    "X-Inframeld-CSRF": "1",
    "Idempotency-Key": "lifecycle-request",
}


def route(operation: str) -> str:
    return f"/v1/organizations/{SUSPEND.organization_id.value}/humans/{TARGET.id.value}/{operation}"


def body(operation: str) -> dict[str, object]:
    return {
        "expectedAccessRevision": 7,
        **(
            {"reason": SUSPEND.reason.value}
            if operation == "suspend"
            else {"securityReviewReference": RESTORE.security_review_reference.value}
        ),
    }


class MockLifecycleAuthenticator(HumanSessionAuthenticator, HumanAccessTokenAuthenticator):
    @override
    async def authenticate(
        self, credential: BrowserSessionCredential | HumanAccessTokenCredential | None
    ) -> AccessContextDTO:
        if isinstance(credential, BrowserSessionCredential):
            return ACCESS
        if isinstance(credential, HumanAccessTokenCredential):
            return OAUTH_ACCESS
        raise AuthenticationRequiredError()


class MockLifecycleOperations(HumanSuspender, HumanRestorer):
    def __init__(self, *, replay: bool = False) -> None:
        self.suspension = HumanSuspensionResultDTO(
            SUSPEND.organization_id,
            TARGET.id,
            ACCESS.actor_principal_id,
            8,
            OperationId("original-cleanup"),
            replace(ASYNC, created=not replay),
        )
        self.restoration = HumanRestorationResultDTO(
            RESTORE.organization_id,
            TARGET.id,
            ACCESS.actor_principal_id,
            8,
            VERSION,
            replace(SYNC, created=not replay),
        )
        self.calls: list[
            tuple[
                SuspendHumanCommand | RestoreHumanCommand, IdempotencyContextDTO, AccessContextDTO
            ]
        ] = []
        self.error: ApplicationError | None = None

    @override
    async def suspend(
        self,
        *,
        access: AccessContextDTO,
        command: SuspendHumanCommand,
        context: IdempotencyContextDTO,
        request_id: RequestId,
    ) -> HumanSuspensionResultDTO:
        self.calls.append((command, context, access))
        if self.error is not None:
            raise self.error
        return self.suspension

    @override
    async def restore(
        self,
        *,
        access: AccessContextDTO,
        command: RestoreHumanCommand,
        context: IdempotencyContextDTO,
    ) -> HumanRestorationResultDTO:
        self.calls.append((command, context, access))
        if self.error is not None:
            raise self.error
        return self.restoration


def client_for(
    service: MockLifecycleOperations, actual: MockHumanLifecycle | None = None
) -> TestClient:
    @asynccontextmanager
    async def open_suspender() -> AsyncGenerator[HumanSuspender]:
        yield actual.suspend_service() if actual is not None else service

    @asynccontextmanager
    async def open_restorer() -> AsyncGenerator[HumanRestorer]:
        yield actual.restore_service() if actual is not None else service

    app = FastAPI()
    configure_problem_openapi(app)
    register_error_handlers(app)
    register_human_oauth_credential_error_handler(app)
    auth = MockLifecycleAuthenticator()
    app.include_router(
        create_human_lifecycle_router(
            ProductAccessDependency(
                auth,
                CSRFProtectionDependency((HttpUrl("https://account.test"),)),
                access_token_authenticator=auth,
                application_authenticator=MockApplicationAuthenticator(APP_ACCESS),
            ),
            open_suspender,
            open_restorer,
        )
    )
    app.add_middleware(RequestContextMiddleware)
    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize("operation", ["suspend", "restore"])
@pytest.mark.parametrize("replay", [False, True])
def test_exact_original_receipt_and_status_are_preserved(operation: str, replay: bool) -> None:
    service = MockLifecycleOperations(replay=replay)
    with client_for(service) as client:
        response = client.post(route(operation), json=body(operation), headers=HEADERS)
    assert response.status_code == (202 if operation == "suspend" else 200)
    expected = {
        "operationId": ASYNC.operation_id.value,
        "organizationId": str(SUSPEND.organization_id.value),
        "principalId": str(TARGET.id.value),
        "accessRevision": 8,
        "idempotencyExpiresAt": None if operation == "suspend" else "2030-01-01T00:00:00Z",
    }
    if operation == "suspend":
        expected.update({"accessBlocked": True, "cleanupOperationId": "original-cleanup"})
    assert response.json() == expected
    assert response.headers["cache-control"] == "no-store"
    assert service.calls == [
        (SUSPEND if operation == "suspend" else RESTORE, context(operation == "restore"), ACCESS)
    ]


@pytest.mark.parametrize("operation", ["suspend", "restore"])
def test_human_bearer_carries_distinct_oauth_evidence_without_cookie_csrf(operation: str) -> None:
    from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
        HumanOAuthCredentialBindingDTO,
    )

    service = MockLifecycleOperations()
    with client_for(service) as client:
        response = client.post(
            route(operation),
            json=body(operation),
            headers={
                "Authorization": "Bearer controlled-token",
                "Idempotency-Key": "lifecycle-request",
            },
        )
    assert response.status_code == (202 if operation == "suspend" else 200)
    assert len(service.calls) == 1 and service.calls[0][2] == OAUTH_ACCESS
    assert isinstance(service.calls[0][2].authentication_evidence, HumanOAuthCredentialBindingDTO)


@pytest.mark.parametrize("operation", ["suspend", "restore"])
@pytest.mark.parametrize("revision", [True, "7", 7.0, -1, 2**53])
def test_revision_is_strict_and_safe_before_either_port(operation: str, revision: object) -> None:
    service = MockLifecycleOperations()
    with client_for(service) as client:
        response = client.post(
            route(operation),
            json={**body(operation), "expectedAccessRevision": revision},
            headers=HEADERS,
        )
    assert response.status_code == 422 and not service.calls
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("operation", ["suspend", "restore"])
@pytest.mark.parametrize(
    "text", ["", " ", "private\nmarker", "private\u2028marker", "x" * 1025, 42]
)
def test_review_text_is_required_bounded_and_safe(operation: str, text: object) -> None:
    service = MockLifecycleOperations()
    field = "reason" if operation == "suspend" else "securityReviewReference"
    with client_for(service) as client:
        response = client.post(
            route(operation), json={**body(operation), field: text}, headers=HEADERS
        )
    assert response.status_code == 422 and not service.calls
    assert "private" not in response.text and response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("operation", ["suspend", "restore"])
@pytest.mark.parametrize(
    "raw,status",
    [
        ("{}", 422),
        ("[1,2]", 422),
        ("{", 422),
        ('{"expectedAccessRevision":7,"expectedAccessRevision":8}', 422),
        ('{"expectedAccessRevision":NaN}', 422),
        ('{"pad":"' + "x" * 32768 + '"}', 413),
    ],
)
def test_bounded_unambiguous_json_precedes_either_port(
    operation: str, raw: str, status: int
) -> None:
    service = MockLifecycleOperations()
    with client_for(service) as client:
        response = client.post(
            route(operation), content=raw, headers={**HEADERS, "Content-Type": "application/json"}
        )
    assert response.status_code == status and not service.calls
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["content-type"].startswith("application/problem+json")


@pytest.mark.parametrize("operation", ["suspend", "restore"])
@pytest.mark.parametrize("removed", ["Cookie", "Origin", "X-Inframeld-CSRF", "Idempotency-Key"])
def test_missing_auth_csrf_or_key_does_not_invoke_either_port(operation: str, removed: str) -> None:
    service = MockLifecycleOperations()
    with client_for(service) as client:
        response = client.post(
            route(operation),
            json=body(operation),
            headers={k: v for k, v in HEADERS.items() if k != removed},
        )
    assert response.status_code in {401, 403, 422} and not service.calls
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("operation", ["suspend", "restore"])
def test_duplicate_key_and_wrong_media_type_do_not_invoke_either_port(operation: str) -> None:
    service = MockLifecycleOperations()
    with client_for(service) as client:
        duplicate = client.post(
            route(operation),
            json=body(operation),
            headers=[*HEADERS.items(), ("Idempotency-Key", "another")],
        )
        media = client.post(
            route(operation), content="private", headers={**HEADERS, "Content-Type": "text/plain"}
        )
    assert duplicate.status_code == 422 and media.status_code == 415 and not service.calls
    assert all(r.headers["cache-control"] == "no-store" for r in [duplicate, media])


@pytest.mark.parametrize("operation", ["suspend", "restore"])
@pytest.mark.parametrize(
    "error,status",
    [
        (AuthenticationRequiredError(), 401),
        (AccessDeniedError(), 403),
        (ResourceNotFoundError(), 404),
        (ConflictError(), 409),
        (StaleRevisionError(), 409),
        (DependencyUnavailableError(), 503),
    ],
)
def test_typed_application_problems_are_safe_and_noncacheable(
    operation: str, error: ApplicationError, status: int
) -> None:
    service = MockLifecycleOperations()
    service.error = error
    with client_for(service) as client:
        response = client.post(route(operation), json=body(operation), headers=HEADERS)
    assert response.status_code == status
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["requestId"]


@pytest.mark.parametrize("operation", ["suspend", "restore"])
def test_valid_application_key_reaches_the_actual_human_only_guard(operation: str) -> None:
    actual = MockHumanLifecycle(restoring=operation == "restore")
    assert actual.facts is not None
    actual.facts = replace(
        actual.facts,
        actor=replace(
            actual.facts.actor, id=APP_ACCESS.actor_principal_id, kind=PrincipalKind.APPLICATION
        ),
        actor_credential_facts=None,
    )
    service = MockLifecycleOperations()
    with client_for(service, actual) as client:
        response = client.post(
            route(operation),
            json=body(operation),
            headers={"Authorization": "Bearer " + APP_KEY, "Idempotency-Key": "lifecycle-request"},
        )
    assert response.status_code == 403 and not actual.writes
    assert (
        "preauthorization" in actual.events
        and "reserve" not in actual.events
        and "verify" not in actual.events
    )


def receipt_values(
    model: type[HumanSuspensionResponse] | type[HumanRestorationResponse],
) -> dict[str, object]:
    values: dict[str, object] = {
        "operation_id": "original",
        "organization_id": SUSPEND.organization_id.value,
        "principal_id": TARGET.id.value,
        "access_revision": 8,
    }
    if model is HumanSuspensionResponse:
        values.update({"access_blocked": True, "cleanup_operation_id": "original-cleanup"})
    return values


@pytest.mark.parametrize("model", [HumanSuspensionResponse, HumanRestorationResponse])
def test_original_expiry_is_required_with_operation_specific_nullability(
    model: type[HumanSuspensionResponse] | type[HumanRestorationResponse],
) -> None:
    values = receipt_values(model)
    with pytest.raises(ValidationError):
        model.model_validate(values)
    if model is HumanSuspensionResponse:
        assert (
            model.model_validate({**values, "idempotency_expires_at": None}).idempotency_expires_at
            is None
        )
    else:
        with pytest.raises(ValidationError):
            model.model_validate({**values, "idempotency_expires_at": None})
    with pytest.raises(ValidationError):
        model.model_validate({**values, "idempotency_expires_at": datetime(2030, 1, 1)})
    expiry = datetime(2030, 1, 1, 1, tzinfo=timezone(timedelta(hours=1)))
    assert (
        model.model_validate({**values, "idempotency_expires_at": expiry}).model_dump(
            mode="json", by_alias=True
        )["idempotencyExpiresAt"]
        == "2030-01-01T00:00:00Z"
    )


@pytest.mark.parametrize("model", [HumanSuspensionResponse, HumanRestorationResponse])
def test_receipt_schema_closes_fields_and_bounds_opaque_ids(
    model: type[HumanSuspensionResponse] | type[HumanRestorationResponse],
) -> None:
    schema = model.model_json_schema(mode="serialization")
    assert schema.get("additionalProperties") is False
    ids = ["operationId"]
    if model is HumanSuspensionResponse:
        ids.append("cleanupOperationId")
    for field in ids:
        properties = schema["properties"][field]
        assert (properties["minLength"], properties["maxLength"]) == (1, 128)
        assert field in schema["required"]
    assert "idempotencyExpiresAt" in schema["required"]
    with pytest.raises(ValidationError):
        model.model_validate(
            {
                **receipt_values(model),
                "idempotency_expires_at": "2030-01-01T00:00:00Z",
                "unexpected": "private",
            }
        )


@pytest.mark.parametrize(
    ("model", "field"),
    [
        (HumanSuspensionResponse, "operation_id"),
        (HumanSuspensionResponse, "cleanup_operation_id"),
        (HumanRestorationResponse, "operation_id"),
    ],
)
def test_receipt_opaque_ids_accept_only_one_to_128_characters(
    model: type[HumanSuspensionResponse] | type[HumanRestorationResponse], field: str
) -> None:
    values = {**receipt_values(model), "idempotency_expires_at": "2030-01-01T00:00:00Z"}
    for identifier in ("x", "x" * 128):
        assert model.model_validate({**values, field: identifier}).model_dump()[field] == identifier
    for identifier in ("", "x" * 129):
        with pytest.raises(ValidationError):
            model.model_validate({**values, field: identifier})


@pytest.mark.parametrize("operation", ["suspend", "restore"])
@pytest.mark.parametrize("token", ["x", "\U0001f600"])
@pytest.mark.parametrize("over_limit", [False, True])
def test_audit_character_limit_accepts_multibyte_text_at_boundary(
    operation: str, token: str, over_limit: bool
) -> None:
    service = MockLifecycleOperations()
    field, limit, status = (
        ("reason", 512, 202) if operation == "suspend" else ("securityReviewReference", 128, 200)
    )
    text = token * (limit + int(over_limit))
    with client_for(service) as client:
        response = client.post(
            route(operation), json={**body(operation), field: text}, headers=HEADERS
        )
    assert response.status_code == (422 if over_limit else status)
    assert len(service.calls) == int(not over_limit)
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("operation", ["suspend", "restore"])
def test_registered_factory_rejects_bad_media_before_authentication(operation: str) -> None:
    client = TestClient(create_app())
    try:
        response = client.post(
            route(operation), content="not-json", headers={"Content-Type": "text/plain"}
        )
    finally:
        client.close()
    assert response.status_code == 415
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("operation", ["suspend", "restore"])
def test_noop_receipt_does_not_infer_a_new_revision_or_expose_private_version(
    operation: str,
) -> None:
    service = MockLifecycleOperations()
    service.suspension = replace(service.suspension, access_revision=7)
    service.restoration = replace(service.restoration, access_revision=7)
    with client_for(service) as client:
        response = client.post(route(operation), json=body(operation), headers=HEADERS)
    assert response.status_code == (202 if operation == "suspend" else 200)
    assert response.json()["accessRevision"] == 7
    assert len(response.json()) == (7 if operation == "suspend" else 5)
    assert len(service.calls) == 1


@pytest.mark.parametrize("operation", ["suspend", "restore"])
def test_extra_private_input_and_missing_review_field_are_rejected(operation: str) -> None:
    service = MockLifecycleOperations()
    field = "reason" if operation == "suspend" else "securityReviewReference"
    with client_for(service) as client:
        extra = client.post(
            route(operation),
            json={**body(operation), "identity": "private-marker"},
            headers=HEADERS,
        )
        missing = client.post(
            route(operation),
            json={key: value for key, value in body(operation).items() if key != field},
            headers=HEADERS,
        )
    assert extra.status_code == missing.status_code == 422 and not service.calls
    assert "private-marker" not in extra.text


@pytest.mark.parametrize("operation", ["suspend", "restore"])
@pytest.mark.parametrize("part", ["organization", "principal"])
def test_malformed_path_scope_does_not_invoke_either_port(operation: str, part: str) -> None:
    service = MockLifecycleOperations()
    target = route(operation).replace(
        str(SUSPEND.organization_id.value) if part == "organization" else str(TARGET.id.value),
        "invalid",
    )
    with client_for(service) as client:
        response = client.post(target, json=body(operation), headers=HEADERS)
    assert response.status_code == 422 and not service.calls
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("operation", ["suspend", "restore"])
def test_path_uuids_are_canonical_in_the_original_retry_context(operation: str) -> None:
    organization = UUID("abcdefab-abcd-4bcd-8bcd-abcdefabcdef")
    principal = UUID("bbbbbbbb-abcd-4bcd-8bcd-abcdefabcdef")
    service = MockLifecycleOperations()
    with client_for(service) as client:
        response = client.post(
            f"/v1/organizations/{str(organization).upper()}/humans/{str(principal).upper()}/{operation}",
            json=body(operation),
            headers=HEADERS,
        )
    assert response.status_code == (202 if operation == "suspend" else 200)
    command, original, _access = service.calls[0]
    assert command.organization_id.value == organization and command.principal_id.value == principal
    assert (
        original.requested_route
        == f"/v1/organizations/{organization}/humans/{principal}/{operation}"
    )


@pytest.mark.parametrize("operation", ["suspend", "restore"])
def test_stale_human_family_challenges_are_not_crossed(operation: str) -> None:
    from inframeld_backend.access.application.errors.human_oauth_credential_rejected_error import (
        HumanOAuthCredentialRejectedError,
    )

    service = MockLifecycleOperations()
    with client_for(service) as client:
        service.error = AuthenticationRequiredError()
        browser = client.post(route(operation), json=body(operation), headers=HEADERS)
        service.error = HumanOAuthCredentialRejectedError()
        bearer = client.post(
            route(operation),
            json=body(operation),
            headers={
                "Authorization": "Bearer controlled-token",
                "Idempotency-Key": "lifecycle-request",
            },
        )
    assert browser.status_code == bearer.status_code == 401
    assert "invalid_token" not in browser.headers.get("www-authenticate", "")
    assert "invalid_token" in bearer.headers["www-authenticate"]
