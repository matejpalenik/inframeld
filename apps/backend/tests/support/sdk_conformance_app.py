"""Serve real HTTP adapters with synthetic collaborators for SDK conformance.

This factory never opens a database or calls Kratos, Hydra or a model provider.
It is test support, not an alternative deployment or authorization implementation.
"""

import asyncio
import base64
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from json import JSONDecodeError
from typing import Literal, override
from uuid import UUID

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, HttpUrl, JsonValue
from starlette.datastructures import UploadFile
from starlette.middleware.base import RequestResponseEndpoint
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response, StreamingResponse

from inframeld_backend.access.application.commands.assign_project_use_only_grant_command import (
    AssignProjectUseOnlyGrantCommand,
)
from inframeld_backend.access.application.commands.decide_human_oauth_consent_command import (
    DecideHumanOAuthConsentCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.human_oauth_consent_details_dto import (
    HumanOAuthConsentDetailsDTO,
)
from inframeld_backend.access.application.dtos.oauth_consent_continuation_dto import (
    OAuthConsentContinuationDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.protocols.human_access_token_authenticator import (
    HumanAccessTokenAuthenticator,
)
from inframeld_backend.access.application.protocols.human_oauth_consent_handler import (
    HumanOAuthConsentHandler,
)
from inframeld_backend.access.application.protocols.human_session_authenticator import (
    HumanSessionAuthenticator,
)
from inframeld_backend.access.application.protocols.project_grant_changer import ProjectGrantChanger
from inframeld_backend.access.application.queries.inspect_human_oauth_consent_query import (
    InspectHumanOAuthConsentQuery,
)
from inframeld_backend.access.application.value_objects.browser_session_credential import (
    BrowserSessionCredential,
)
from inframeld_backend.access.application.value_objects.human_access_token_credential import (
    HumanAccessTokenCredential,
)
from inframeld_backend.access.application.value_objects.oauth_client_id import OAuthClientId
from inframeld_backend.access.domain.enums.human_oauth_scope import HumanOAuthScope
from inframeld_backend.access.domain.value_objects.human_api_audience import HumanAPIAudience
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.http.dependencies.csrf_protection_dependency import (
    CSRFProtectionDependency,
)
from inframeld_backend.access.http.dependencies.human_session_dependency import (
    HumanSessionDependency,
)
from inframeld_backend.access.http.routes.current_session_routes import create_session_router
from inframeld_backend.access.http.routes.human_oauth_consent_routes import (
    create_human_oauth_consent_router,
)
from inframeld_backend.access.http.routes.project_grant_routes import create_project_grant_router
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.dtos.operation_admission_context_dto import (
    OperationAdmissionContextDTO,
)
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    AuthenticationRequiredError,
    DependencyUnavailableError,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.http.routes.health_routes import router as health_router
from tests.support.authentication_evidence import MockAuthenticationEvidence
from tests.support.openapi_schema_fixture import create_schema_fixture_app

PRINCIPAL = PrincipalId(UUID("00000000-0000-4000-8000-000000000001"))
IDENTITY = VerifiedHumanIdentityDTO(IdentityAuthority("kratos:test"), IdentitySubject("alice"))


class SDKFaultRequestDTO(BaseModel):
    """Arrange an isolated wire fault outside the delivered API contract."""

    kind: Literal[
        "none", "json", "raw", "malformed", "unexpected", "redirect", "slow", "disconnect"
    ]
    body: JsonValue = None
    status: int = 200
    body_base64: str = Field(default="", alias="bodyBase64")
    content_type: str | None = Field(default="application/json", alias="contentType")
    headers: list[tuple[str, str]] = Field(default_factory=list[tuple[str, str]])


class MockSDKBrowserAuthenticator(HumanSessionAuthenticator):
    @override
    async def authenticate(self, credential: BrowserSessionCredential | None) -> AccessContextDTO:
        if credential is None or credential.value != "sdk-cookie":
            raise AuthenticationRequiredError()

        return AccessContextDTO(PRINCIPAL, MockAuthenticationEvidence.browser(IDENTITY))


class MockSDKTokenAuthenticator(HumanAccessTokenAuthenticator):
    @override
    async def authenticate(self, credential: HumanAccessTokenCredential | None) -> AccessContextDTO:
        if credential is not None and credential.value == "sdk-denied":
            raise AccessDeniedError()
        if credential is not None and credential.value == "sdk-unavailable":
            raise DependencyUnavailableError()
        if credential is None or credential.value != "sdk-human":
            raise AuthenticationRequiredError()

        return AccessContextDTO(PRINCIPAL, MockAuthenticationEvidence.human_oauth(IDENTITY))


class MockSDKConsentHandler(HumanOAuthConsentHandler):
    @override
    async def inspect(
        self, *, credential: BrowserSessionCredential, query: InspectHumanOAuthConsentQuery
    ) -> HumanOAuthConsentDetailsDTO:
        if credential.value != "sdk-cookie":
            raise AuthenticationRequiredError()
        if query.challenge.value != "a+b&/":
            raise ValueError("The SDK changed the challenge query parameter.")

        return HumanOAuthConsentDetailsDTO(
            IDENTITY,
            OAuthClientId("inframeld-cli"),
            HumanAPIAudience("https://api.test"),
            (HumanOAuthScope.API,),
            (HumanAPIAudience("https://api.test"),),
            True,
            3600,
        )

    @override
    async def decide(
        self, *, credential: BrowserSessionCredential, command: DecideHumanOAuthConsentCommand
    ) -> OAuthConsentContinuationDTO:
        if credential.value != "sdk-cookie":
            raise AuthenticationRequiredError()
        if command.challenge.value != "a+b&/":
            raise ValueError("The SDK changed the consent request body.")

        return OAuthConsentContinuationDTO("https://auth.test/continue")


class MockSDKGrantChanger(ProjectGrantChanger):
    @override
    async def assign_use_only(
        self,
        *,
        access: AccessContextDTO,
        command: AssignProjectUseOnlyGrantCommand,
        context: OperationAdmissionContextDTO,
    ) -> CompletedSynchronousOperationDTO:
        if context.key.value != "sdk-key":
            raise ValueError("The SDK changed the idempotency header.")

        return CompletedSynchronousOperationDTO(
            OperationId("sdk-operation"),
            True,
            OperationReplayKind.SAFE_RESULT,
            datetime(2030, 1, 1, tzinfo=UTC),
        )


@asynccontextmanager
async def _open_grant_change() -> AsyncGenerator[ProjectGrantChanger]:
    yield MockSDKGrantChanger()


async def _fault_response(fault: SDKFaultRequestDTO | None) -> Response | None:
    """Return an explicitly arranged wire response without changing production routes."""
    if fault is None:
        return None

    headers = {"X-Request-ID": "00000000-0000-4000-8000-000000000099"}
    if fault.kind == "raw":
        response = Response(
            base64.b64decode(fault.body_base64, validate=True),
            status_code=fault.status,
            media_type=fault.content_type,
            headers=headers,
        )
        response.raw_headers.extend(
            (name.encode("ascii"), value.encode("latin1")) for name, value in fault.headers
        )
        return response
    if fault.kind == "json":
        return JSONResponse(
            fault.body, status_code=fault.status, headers=headers, media_type=fault.content_type
        )
    if fault.kind == "malformed":
        return Response(b"{", media_type="application/json", headers=headers)
    if fault.kind == "unexpected":
        return Response(
            b'{"unrecognized":true}',
            status_code=418,
            media_type="application/json",
            headers=headers,
        )
    if fault.kind == "redirect":
        return RedirectResponse("/health", status_code=307)
    if fault.kind == "slow":
        await asyncio.sleep(0.25)
    if fault.kind == "disconnect":
        # Observe one request, then lose its response. This is no persistence proof.
        async def interrupted_body() -> AsyncIterator[bytes]:
            yield b"{"
            raise RuntimeError("Synthetic lost response after an observed request.")

        return StreamingResponse(interrupted_body(), media_type="application/json")

    return None


class SDKCaseRequestDTO(BaseModel):
    """Register the exact native calls owned by one conformance case."""

    calls: dict[str, SDKFaultRequestDTO]


class SDKCaseEvidenceDTO(BaseModel):
    """Retain only one case's wire evidence until the caller collects it."""

    observations: dict[str, dict[str, JsonValue]]
    counts: dict[str, int]


def create_sdk_conformance_app(browser_origin: str | None = None) -> FastAPI:
    application = create_schema_fixture_app()
    origins = (HttpUrl("https://account.test"),)
    if browser_origin is not None:
        origins += (HttpUrl(browser_origin),)

    csrf = CSRFProtectionDependency(origins)
    authenticate = HumanSessionDependency(
        MockSDKBrowserAuthenticator(), csrf, access_token_authenticator=MockSDKTokenAuthenticator()
    )
    application.include_router(health_router)
    application.include_router(create_session_router(authenticate))
    application.include_router(create_project_grant_router(authenticate, _open_grant_change))
    application.include_router(create_human_oauth_consent_router(MockSDKConsentHandler(), csrf))
    counts: dict[str, int] = {}
    observations: dict[str, dict[str, JsonValue]] = {}
    faults: dict[str, SDKFaultRequestDTO] = {}

    cases: dict[str, set[str]] = {}

    @application.post("/sdk-control/cases/{case_id}", include_in_schema=False)
    async def configure_case(case_id: str, registration: SDKCaseRequestDTO) -> dict[str, str]:
        if case_id in cases or any(key in faults for key in registration.calls):
            raise HTTPException(status_code=409, detail="Case or call already registered")
        if not registration.calls:
            raise HTTPException(status_code=422, detail="A case requires calls")
        cases[case_id] = set(registration.calls)
        faults.update(registration.calls)
        return {"caseId": case_id}

    @application.get("/sdk-control/counts", include_in_schema=False)
    async def request_counts() -> dict[str, int]:
        return {"_total": counts.get("_total", 0)}

    @application.get("/sdk-control/cases/{case_id}", include_in_schema=False)
    async def case_evidence(case_id: str) -> SDKCaseEvidenceDTO:
        if case_id not in cases:
            raise HTTPException(status_code=404, detail="Case not registered")
        keys = cases[case_id]
        return SDKCaseEvidenceDTO(
            observations={key: observations[key] for key in keys if key in observations},
            counts={key: counts.get(key, 0) for key in keys},
        )

    @application.delete("/sdk-control/cases/{case_id}", include_in_schema=False)
    async def delete_case(case_id: str) -> dict[str, str]:
        if case_id not in cases:
            raise HTTPException(status_code=404, detail="Case not registered")
        for key in cases.pop(case_id):
            faults.pop(key, None)
            observations.pop(key, None)
            counts.pop(key, None)
        return {"caseId": case_id}

    @application.middleware("http")
    async def inject_fault(request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not request.url.path.startswith("/sdk-control/") and request.method != "OPTIONS":
            # Independent totals still expose a retry that drops the witness header.
            counts["_total"] = counts.get("_total", 0) + 1
        key = request.headers.get("X-SDK-Test")
        if key is not None and key in faults:
            counts[key] = counts.get(key, 0) + 1
            observations[key] = {
                "method": request.method,
                "path": request.url.path,
                "query": request.url.query,
                "cursor": request.query_params.get("cursor", ""),
                "authorization": request.headers.get("authorization", ""),
                "csrf": request.headers.get("x-inframeld-csrf", ""),
                "origin": request.headers.get("origin", ""),
                "headers": dict(request.headers),
                "rawBodyBase64": base64.b64encode(await request.body()).decode(),
            }
            if request.url.path == "/contract-fixture/upload":
                # Cache the wire body for the downstream route's independent parser.
                await request.body()
                async with request.form() as form:
                    upload = form.get("file")
                    if isinstance(upload, UploadFile):
                        observations[key]["fileBase64"] = base64.b64encode(
                            await upload.read()
                        ).decode()
                        observations[key]["fileName"] = upload.filename or ""
                    label = form.get("label")
                    if isinstance(label, str):
                        observations[key]["label"] = label
            if request.headers.get("content-type", "").split(";")[0] == "application/json":
                try:
                    payload_json: JsonValue = await request.json()
                    observations[key]["jsonBody"] = payload_json
                except JSONDecodeError:
                    pass
            if request.url.path == "/contract-fixture/payload":
                try:
                    payload: object = await request.json()
                except JSONDecodeError:
                    payload = {}
                if isinstance(payload, dict):
                    observations[key] |= {
                        "optionalAbsent": "optional_nullable" not in payload,
                        "optionalNull": "optional_nullable" in payload
                        and payload["optional_nullable"] is None,
                        "requiredNull": "required_nullable" in payload
                        and payload["required_nullable"] is None,
                    }

        arranged = await _fault_response(faults.get(key or ""))
        response = arranged if arranged is not None else await call_next(request)
        if key is not None and key in faults:
            observations[key]["status"] = response.status_code
        return response

    if browser_origin is not None:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=[browser_origin],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
            expose_headers=["X-Request-ID", "WWW-Authenticate"],
        )

    return application
