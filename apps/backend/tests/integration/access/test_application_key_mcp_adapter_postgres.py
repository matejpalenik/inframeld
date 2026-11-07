"""Qualify the credential guard and real authorizer as ASGI components, without an MCP server."""

import os

import httpx2
import pytest
from sqlalchemy import DateTime, delete, func, update
from starlette.responses import JSONResponse
from starlette.types import Message, Receive, Scope, Send
from tests.support.application_key_scenarios import seed_application_key, store_application_key

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.application_key_authentication_dto import (
    ApplicationKeyAuthenticationDTO,
)
from inframeld_backend.access.application.dtos.application_key_verification_profile_dto import (
    ApplicationKeyVerificationProfileDTO,
)
from inframeld_backend.access.application.dtos.project_action_authorization_dto import (
    ProjectActionAuthorizationDTO,
)
from inframeld_backend.access.application.dtos.project_action_authorization_request_dto import (
    ProjectActionAuthorizationRequestDTO,
)
from inframeld_backend.access.application.errors.application_key_credential_rejected_error import (
    ApplicationKeyCredentialRejectedError,
)
from inframeld_backend.access.application.services.action_authorization_service import (
    ActionAuthorizationService,
)
from inframeld_backend.access.application.services.application_authentication_service import (
    ApplicationAuthenticationService,
)
from inframeld_backend.access.domain.enums.application_key_adapter import ApplicationKeyAdapter
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.project_action import ProjectAction
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.application_key_audience import (
    ApplicationKeyAudience,
)
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.http.mappers.mcp_access_context_mapper import MCPAccessContextMapper
from inframeld_backend.access.http.middleware.mcp_application_key_middleware import (
    MCPApplicationKeyMiddleware,
)
from inframeld_backend.access.infrastructure.readers.postgres_application_authentication_facts_reader import (
    PostgresApplicationAuthenticationFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_project_action_facts_reader import (
    PostgresProjectActionFactsReader,
)
from inframeld_backend.access.infrastructure.rows.application_key_row import ApplicationKeyRow
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.verifiers.postgres_application_key_verifier import (
    PostgresApplicationKeyVerifier,
)
from inframeld_backend.shared.http.middleware.request_context_middleware import (
    RequestContextMiddleware,
)
from inframeld_backend.shared.infrastructure.resources.database import Database

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
        reason="Requires isolated PostgreSQL services",
    ),
]
HTTP_PROFILE = ApplicationKeyVerificationProfileDTO(
    ApplicationKeyAudience("https://api.test"), ApplicationKeyAdapter.HTTP
)
MCP_PROFILE = ApplicationKeyVerificationProfileDTO(
    ApplicationKeyAudience("https://api.test/mcp"), ApplicationKeyAdapter.MCP
)
ACTION = ActionId(ProjectAction.INSPECT_BUDGET.value)


def _authenticator(database: Database) -> ApplicationAuthenticationService:
    return ApplicationAuthenticationService(
        key_verifier=PostgresApplicationKeyVerifier(database),
        authentication_facts_reader=PostgresApplicationAuthenticationFactsReader(database),
        verification_profile=MCP_PROFILE,
    )


async def _grant(database: Database, access: AccessContextDTO, project_id: ProjectId) -> None:
    async with database.session() as session, session.begin():
        session.add(
            ProjectActionGrantRow(
                project_id=project_id.value,
                recipient_principal_id=access.actor_principal_id.value,
                recipient_kind=PrincipalKind.APPLICATION,
                action=ACTION.value,
                can_grant=False,
            )
        )


async def _authorize(
    database: Database,
    access: AccessContextDTO,
    project_id: ProjectId,
    profile: ApplicationKeyVerificationProfileDTO | None,
) -> ProjectActionAuthorizationDTO:
    async with database.session() as session, session.begin():
        return await ActionAuthorizationService(
            PostgresProjectActionFactsReader(session, application_key_profile=profile)
        ).require_authorization(
            access=access, request=ProjectActionAuthorizationRequestDTO(project_id, ACTION)
        )


async def test_real_mcp_headers_are_consumed_and_protocol_sessions_never_replace_current_keys(
    database: Database,
) -> None:
    seed = await seed_application_key(
        database, audience=MCP_PROFILE.audience.value, adapters=(ApplicationKeyAdapter.MCP,)
    )
    auth = _authenticator(database)
    access = await auth.authenticate(seed.credential)
    await _grant(database, access, seed.account.project_id)
    replacement = await store_application_key(
        database,
        principal_id=seed.account.principal_id,
        organization_id=seed.account.organization_id,
        project_id=seed.account.project_id,
        issued_by=seed.creator_access.actor_principal_id,
        audience=MCP_PROFILE.audience.value,
        adapters=(ApplicationKeyAdapter.MCP,),
    )
    observed: list[AccessContextDTO] = []

    async def operation(scope: Scope, receive: Receive, send: Send) -> None:
        current = MCPAccessContextMapper.from_scope(scope)
        observed.append(current)
        assert all(name.lower() != b"authorization" for name, _value in scope["headers"])
        authorized = await _authorize(database, current, seed.account.project_id, MCP_PROFILE)
        await JSONResponse(
            {
                "principalId": str(current.actor_principal_id.value),
                "projectId": str(authorized.project_id.value),
            },
            headers={"Cache-Control": "no-store"},
        )(scope, receive, send)

    application = RequestContextMiddleware(
        MCPApplicationKeyMiddleware(operation, authenticator=auth)
    )
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=application), base_url="https://api.test"
    ) as client:
        first = await client.post(
            "/mcp/tools/query",
            headers={
                "Authorization": "Bearer " + seed.credential.value,
                "Mcp-Session-Id": "old-session",
            },
        )
        second = await client.get(
            "/mcp/saved-result",
            headers={
                "Authorization": "Bearer " + replacement.value,
                "Mcp-Session-Id": "old-session",
            },
        )
        missing = await client.delete(
            "/mcp/session/claimed", headers={"Mcp-Session-Id": "old-session"}
        )
        async with database.session() as session, session.begin():
            await session.execute(
                update(ApplicationKeyRow)
                .where(ApplicationKeyRow.key_id == seed.credential.key_id.value)
                .values(revoked_at=func.clock_timestamp(type_=DateTime(timezone=True)))
            )
        revoked = await client.post(
            "/mcp/tools/query",
            headers={
                "Authorization": "Bearer " + seed.credential.value,
                "Mcp-Session-Id": "old-session",
            },
        )
    expected = {
        "principalId": str(seed.account.principal_id.value),
        "projectId": str(seed.account.project_id.value),
    }
    assert (
        first.status_code == second.status_code == 200 and first.json() == second.json() == expected
    )
    assert missing.status_code == revoked.status_code == 401
    assert [item.authentication_evidence for item in observed] == [
        ApplicationKeyAuthenticationDTO(seed.credential.key_id),
        ApplicationKeyAuthenticationDTO(replacement.key_id),
    ]
    for response in [first, second, missing, revoked]:
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-request-id"]
        assert seed.credential.value not in response.text and replacement.value not in response.text


@pytest.mark.parametrize(
    ("stored_profile", "downstream_profile", "status", "dispatched"),
    [
        (HTTP_PROFILE, MCP_PROFILE, 401, 0),
        (MCP_PROFILE, HTTP_PROFILE, 401, 1),
        (MCP_PROFILE, None, 503, 1),
    ],
    ids=["http-key", "independent-downstream-profile", "missing-downstream-profile"],
)
async def test_real_mcp_requires_both_initial_and_downstream_trusted_profiles(
    database: Database,
    stored_profile: ApplicationKeyVerificationProfileDTO,
    downstream_profile: ApplicationKeyVerificationProfileDTO | None,
    status: int,
    dispatched: int,
) -> None:
    seed = await seed_application_key(
        database, audience=stored_profile.audience.value, adapters=(stored_profile.adapter,)
    )
    called = 0

    async def operation(scope: Scope, receive: Receive, send: Send) -> None:
        nonlocal called
        called += 1
        await _authorize(
            database,
            MCPAccessContextMapper.from_scope(scope),
            seed.account.project_id,
            downstream_profile,
        )
        await JSONResponse({"protected": True})(scope, receive, send)

    application = RequestContextMiddleware(
        MCPApplicationKeyMiddleware(operation, authenticator=_authenticator(database))
    )
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=application), base_url="https://api.test"
    ) as client:
        response = await client.post(
            "/mcp/tools/query",
            headers={
                "Authorization": "Bearer " + seed.credential.value,
            },
        )
    assert response.status_code == status and called == dispatched
    assert response.headers["cache-control"] == "no-store"
    assert seed.credential.value not in response.text
    if status == 401:
        assert (
            response.headers["www-authenticate"]
            == 'Bearer realm="inframeld", error="invalid_token"'
        )


@pytest.mark.parametrize(
    "revoke", [True, False], ids=["revoked-before-disclosure", "grant-removed"]
)
async def test_real_mcp_maps_late_current_authority_failure_before_response_start(
    database: Database, revoke: bool
) -> None:
    seed = await seed_application_key(
        database, audience=MCP_PROFILE.audience.value, adapters=(ApplicationKeyAdapter.MCP,)
    )
    auth = _authenticator(database)
    await _grant(database, await auth.authenticate(seed.credential), seed.account.project_id)

    async def operation(scope: Scope, receive: Receive, send: Send) -> None:
        async with database.session() as session, session.begin():
            if revoke:
                await session.execute(
                    update(ApplicationKeyRow)
                    .where(ApplicationKeyRow.key_id == seed.credential.key_id.value)
                    .values(revoked_at=func.clock_timestamp(type_=DateTime(timezone=True)))
                )
            else:
                await session.execute(
                    delete(ProjectActionGrantRow).where(
                        ProjectActionGrantRow.project_id == seed.account.project_id.value,
                        ProjectActionGrantRow.recipient_principal_id
                        == seed.account.principal_id.value,
                        ProjectActionGrantRow.action == ACTION.value,
                    )
                )
        await _authorize(
            database, MCPAccessContextMapper.from_scope(scope), seed.account.project_id, MCP_PROFILE
        )
        await JSONResponse({"protected": True})(scope, receive, send)

    application = RequestContextMiddleware(
        MCPApplicationKeyMiddleware(operation, authenticator=auth)
    )
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=application), base_url="https://api.test"
    ) as client:
        response = await client.post(
            "/mcp/tools/query",
            headers={
                "Authorization": "Bearer " + seed.credential.value,
            },
        )
    assert response.status_code == (401 if revoke else 403)
    assert response.headers["cache-control"] == "no-store" and response.headers["x-request-id"]
    assert seed.credential.value not in response.text
    if revoke:
        assert (
            response.headers["www-authenticate"]
            == 'Bearer realm="inframeld", error="invalid_token"'
        )


async def test_real_mcp_late_revocation_after_response_start_propagates_without_replacement(
    database: Database,
) -> None:
    seed = await seed_application_key(
        database, audience=MCP_PROFILE.audience.value, adapters=(ApplicationKeyAdapter.MCP,)
    )
    auth = _authenticator(database)
    await _grant(database, await auth.authenticate(seed.credential), seed.account.project_id)
    messages: list[Message] = []

    async def operation(scope: Scope, receive: Receive, send: Send) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        async with database.session() as session, session.begin():
            await session.execute(
                update(ApplicationKeyRow)
                .where(ApplicationKeyRow.key_id == seed.credential.key_id.value)
                .values(revoked_at=func.clock_timestamp(type_=DateTime(timezone=True)))
            )
        await _authorize(
            database, MCPAccessContextMapper.from_scope(scope), seed.account.project_id, MCP_PROFILE
        )

    async def receive() -> Message:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: Message) -> None:
        messages.append(message)

    scope: Scope = {
        "type": "http",
        "method": "POST",
        "path": "/mcp/tools/query",
        "scheme": "https",
        "headers": [(b"authorization", ("Bearer " + seed.credential.value).encode())],
        "query_string": b"",
    }
    with pytest.raises(ApplicationKeyCredentialRejectedError):
        await RequestContextMiddleware(MCPApplicationKeyMiddleware(operation, authenticator=auth))(
            scope, receive, send
        )
    assert [message["type"] for message in messages] == ["http.response.start"]
