"""Qualify registered HTTP operations with real Access state and controlled provider proofs."""

import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from uuid import UUID, uuid4

import httpx2
import pytest
from pydantic import HttpUrl
from sqlalchemy import DateTime, delete, func, update
from tests.integration.access.test_application_key_issuance_http_postgres import (
    BEARER,
    COOKIE,
    ControlledBrowserProof,
    ControlledIdentityProof,
    ControlledTokenProof,
)
from tests.support.access_group_scenarios import create_group
from tests.support.application_account_scenarios import create_account
from tests.support.application_key_scenarios import store_application_key
from tests.support.project_creation_scenarios import create_project
from tests.support.project_upload_default_scenarios import (
    replace_upload_default,
    seed_upload_default_scenario,
    upload_default_effects,
)

from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
    HumanOAuthCredentialBindingDTO,
)
from inframeld_backend.access.application.services.human_access_token_authentication_service import (
    HumanAccessTokenAuthenticationService,
)
from inframeld_backend.access.application.services.human_session_authentication_service import (
    HumanSessionAuthenticationService,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.project_action import ProjectAction
from inframeld_backend.access.infrastructure.readers.postgres_human_credential_state_reader import (
    PostgresHumanCredentialStateReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_human_identity_link_reader import (
    PostgresHumanIdentityLinkReader,
)
from inframeld_backend.access.infrastructure.rows.application_key_row import ApplicationKeyRow
from inframeld_backend.access.infrastructure.rows.group_action_grant_row import GroupActionGrantRow
from inframeld_backend.access.infrastructure.rows.group_manager_row import GroupManagerRow
from inframeld_backend.access.infrastructure.rows.group_membership_row import GroupMembershipRow
from inframeld_backend.access.infrastructure.rows.human_credential_version_row import (
    HumanCredentialVersionRow,
)
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.settings.application_key_authentication_settings import (
    ApplicationKeyAuthenticationSettings,
)
from inframeld_backend.access.infrastructure.settings.application_key_issuance_settings import (
    ApplicationKeyIssuanceSettings,
)
from inframeld_backend.access.infrastructure.settings.csrf_settings import CSRFSettings
from inframeld_backend.access.infrastructure.settings.human_authentication_settings import (
    HumanAuthenticationSettings,
)
from inframeld_backend.access.infrastructure.settings.hydra_settings import HydraSettings
from inframeld_backend.access.infrastructure.settings.kratos_settings import KratosSettings
from inframeld_backend.bootstrap.access_components import AccessComponents
from inframeld_backend.bootstrap.access_composition import create_access_components
from inframeld_backend.bootstrap.application_environment import ApplicationEnvironment
from inframeld_backend.bootstrap.application_factory import create_app
from inframeld_backend.bootstrap.application_settings import ApplicationSettings, get_settings
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.settings.database_settings import DatabaseSettings
from inframeld_backend.shared.infrastructure.settings.request_fingerprint_settings import (
    RequestFingerprintSettings,
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
        reason="Requires isolated PostgreSQL integration services",
    ),
]


HTTP_AUDIENCE, MCP_AUDIENCE = "https://api.test", "https://mcp.test/mcp"


def _settings(
    postgres: DatabaseSettings,
    tmp_path: Path,
    *,
    http: str | None = HTTP_AUDIENCE,
    mcp: str | None = MCP_AUDIENCE,
) -> ApplicationSettings:
    fingerprint = tmp_path / "fingerprint.key"
    with os.fdopen(os.open(fingerprint, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as key:
        key.write(b"K" * 32)
    return get_settings().model_copy(
        update={
            "environment": ApplicationEnvironment.TEST,
            "database": postgres,
            "request_fingerprint": RequestFingerprintSettings(key_file=fingerprint),
            "kratos": None,
            "hydra": None,
            "discovery": None,
            "csrf": CSRFSettings(trusted_origins=(HttpUrl("https://account.test"),)),
            "application_key_authentication": ApplicationKeyAuthenticationSettings(
                http_audience=http, mcp_audience=mcp
            ),
            "application_key_issuance": ApplicationKeyIssuanceSettings(
                default_lifetime_seconds=60, maximum_lifetime_seconds=120
            ),
        }
    )


@asynccontextmanager
async def _client(
    settings: ApplicationSettings,
    binding: HumanOAuthCredentialBindingDTO,
    *,
    raise_app_exceptions: bool = True,
) -> AsyncGenerator[httpx2.AsyncClient]:
    def assemble(
        kratos_settings: KratosSettings | None,
        hydra_settings: HydraSettings | None,
        database: Database,
        *,
        human_authentication_settings: HumanAuthenticationSettings,
        application_key_authentication_settings: ApplicationKeyAuthenticationSettings | None = None,
    ) -> AccessComponents:
        """Replace provider proofs only, preserving production current admission and key adapters."""
        access = create_access_components(
            kratos_settings,
            hydra_settings,
            database,
            human_authentication_settings=human_authentication_settings,
            application_key_authentication_settings=application_key_authentication_settings,
        )
        links = PostgresHumanIdentityLinkReader(database)
        browser = HumanSessionAuthenticationService(
            ControlledBrowserProof(binding),
            PostgresHumanCredentialStateReader(database),
            provider_timeout_seconds=human_authentication_settings.provider_timeout_seconds,
            total_timeout_seconds=human_authentication_settings.total_timeout_seconds,
        )
        bearer = HumanAccessTokenAuthenticationService(
            ControlledTokenProof(binding),
            ControlledIdentityProof(binding),
            links,
            credential_state_reader=PostgresHumanCredentialStateReader(database),
            provider_timeout_seconds=human_authentication_settings.provider_timeout_seconds,
            total_timeout_seconds=human_authentication_settings.total_timeout_seconds,
        )
        return replace(access, authenticator=browser, access_token_authenticator=bearer)

    with patch(
        "inframeld_backend.bootstrap.application_factory.create_access_components", assemble
    ):
        app = create_app(settings)
    async with (
        app.router.lifespan_context(app),
        httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app, raise_app_exceptions=raise_app_exceptions),
            base_url=HTTP_AUDIENCE,
        ) as client,
    ):
        yield client


@pytest.mark.parametrize("family", ["cookie", "bearer"])
async def test_registered_defaults_keep_current_read_original_replay_and_revision_checked_noop(
    database: Database, temporary_postgres_settings: DatabaseSettings, tmp_path: Path, family: str
) -> None:
    scope = await seed_upload_default_scenario(database)
    route = f"/v1/projects/{scope.project_id.value}/upload-defaults"
    groups = [str(group.group_id.value) for group in scope.groups]
    # The actor keeps only the exact action, without delegation or unrelated Project grants.
    async with database.session() as session, session.begin():
        await session.execute(
            delete(ProjectActionGrantRow).where(
                ProjectActionGrantRow.project_id == scope.project_id.value,
                ProjectActionGrantRow.recipient_principal_id
                == scope.actor.access.actor_principal_id.value,
                ProjectActionGrantRow.action != ProjectAction.MANAGE_UPLOAD_DEFAULTS,
            )
        )
        await session.execute(
            update(ProjectActionGrantRow)
            .where(
                ProjectActionGrantRow.project_id == scope.project_id.value,
                ProjectActionGrantRow.recipient_principal_id
                == scope.actor.access.actor_principal_id.value,
            )
            .values(can_grant=False)
        )
    headers = COOKIE if family == "cookie" else BEARER
    async with _client(
        _settings(temporary_postgres_settings, tmp_path), scope.actor.binding
    ) as client:
        unset = await client.get(route, headers=headers)
        assert unset.status_code == 200 and unset.json() == {
            "projectId": str(scope.project_id.value),
            "groupIds": None,
            "accessRevision": scope.revision,
        }
        a = await client.put(
            route,
            json={"groupIds": [groups[0]], "expectedAccessRevision": scope.revision},
            headers=headers | {"Idempotency-Key": "initial-a"},
        )
        assert a.status_code == 200
        original_body = {
            "groupIds": [groups[1]],
            "expectedAccessRevision": a.json()["accessRevision"],
        }
        original_headers = headers | {"Idempotency-Key": "original-b"}
        b = await client.put(route, json=original_body, headers=original_headers)
        assert b.status_code == 200
        c = await client.put(
            route,
            json={"groupIds": [groups[2]], "expectedAccessRevision": b.json()["accessRevision"]},
            headers=headers | {"Idempotency-Key": "later-c"},
        )
        assert c.status_code == 200
        replay = await client.put(route, json=original_body, headers=original_headers)
        current = await client.get(route, headers=headers)
        assert replay.status_code == current.status_code == 200 and replay.json() == b.json()
        assert current.json()["groupIds"] == [groups[2]] and replay.json()["groupIds"] == [
            groups[1]
        ]
        assert set(replay.json()) == {
            "projectId",
            "groupIds",
            "accessRevision",
            "operationId",
            "idempotencyExpiresAt",
        }
        assert groups[0] not in replay.text and "beforeGroupIds" not in replay.json()
        before = await upload_default_effects(database, scope.project_id)
        stale = await client.put(
            route,
            json={"groupIds": [groups[2]], "expectedAccessRevision": b.json()["accessRevision"]},
            headers=headers | {"Idempotency-Key": "fresh-stale"},
        )
        assert stale.status_code == 409 and stale.json()["code"] == "stale_revision"
        assert await upload_default_effects(database, scope.project_id) == before
        noop = await client.put(
            route,
            json={
                "groupIds": [groups[2]],
                "expectedAccessRevision": current.json()["accessRevision"],
            },
            headers=headers | {"Idempotency-Key": "fresh-noop"},
        )
        assert (
            noop.status_code == 200
            and noop.json()["accessRevision"] == current.json()["accessRevision"]
        )
        after = await upload_default_effects(database, scope.project_id)
        assert after[:3] == before[:3] and after[3:] == (before[3] + 1, before[4] + 1)
        for response in (unset, a, b, c, replay, current, stale, noop):
            assert response.headers["cache-control"] == "no-store" and UUID(
                response.headers["x-request-id"]
            )


@pytest.mark.parametrize("loss", ["old", "new", "retained"])
async def test_registered_change_requires_management_of_every_old_new_and_retained_group(
    database: Database, temporary_postgres_settings: DatabaseSettings, tmp_path: Path, loss: str
) -> None:
    scope = await seed_upload_default_scenario(database)
    initial = await replace_upload_default(database, scope, (0,), scope.revision, "seed-a")
    index = 1 if loss == "new" else 0
    target = scope.groups[index].group_id.value
    async with database.session() as session, session.begin():
        session.add(
            GroupMembershipRow(
                project_id=scope.project_id.value, group_id=target, principal_id=scope.bob_id.value
            )
        )
        await session.flush()
        session.add(
            GroupManagerRow(
                project_id=scope.project_id.value,
                group_id=target,
                principal_id=scope.bob_id.value,
                principal_kind=PrincipalKind.HUMAN,
            )
        )
        await session.flush()
        await session.execute(
            delete(GroupManagerRow).where(
                GroupManagerRow.project_id == scope.project_id.value,
                GroupManagerRow.group_id == target,
                GroupManagerRow.principal_id == scope.actor.access.actor_principal_id.value,
            )
        )
    before = await upload_default_effects(database, scope.project_id)
    selected = (0, 1) if loss == "retained" else (1,)
    async with _client(
        _settings(temporary_postgres_settings, tmp_path), scope.actor.binding
    ) as client:
        response = await client.put(
            f"/v1/projects/{scope.project_id.value}/upload-defaults",
            json={
                "groupIds": [str(scope.groups[i].group_id.value) for i in selected],
                "expectedAccessRevision": initial.default.access_revision,
            },
            headers=BEARER | {"Idempotency-Key": "must-deny"},
        )
    assert response.status_code == 403 and response.json()["code"] == "access_denied"
    assert await upload_default_effects(database, scope.project_id) == before


@pytest.mark.parametrize("foreign", [False, True], ids=["missing-group", "foreign-project-group"])
async def test_registered_change_hides_missing_or_foreign_group_scope(
    database: Database, temporary_postgres_settings: DatabaseSettings, tmp_path: Path, foreign: bool
) -> None:
    scope = await seed_upload_default_scenario(database)
    group = uuid4()
    if foreign:
        async with database.session() as session:
            organization = await session.get(OrganizationRow, scope.actor.organization_id.value)
            assert organization is not None
            actor = replace(scope.actor, access_revision=organization.access_revision)
        project = (
            await create_project(
                database, actor, name="other-upload-project", key="other-upload-project"
            )
        ).project
        group = (
            await create_group(
                database,
                scope.actor.access,
                project.project_id,
                project.access_revision,
                name="foreign-upload",
                key="foreign-upload",
            )
        ).group.group_id.value
    before = await upload_default_effects(database, scope.project_id)
    async with _client(
        _settings(temporary_postgres_settings, tmp_path), scope.actor.binding
    ) as client:
        response = await client.put(
            f"/v1/projects/{scope.project_id.value}/upload-defaults",
            json={"groupIds": [str(group)], "expectedAccessRevision": scope.revision},
            headers=BEARER | {"Idempotency-Key": "foreign-default"},
        )
    assert response.status_code == 404 and response.json()["code"] == "resource_not_found"
    assert str(group) not in response.text
    assert await upload_default_effects(database, scope.project_id) == before


@pytest.mark.parametrize("failure", ["csrf", "origin", "body"])
async def test_registered_http_guards_reject_without_any_database_effect(
    database: Database, temporary_postgres_settings: DatabaseSettings, tmp_path: Path, failure: str
) -> None:
    scope = await seed_upload_default_scenario(database)
    headers = COOKIE | {"Idempotency-Key": "invalid-write"}
    body = {
        "groupIds": [str(scope.groups[0].group_id.value)],
        "expectedAccessRevision": scope.revision,
    }
    if failure == "csrf":
        headers = {k: v for k, v in headers.items() if k != "X-Inframeld-CSRF"}
    elif failure == "origin":
        headers = headers | {"Origin": "https://foreign.test"}
    else:
        body["groupIds"] = []
    before = await upload_default_effects(database, scope.project_id)
    async with _client(
        _settings(temporary_postgres_settings, tmp_path), scope.actor.binding
    ) as client:
        response = await client.put(
            f"/v1/projects/{scope.project_id.value}/upload-defaults", json=body, headers=headers
        )
    assert response.status_code == (422 if failure == "body" else 403)
    assert response.headers["cache-control"] == "no-store"
    assert await upload_default_effects(database, scope.project_id) == before


async def test_registered_current_action_loss_denies_original_recovery_without_regrant(
    database: Database, temporary_postgres_settings: DatabaseSettings, tmp_path: Path
) -> None:
    scope = await seed_upload_default_scenario(database)
    route = f"/v1/projects/{scope.project_id.value}/upload-defaults"
    body = {
        "groupIds": [str(scope.groups[0].group_id.value)],
        "expectedAccessRevision": scope.revision,
    }
    headers = BEARER | {"Idempotency-Key": "authority-original"}
    async with _client(
        _settings(temporary_postgres_settings, tmp_path), scope.actor.binding
    ) as client:
        first = await client.put(route, json=body, headers=headers)
        assert first.status_code == 200
        before = await upload_default_effects(database, scope.project_id)
        async with database.session() as session, session.begin():
            await session.execute(
                delete(ProjectActionGrantRow).where(
                    ProjectActionGrantRow.project_id == scope.project_id.value,
                    ProjectActionGrantRow.recipient_principal_id
                    == scope.actor.access.actor_principal_id.value,
                    ProjectActionGrantRow.action == ProjectAction.MANAGE_UPLOAD_DEFAULTS,
                )
            )
        replay = await client.put(route, json=body, headers=headers)
        read = await client.get(route, headers=BEARER)
    assert replay.status_code == read.status_code == 403
    assert await upload_default_effects(database, scope.project_id) == before


async def test_registered_bearer_rechecks_current_credential_before_original(
    database: Database, temporary_postgres_settings: DatabaseSettings, tmp_path: Path
) -> None:
    scope = await seed_upload_default_scenario(database)
    route = f"/v1/projects/{scope.project_id.value}/upload-defaults"
    body = {
        "groupIds": [str(scope.groups[0].group_id.value)],
        "expectedAccessRevision": scope.revision,
    }
    headers = BEARER | {"Idempotency-Key": "credential-original"}
    async with _client(
        _settings(temporary_postgres_settings, tmp_path), scope.actor.binding
    ) as client:
        first = await client.put(route, json=body, headers=headers)
        assert first.status_code == 200
        before = await upload_default_effects(database, scope.project_id)
        async with database.session() as session, session.begin():
            await session.execute(
                update(HumanCredentialVersionRow)
                .where(
                    HumanCredentialVersionRow.installation_id
                    == scope.actor.binding.installation_id.value,
                    HumanCredentialVersionRow.authority
                    == scope.actor.binding.identity.authority.value,
                    HumanCredentialVersionRow.subject == scope.actor.binding.identity.subject.value,
                )
                .values(version=scope.actor.binding.version.value + 1)
            )
        replay = await client.put(route, json=body, headers=headers)
    assert replay.status_code == 401 and "invalid_token" in replay.headers["www-authenticate"]
    assert await upload_default_effects(database, scope.project_id) == before


async def test_registered_application_is_denied_and_revoked_key_stays_unauthorized(
    database: Database, temporary_postgres_settings: DatabaseSettings, tmp_path: Path
) -> None:
    scope = await seed_upload_default_scenario(database)
    account = (
        await create_account(
            database, scope.actor.access, scope.project_id, revision=scope.revision
        )
    ).account
    key = await store_application_key(
        database,
        principal_id=account.principal_id,
        organization_id=scope.actor.organization_id,
        project_id=scope.project_id,
    )
    route = f"/v1/projects/{scope.project_id.value}/upload-defaults"
    async with _client(
        _settings(temporary_postgres_settings, tmp_path), scope.actor.binding
    ) as client:
        before = await upload_default_effects(database, scope.project_id)
        for method in ("GET", "PUT"):
            response = await client.request(
                method,
                route,
                json={
                    "groupIds": [str(scope.groups[0].group_id.value)],
                    "expectedAccessRevision": before[1],
                }
                if method == "PUT"
                else None,
                headers={
                    "Authorization": "Bearer " + key.value,
                    "Idempotency-Key": "application-denied",
                },
            )
            assert response.status_code == 403 and key.value not in response.text
        async with database.session() as session, session.begin():
            await session.execute(
                update(ApplicationKeyRow)
                .where(ApplicationKeyRow.key_id == key.key_id.value)
                .values(revoked_at=func.clock_timestamp(type_=DateTime(timezone=True)))
            )
        rejected = await client.get(route, headers={"Authorization": "Bearer " + key.value})
    assert rejected.status_code == 401 and "invalid_token" in rejected.headers["www-authenticate"]
    assert await upload_default_effects(database, scope.project_id) == before


@pytest.mark.parametrize("replay", [False, True])
@pytest.mark.parametrize(
    ("visibility", "expected_status", "expected_code"),
    [
        ("hidden", 404, "resource_not_found"),
        ("member", 403, "access_denied"),
        ("action", 403, "access_denied"),
    ],
)
async def test_registered_proposed_visibility_is_checked_before_fresh_or_original_work(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
    tmp_path: Path,
    replay: bool,
    visibility: str,
    expected_status: int,
    expected_code: str,
) -> None:
    scope = await seed_upload_default_scenario(database)
    initial = await replace_upload_default(database, scope, (0,), scope.revision, "privacy-seed")
    reviewed = initial.default.access_revision
    key = "privacy-original" if replay else "privacy-fresh"
    if replay:
        original = await replace_upload_default(database, scope, (1,), reviewed, key)
        await replace_upload_default(
            database, scope, (2,), original.default.access_revision, "privacy-later"
        )
    target = scope.groups[1].group_id.value
    actor = scope.actor.access.actor_principal_id.value
    async with database.session() as session, session.begin():
        session.add(
            GroupMembershipRow(
                project_id=scope.project_id.value,
                group_id=target,
                principal_id=scope.bob_id.value,
            )
        )
        await session.flush()
        session.add(
            GroupManagerRow(
                project_id=scope.project_id.value,
                group_id=target,
                principal_id=scope.bob_id.value,
                principal_kind=PrincipalKind.HUMAN,
            )
        )
        await session.flush()
        await session.execute(
            delete(GroupActionGrantRow).where(
                GroupActionGrantRow.project_id == scope.project_id.value,
                GroupActionGrantRow.group_id == target,
                GroupActionGrantRow.recipient_principal_id == actor,
            )
        )
        await session.execute(
            delete(GroupManagerRow).where(
                GroupManagerRow.project_id == scope.project_id.value,
                GroupManagerRow.group_id == target,
                GroupManagerRow.principal_id == actor,
            )
        )
        if visibility != "member":
            await session.execute(
                delete(GroupMembershipRow).where(
                    GroupMembershipRow.project_id == scope.project_id.value,
                    GroupMembershipRow.group_id == target,
                    GroupMembershipRow.principal_id == actor,
                )
            )
        if visibility == "action":
            session.add(
                GroupActionGrantRow(
                    project_id=scope.project_id.value,
                    group_id=target,
                    recipient_principal_id=actor,
                    recipient_kind=PrincipalKind.HUMAN,
                    action="add-documents",
                    can_grant=False,
                )
            )
    before = await upload_default_effects(database, scope.project_id)
    async with _client(
        _settings(temporary_postgres_settings, tmp_path), scope.actor.binding
    ) as client:
        response = await client.put(
            f"/v1/projects/{scope.project_id.value}/upload-defaults",
            json={"groupIds": [str(target)], "expectedAccessRevision": reviewed},
            headers=BEARER | {"Idempotency-Key": key},
        )
    assert response.status_code == expected_status and response.json()["code"] == expected_code
    assert str(target) not in response.text
    assert await upload_default_effects(database, scope.project_id) == before


@pytest.mark.parametrize("hidden_lower", [False, True])
async def test_registered_hidden_proposal_wins_over_visible_management_denial_in_both_uuid_orders(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
    tmp_path: Path,
    hidden_lower: bool,
) -> None:
    scope = await seed_upload_default_scenario(database)
    initial = await replace_upload_default(database, scope, (0,), scope.revision, "mixed-seed")
    pair = sorted(scope.groups[1:], key=lambda group: group.group_id.value)
    hidden, visible = pair if hidden_lower else tuple(reversed(pair))
    actor = scope.actor.access.actor_principal_id.value
    async with database.session() as session, session.begin():
        for group in pair:
            session.add(
                GroupMembershipRow(
                    project_id=scope.project_id.value,
                    group_id=group.group_id.value,
                    principal_id=scope.bob_id.value,
                )
            )
        await session.flush()
        for group in pair:
            session.add(
                GroupManagerRow(
                    project_id=scope.project_id.value,
                    group_id=group.group_id.value,
                    principal_id=scope.bob_id.value,
                    principal_kind=PrincipalKind.HUMAN,
                )
            )
        await session.flush()
        await session.execute(
            delete(GroupActionGrantRow).where(
                GroupActionGrantRow.project_id == scope.project_id.value,
                GroupActionGrantRow.group_id.in_([group.group_id.value for group in pair]),
                GroupActionGrantRow.recipient_principal_id == actor,
            )
        )
        await session.execute(
            delete(GroupManagerRow).where(
                GroupManagerRow.project_id == scope.project_id.value,
                GroupManagerRow.group_id.in_([group.group_id.value for group in pair]),
                GroupManagerRow.principal_id == actor,
            )
        )
        await session.execute(
            delete(GroupMembershipRow).where(
                GroupMembershipRow.project_id == scope.project_id.value,
                GroupMembershipRow.group_id == hidden.group_id.value,
                GroupMembershipRow.principal_id == actor,
            )
        )
    before = await upload_default_effects(database, scope.project_id)
    async with _client(
        _settings(temporary_postgres_settings, tmp_path), scope.actor.binding
    ) as client:
        response = await client.put(
            f"/v1/projects/{scope.project_id.value}/upload-defaults",
            json={
                "groupIds": [str(hidden.group_id.value), str(visible.group_id.value)],
                "expectedAccessRevision": initial.default.access_revision,
            },
            headers=BEARER | {"Idempotency-Key": "mixed-proposals"},
        )
    assert response.status_code == 404 and response.json()["code"] == "resource_not_found"
    assert all(str(group.group_id.value) not in response.text for group in pair)
    assert await upload_default_effects(database, scope.project_id) == before


async def test_registered_current_audience_denial_precedes_a_missing_proposal(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
    tmp_path: Path,
) -> None:
    scope = await seed_upload_default_scenario(database)
    initial = await replace_upload_default(database, scope, (0,), scope.revision, "current-seed")
    target = scope.groups[0].group_id.value
    async with database.session() as session, session.begin():
        session.add(
            GroupMembershipRow(
                project_id=scope.project_id.value,
                group_id=target,
                principal_id=scope.bob_id.value,
            )
        )
        await session.flush()
        session.add(
            GroupManagerRow(
                project_id=scope.project_id.value,
                group_id=target,
                principal_id=scope.bob_id.value,
                principal_kind=PrincipalKind.HUMAN,
            )
        )
        await session.flush()
        await session.execute(
            delete(GroupManagerRow).where(
                GroupManagerRow.project_id == scope.project_id.value,
                GroupManagerRow.group_id == target,
                GroupManagerRow.principal_id == scope.actor.access.actor_principal_id.value,
            )
        )
    before = await upload_default_effects(database, scope.project_id)
    async with _client(
        _settings(temporary_postgres_settings, tmp_path), scope.actor.binding
    ) as client:
        response = await client.put(
            f"/v1/projects/{scope.project_id.value}/upload-defaults",
            json={
                "groupIds": [str(UUID(int=1))],
                "expectedAccessRevision": initial.default.access_revision,
            },
            headers=BEARER | {"Idempotency-Key": "current-before-proposal"},
        )
    assert response.status_code == 403 and response.json()["code"] == "access_denied"
    assert await upload_default_effects(database, scope.project_id) == before
