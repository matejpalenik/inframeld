"""Use production HTTP assembly with real keys and no human identity providers."""

import asyncio
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import patch
from uuid import UUID, uuid4

import httpx2
import pytest
from sqlalchemy import DateTime, Integer, String, column, func, select, table, update
from sqlalchemy.dialects.postgresql import ARRAY
from tests.support.access_group_scenarios import (
    change_group,
    create_group,
    group_fingerprints,
)
from tests.support.application_key_scenarios import ApplicationKeySeedDTO, seed_application_key

from inframeld_backend.access.application.commands.set_access_group_action_grant_command import (
    SetAccessGroupActionGrantCommand,
)
from inframeld_backend.access.application.dtos.application_key_verification_profile_dto import (
    ApplicationKeyVerificationProfileDTO,
)
from inframeld_backend.access.application.dtos.created_access_group_dto import CreatedAccessGroupDTO
from inframeld_backend.access.application.dtos.verified_application_key_dto import (
    VerifiedApplicationKeyDTO,
)
from inframeld_backend.access.application.enums.access_group_change_kind import (
    AccessGroupChangeKind,
)
from inframeld_backend.access.application.enums.access_group_collection import AccessGroupCollection
from inframeld_backend.access.application.errors.application_key_credential_rejected_error import (
    ApplicationKeyCredentialRejectedError,
)
from inframeld_backend.access.application.protocols.access_group_reader import AccessGroupReader
from inframeld_backend.access.application.queries.list_access_group_principals_query import (
    ListAccessGroupPrincipalsQuery,
)
from inframeld_backend.access.application.services.access_group_read_service import (
    AccessGroupReadService,
)
from inframeld_backend.access.application.services.application_authentication_service import (
    ApplicationAuthenticationService,
)
from inframeld_backend.access.application.value_objects.application_key_credential import (
    ApplicationKeyCredential,
)
from inframeld_backend.access.domain.enums.access_group_action import AccessGroupAction
from inframeld_backend.access.domain.enums.application_key_adapter import ApplicationKeyAdapter
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.application_key_audience import (
    ApplicationKeyAudience,
)
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.readers.postgres_access_group_facts_reader import (
    PostgresAccessGroupFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_application_authentication_facts_reader import (
    PostgresApplicationAuthenticationFactsReader,
)
from inframeld_backend.access.infrastructure.rows.access_group_row import AccessGroupRow
from inframeld_backend.access.infrastructure.rows.application_key_row import ApplicationKeyRow
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.access.infrastructure.settings.application_key_authentication_settings import (
    ApplicationKeyAuthenticationSettings,
)
from inframeld_backend.access.infrastructure.verifiers.postgres_application_key_verifier import (
    PostgresApplicationKeyVerifier,
)
from inframeld_backend.bootstrap.access_group_composition import open_access_group_read
from inframeld_backend.bootstrap.access_group_grant_composition import (
    open_access_group_grant_change,
)
from inframeld_backend.bootstrap.application_environment import ApplicationEnvironment
from inframeld_backend.bootstrap.application_factory import create_app
from inframeld_backend.bootstrap.application_settings import ApplicationSettings, get_settings
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.infrastructure.readers.postgres_installation_identity_reader import (
    PostgresInstallationIdentityReader,
)
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.resources.sqlalchemy_transaction_manager import (
    SqlAlchemyTransactionManager,
)
from inframeld_backend.shared.infrastructure.settings.database_settings import DatabaseSettings
from inframeld_backend.shared.infrastructure.settings.request_fingerprint_settings import (
    RequestFingerprintSettings,
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
        reason="Requires isolated PostgreSQL services",
    ),
]
AUDIENCE = "https://api.test"
PROFILE = ApplicationKeyVerificationProfileDTO(
    ApplicationKeyAudience(AUDIENCE), ApplicationKeyAdapter.HTTP
)


async def _group(
    database: Database, seed: ApplicationKeySeedDTO, *, visibility: str = "member"
) -> CreatedAccessGroupDTO:
    """Use delivered administration to give the application one permitted visibility route."""
    async with database.session() as session:
        revision = await session.scalar(
            select(ProjectRow.access_revision).where(ProjectRow.id == seed.account.project_id.value)
        )
    assert revision is not None
    group = (
        await create_group(
            database, seed.creator_access, seed.account.project_id, revision=revision
        )
    ).group
    if visibility == "member":
        await change_group(
            database,
            seed.creator_access,
            group,
            seed.account.principal_id,
            AccessGroupChangeKind.ADD_MEMBER,
            group.access_revision,
            "application-group-member",
        )
    elif visibility == "document-grant":
        action = ActionId(AccessGroupAction.ADD_DOCUMENTS.value)
        async with open_access_group_grant_change(database, group_fingerprints()) as changer:
            await changer.set_grant(
                access=seed.creator_access,
                command=SetAccessGroupActionGrantCommand(
                    project_id=group.project_id,
                    group_id=group.group_id,
                    recipient_principal_id=seed.account.principal_id,
                    action_id=action,
                    can_grant=False,
                    expected_access_revision=group.access_revision,
                ),
                context=IdempotencyContextDTO(
                    HttpMethod.PUT,
                    f"/v1/projects/{group.project_id.value}/access-groups/{group.group_id.value}/grants/{seed.account.principal_id.value}/{action.value}",
                    IdempotencyKey("application-group-document-use"),
                ),
            )
    else:
        assert visibility == "hidden"
    return group


def _group_path(project_id: ProjectId, group: CreatedAccessGroupDTO, selector: str) -> str:
    base = f"/v1/projects/{project_id.value}/access-groups"
    return (
        f"{base}/{group.group_id.value}"
        if selector == "id"
        else f"{base}/resolve?name={group.name.value}"
    )


async def _foreign_project(database: Database, seed: ApplicationKeySeedDTO) -> ProjectId:
    project_id = ProjectId(uuid4())
    async with database.session() as session, session.begin():
        session.add(
            ProjectRow(
                id=project_id.value,
                organization_id=seed.account.organization_id.value,
                name="Foreign Project",
                status=ProjectStatus.ACTIVE,
            )
        )
    return project_id


def _settings(
    postgres: DatabaseSettings, tmp_path: Path, *, audience: str | None = AUDIENCE
) -> ApplicationSettings:
    fingerprint = tmp_path / "fingerprint.key"
    with os.fdopen(os.open(fingerprint, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as key:
        key.write(b"K" * 32)
    return get_settings().model_copy(
        update={
            "environment": ApplicationEnvironment.TEST,
            "database": postgres,
            "request_fingerprint": RequestFingerprintSettings(key_file=fingerprint),
            "application_key_authentication": ApplicationKeyAuthenticationSettings(
                http_audience=audience
            ),
            "kratos": None,
            "hydra": None,
            "discovery": None,
        }
    )


@asynccontextmanager
async def _client(settings: ApplicationSettings) -> AsyncGenerator[httpx2.AsyncClient]:
    application = create_app(settings)
    async with (
        application.router.lifespan_context(application),
        httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=application), base_url=AUDIENCE
        ) as client,
    ):
        yield client


def _assert_safe(response: httpx2.Response, credential: ApplicationKeyCredential) -> None:
    assert response.headers["cache-control"] == "no-store"
    assert UUID(response.headers["x-request-id"])
    assert credential.value not in response.text


async def test_real_http_identity_metadata_and_human_only_boundaries_without_providers(
    database: Database, temporary_postgres_settings: DatabaseSettings, tmp_path: Path
) -> None:
    seed = await seed_application_key(database)
    headers = {"Authorization": "Bearer " + seed.credential.value}
    metadata_path = f"/v1/projects/{seed.account.project_id.value}/metadata"
    installed = await PostgresInstallationIdentityReader(database).read()
    async with _client(_settings(temporary_postgres_settings, tmp_path)) as client:
        identity = await client.get("/v1/application-session", headers=headers)
        metadata = await client.get(metadata_path, headers=headers)
        assert identity.status_code == metadata.status_code == 200
        assert identity.json() == {
            "principalId": str(seed.account.principal_id.value),
            "projectId": str(seed.account.project_id.value),
        }
        assert metadata.json()["projectId"] == str(seed.account.project_id.value)
        denied_change = await client.patch(
            metadata_path,
            headers=headers | {"Idempotency-Key": "app-cannot-edit-metadata"},
            json={"expectedMetadataRevision": 0, "displayName": "Forbidden replacement"},
        )
        assert denied_change.status_code == 403
        assert (await client.get(metadata_path, headers=headers)).json() == metadata.json()
        human_session = await client.get("/v1/session", headers=headers)
        lookup = await client.post(
            "/v1/operations/lookup",
            headers=headers,
            json={
                "installationId": str(installed.value),
                "organizationId": str(seed.account.organization_id.value),
                "projectId": str(seed.account.project_id.value),
                "method": "POST",
                "requestedRoute": "/test/projects/{project_id}/feedback-reports",
                "key": "original",
                "expectedAuthority": {
                    "family": "project_action_use",
                    "actionId": "inspect-feedback",
                },
            },
        )
        assert human_session.status_code == 401 and lookup.status_code == 403
    for response in [identity, metadata, denied_change, human_session, lookup]:
        _assert_safe(response, seed.credential)


@pytest.mark.parametrize("failure", ["revoked", "suspended", "missing-profile", "wrong-audience"])
async def test_real_http_key_rejection_local_denial_and_missing_profile_are_distinct(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
    tmp_path: Path,
    failure: str,
) -> None:
    seed = await seed_application_key(database)
    audience = (
        None
        if failure == "missing-profile"
        else "https://other.test"
        if failure == "wrong-audience"
        else AUDIENCE
    )
    if failure in {"revoked", "suspended"}:
        async with database.session() as session, session.begin():
            if failure == "revoked":
                await session.execute(
                    update(ApplicationKeyRow)
                    .where(ApplicationKeyRow.key_id == seed.credential.key_id.value)
                    .values(revoked_at=func.clock_timestamp(type_=DateTime(timezone=True)))
                )
            else:
                await session.execute(
                    update(PrincipalRow)
                    .where(PrincipalRow.id == seed.account.principal_id.value)
                    .values(status=PrincipalStatus.SUSPENDED)
                )
    async with _client(
        _settings(temporary_postgres_settings, tmp_path, audience=audience)
    ) as client:
        response = await client.get(
            "/v1/application-session", headers={"Authorization": "Bearer " + seed.credential.value}
        )
    status = 503 if failure == "missing-profile" else 403 if failure == "suspended" else 401
    assert response.status_code == status
    _assert_safe(response, seed.credential)
    if status == 401:
        assert (
            response.headers["www-authenticate"]
            == 'Bearer realm="inframeld", error="invalid_token"'
        )


@pytest.mark.parametrize("target", ["identity", "metadata", "group-id", "group-name"])
async def test_real_http_rechecks_revocation_after_full_verification_before_disclosure(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
    tmp_path: Path,
    target: str,
) -> None:
    seed = await seed_application_key(database)
    original_verify = PostgresApplicationKeyVerifier.verify
    observed_profiles: list[ApplicationKeyVerificationProfileDTO] = []

    async def verify_then_revoke(
        self: PostgresApplicationKeyVerifier,
        credential: ApplicationKeyCredential,
        *,
        profile: ApplicationKeyVerificationProfileDTO,
    ) -> VerifiedApplicationKeyDTO | None:
        verified = await original_verify(self, credential, profile=profile)
        assert verified is not None
        observed_profiles.append(profile)
        async with database.session() as session, session.begin():
            await session.execute(
                update(ApplicationKeyRow)
                .where(ApplicationKeyRow.key_id == credential.key_id.value)
                .values(revoked_at=func.clock_timestamp(type_=DateTime(timezone=True)))
            )
        return verified

    if target.startswith("group-"):
        group = await _group(database, seed)
        path = _group_path(seed.account.project_id, group, target.removeprefix("group-"))
    else:
        path = (
            "/v1/application-session"
            if target == "identity"
            else f"/v1/projects/{seed.account.project_id.value}/metadata"
        )
    with patch.object(PostgresApplicationKeyVerifier, "verify", verify_then_revoke):
        async with _client(_settings(temporary_postgres_settings, tmp_path)) as client:
            response = await client.get(
                path, headers={"Authorization": "Bearer " + seed.credential.value}
            )
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == 'Bearer realm="inframeld", error="invalid_token"'
    assert len(observed_profiles) == 1 and observed_profiles[0].audience == ApplicationKeyAudience(
        AUDIENCE
    )
    _assert_safe(response, seed.credential)


async def test_real_http_exclusive_identity_families_and_competing_headers(
    database: Database, temporary_postgres_settings: DatabaseSettings, tmp_path: Path
) -> None:
    seed = await seed_application_key(database)
    async with _client(_settings(temporary_postgres_settings, tmp_path)) as client:
        human_bearer = await client.get(
            "/v1/application-session", headers={"Authorization": "Bearer human-token"}
        )
        human_cookie = await client.get(
            "/v1/application-session", headers={"Cookie": "ory_kratos_session=human-cookie"}
        )
        competing = await client.get(
            "/v1/application-session",
            headers={
                "Authorization": "Bearer " + seed.credential.value,
                "Cookie": "ory_kratos_session=human-cookie",
            },
        )
    assert human_bearer.status_code == human_cookie.status_code == 401
    assert competing.status_code == 400
    for response in [human_bearer, human_cookie, competing]:
        _assert_safe(response, seed.credential)


@pytest.mark.parametrize("selector", ["id", "name"])
@pytest.mark.parametrize("visibility", ["member", "document-grant"])
async def test_real_http_application_group_metadata_uses_current_key_facts(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
    tmp_path: Path,
    selector: str,
    visibility: str,
) -> None:
    seed = await seed_application_key(database)
    group = await _group(database, seed, visibility=visibility)
    async with _client(_settings(temporary_postgres_settings, tmp_path)) as client:
        response = await client.get(
            _group_path(group.project_id, group, selector),
            headers={"Authorization": "Bearer " + seed.credential.value},
        )
    assert response.status_code == 200
    assert response.json()["accessGroupId"] == str(group.group_id.value)
    assert response.json()["projectId"] == str(group.project_id.value)
    assert response.json()["name"] == group.name.value
    assert response.json()["displayName"] == group.display_name
    assert set(response.json()) == {
        "projectId",
        "accessGroupId",
        "name",
        "displayName",
        "createdAt",
        "accessRevision",
    }
    _assert_safe(response, seed.credential)


@pytest.mark.parametrize("selector", ["id", "name"])
@pytest.mark.parametrize("hidden", ["no-relationship", "foreign-project"])
async def test_real_http_application_group_visibility_remains_hidden(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
    tmp_path: Path,
    selector: str,
    hidden: str,
) -> None:
    seed = await seed_application_key(database)
    group = await _group(
        database, seed, visibility="hidden" if hidden == "no-relationship" else "member"
    )
    project_id = (
        await _foreign_project(database, seed) if hidden == "foreign-project" else group.project_id
    )
    async with _client(_settings(temporary_postgres_settings, tmp_path)) as client:
        response = await client.get(
            _group_path(project_id, group, selector),
            headers={"Authorization": "Bearer " + seed.credential.value},
        )
    assert response.status_code == 404
    assert group.display_name not in response.text
    _assert_safe(response, seed.credential)


async def test_real_http_group_reader_requires_a_profile_separate_from_authentication(
    database: Database, temporary_postgres_settings: DatabaseSettings, tmp_path: Path
) -> None:
    seed = await seed_application_key(database)
    group = await _group(database, seed)

    @asynccontextmanager
    async def missing_reader_profile(
        database: Database,
        *,
        application_key_profile: ApplicationKeyVerificationProfileDTO | None = None,
    ) -> AsyncGenerator[AccessGroupReader]:
        """Keep full HTTP authentication configured and omit only the reader's profile."""
        del application_key_profile
        async with database.session() as session:
            yield AccessGroupReadService(
                SqlAlchemyTransactionManager(session), PostgresAccessGroupFactsReader(session)
            )

    with patch(
        "inframeld_backend.bootstrap.application_factory.open_access_group_read",
        missing_reader_profile,
    ):
        async with _client(_settings(temporary_postgres_settings, tmp_path)) as client:
            response = await client.get(
                _group_path(group.project_id, group, "id"),
                headers={"Authorization": "Bearer " + seed.credential.value},
            )
    assert response.status_code == 503
    assert group.display_name not in response.text
    _assert_safe(response, seed.credential)


async def test_real_group_reader_compares_its_explicit_mcp_profile_with_current_key(
    database: Database,
) -> None:
    seed = await seed_application_key(database)
    group = await _group(database, seed)
    access = await ApplicationAuthenticationService(
        key_verifier=PostgresApplicationKeyVerifier(database),
        authentication_facts_reader=PostgresApplicationAuthenticationFactsReader(database),
        verification_profile=PROFILE,
    ).authenticate(seed.credential)
    mcp_profile = ApplicationKeyVerificationProfileDTO(
        ApplicationKeyAudience("https://api.test/mcp"), ApplicationKeyAdapter.MCP
    )
    async with database.session() as session:
        reader = AccessGroupReadService(
            SqlAlchemyTransactionManager(session),
            PostgresAccessGroupFactsReader(session, application_key_profile=mcp_profile),
        )
        with pytest.raises(ApplicationKeyCredentialRejectedError):
            await reader.inspect(
                access=access, project_id=group.project_id, selector=group.group_id
            )


@pytest.mark.parametrize("operation", ["members", "managers", "add-member", "delete"])
async def test_real_http_application_group_administration_remains_human_only(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
    tmp_path: Path,
    operation: str,
) -> None:
    seed = await seed_application_key(database)
    group = await _group(database, seed)
    async with database.session() as session:
        revision = await session.scalar(
            select(ProjectRow.access_revision).where(ProjectRow.id == group.project_id.value)
        )
    assert revision is not None
    path = _group_path(group.project_id, group, "id")
    headers = {"Authorization": "Bearer " + seed.credential.value}
    async with _client(_settings(temporary_postgres_settings, tmp_path)) as client:
        if operation in {"members", "managers"}:
            response = await client.get(f"{path}/{operation}", headers=headers)
        elif operation == "add-member":
            response = await client.put(
                f"{path}/members/{seed.creator_access.actor_principal_id.value}",
                headers=headers | {"Idempotency-Key": "application-cannot-change-group"},
                json={"expectedAccessRevision": revision},
            )
        else:
            response = await client.delete(
                path,
                headers=headers | {"Idempotency-Key": "application-cannot-delete-group"},
                params={"expectedAccessRevision": revision},
            )
    assert response.status_code == 403
    _assert_safe(response, seed.credential)
    async with database.session() as session:
        assert await session.get(AccessGroupRow, group.group_id.value) is not None
        assert (
            await session.scalar(
                select(ProjectRow.access_revision).where(ProjectRow.id == group.project_id.value)
            )
            == revision
        )


async def test_real_group_human_manager_reads_keep_their_existing_profile_free_path(
    database: Database,
) -> None:
    seed = await seed_application_key(database)
    group = await _group(database, seed)
    async with open_access_group_read(database) as reader:
        by_id = await reader.inspect(
            access=seed.creator_access, project_id=group.project_id, selector=group.group_id
        )
        by_name = await reader.inspect(
            access=seed.creator_access, project_id=group.project_id, selector=group.name
        )
        members = await reader.list_principals(
            access=seed.creator_access,
            query=ListAccessGroupPrincipalsQuery(
                group.project_id, group.group_id, AccessGroupCollection.MEMBERS
            ),
        )
        managers = await reader.list_principals(
            access=seed.creator_access,
            query=ListAccessGroupPrincipalsQuery(
                group.project_id, group.group_id, AccessGroupCollection.MANAGERS
            ),
        )
    assert by_id == by_name
    assert {item.principal_id for item in members.items} == {
        seed.creator_access.actor_principal_id,
        seed.account.principal_id,
    }
    assert {item.principal_id for item in managers.items} == {
        seed.creator_access.actor_principal_id
    }


async def test_real_http_group_expiry_uses_database_time_after_ordinary_key_update_wait(
    database: Database, temporary_postgres_settings: DatabaseSettings, tmp_path: Path
) -> None:
    seed = await seed_application_key(database)
    group = await _group(database, seed)
    pid, name = column("pid", Integer), column("datname", String)
    activity = table("pg_stat_activity", pid, name)
    task: asyncio.Task[httpx2.Response] | None = None
    work_error: BaseException | None = None
    async with _client(_settings(temporary_postgres_settings, tmp_path)) as client:
        try:
            async with database.session() as holder, holder.begin():
                holder_pid = await holder.scalar(select(func.pg_backend_pid(type_=Integer)))
                assert holder_pid is not None
                await holder.execute(
                    update(ApplicationKeyRow)
                    .where(ApplicationKeyRow.key_id == seed.credential.key_id.value)
                    .values(audience=AUDIENCE)
                )
                task = asyncio.create_task(
                    client.get(
                        _group_path(group.project_id, group, "id"),
                        headers={"Authorization": "Bearer " + seed.credential.value},
                    )
                )
                blocked = None
                async with asyncio.timeout(3):
                    while not task.done():
                        async with database.session() as observer:
                            blocked = await observer.scalar(
                                select(pid)
                                .select_from(activity)
                                .where(
                                    name == func.current_database(type_=String()),
                                    func.pg_blocking_pids(pid, type_=ARRAY(Integer)).contains(
                                        [holder_pid]
                                    ),
                                )
                            )
                        if blocked is not None:
                            break
                        await asyncio.sleep(0.01)
                if blocked is None:
                    await task
                    pytest.fail("Group disclosure bypassed its ordinary current-key lock.")
                await holder.execute(
                    update(ApplicationKeyRow)
                    .where(ApplicationKeyRow.key_id == seed.credential.key_id.value)
                    .values(expires_at=func.clock_timestamp(type_=DateTime(timezone=True)))
                )
            response = await task
            assert response.status_code == 401
            assert response.headers["www-authenticate"] == (
                'Bearer realm="inframeld", error="invalid_token"'
            )
            assert group.display_name not in response.text
            _assert_safe(response, seed.credential)
        except BaseException as error:
            work_error = error
            raise
        finally:
            if task is not None:
                try:
                    async with asyncio.timeout(3):
                        if not task.done():
                            task.cancel()
                        outcome = (
                            await asyncio.shield(asyncio.gather(task, return_exceptions=True))
                        )[0]
                    if (
                        isinstance(outcome, BaseException)
                        and not isinstance(outcome, asyncio.CancelledError)
                        and outcome is not work_error
                    ):
                        raise outcome
                except BaseException as cleanup_error:
                    if work_error is not None and cleanup_error is not work_error:
                        raise BaseExceptionGroup(
                            "Group disclosure and request cleanup failed",
                            [work_error, cleanup_error],
                        ) from None
                    raise


async def test_foreign_group_target_does_not_lock_the_application_bound_project(
    database: Database,
) -> None:
    seed = await seed_application_key(database)
    group = await _group(database, seed)
    foreign = await _foreign_project(database, seed)
    access = await ApplicationAuthenticationService(
        key_verifier=PostgresApplicationKeyVerifier(database),
        authentication_facts_reader=PostgresApplicationAuthenticationFactsReader(database),
        verification_profile=PROFILE,
    ).authenticate(seed.credential)
    pid, name = column("pid", Integer), column("datname", String)
    activity = table("pg_stat_activity", pid, name)
    async with database.session() as holder, holder.begin():
        holder_pid = await holder.scalar(select(func.pg_backend_pid(type_=Integer)))
        assert holder_pid is not None
        await holder.scalar(
            select(ProjectRow.id).where(ProjectRow.id == group.project_id.value).with_for_update()
        )
        async with database.session() as caller, caller.begin():
            await caller.scalar(
                select(OrganizationRow.id)
                .where(OrganizationRow.id == seed.account.organization_id.value)
                .with_for_update(read=True)
            )
            await caller.scalar(
                select(ProjectRow.id).where(ProjectRow.id == foreign.value).with_for_update()
            )
            task = asyncio.create_task(
                PostgresAccessGroupFactsReader(caller, application_key_profile=PROFILE).read(
                    access=access, project_id=foreign, selector=group.group_id
                )
            )
            work_error: BaseException | None = None
            try:
                async with asyncio.timeout(3):
                    while not task.done():
                        async with database.session() as observer:
                            blocked = await observer.scalar(
                                select(pid)
                                .select_from(activity)
                                .where(
                                    name == func.current_database(type_=String()),
                                    func.pg_blocking_pids(pid, type_=ARRAY(Integer)).contains(
                                        [holder_pid]
                                    ),
                                )
                            )
                        assert blocked is None, (
                            "Foreign group target tried to lock the application's bound Project."
                        )
                        await asyncio.sleep(0.01)
                assert await task is None
            except BaseException as error:
                work_error = error
                raise
            finally:
                try:
                    async with asyncio.timeout(3):
                        if not task.done():
                            task.cancel()
                        outcome = (
                            await asyncio.shield(asyncio.gather(task, return_exceptions=True))
                        )[0]
                    if (
                        isinstance(outcome, BaseException)
                        and not isinstance(outcome, asyncio.CancelledError)
                        and outcome is not work_error
                    ):
                        raise outcome
                except BaseException as cleanup_error:
                    if work_error is not None and cleanup_error is not work_error:
                        raise BaseExceptionGroup(
                            "Foreign group read and task cleanup failed",
                            [work_error, cleanup_error],
                        ) from None
                    raise
