"""Verify complete persisted keys and separately admit their real Project-bound account."""

import asyncio
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import replace
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy import DateTime, Integer, String, column, delete, func, select, table, update
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import AsyncSession
from tests.support.application_account_scenarios import create_account
from tests.support.application_key_scenarios import seed_application_key

from inframeld_backend.access.application.dtos.application_key_authentication_dto import (
    ApplicationKeyAuthenticationDTO,
)
from inframeld_backend.access.application.dtos.application_key_verification_profile_dto import (
    ApplicationKeyVerificationProfileDTO,
)
from inframeld_backend.access.application.dtos.current_application_session_dto import (
    CurrentApplicationSessionDTO,
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
from inframeld_backend.access.application.services.application_session_service import (
    ApplicationSessionService,
)
from inframeld_backend.access.domain.enums.application_key_adapter import ApplicationKeyAdapter
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.enums.project_action import ProjectAction
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.application_key_audience import (
    ApplicationKeyAudience,
)
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.readers.postgres_application_authentication_facts_reader import (
    PostgresApplicationAuthenticationFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_project_action_facts_reader import (
    PostgresProjectActionFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_project_metadata_facts_reader import (
    PostgresProjectMetadataFactsReader,
)
from inframeld_backend.access.infrastructure.rows.application_key_row import ApplicationKeyRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.project_membership_row import ProjectMembershipRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.access.infrastructure.verifiers.postgres_application_key_verifier import (
    PostgresApplicationKeyVerifier,
)
from inframeld_backend.shared.application.errors.application_errors import AccessDeniedError
from inframeld_backend.shared.infrastructure.resources.database import Database

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
        reason="Requires isolated PostgreSQL integration services",
    ),
]
PROFILE = ApplicationKeyVerificationProfileDTO(
    ApplicationKeyAudience("https://api.test"), ApplicationKeyAdapter.HTTP
)


async def test_real_complete_key_uses_its_stored_verifier_and_exact_profile(
    database: Database,
) -> None:
    seed = await seed_application_key(database)
    verifier = PostgresApplicationKeyVerifier(database)
    verified = await verifier.verify(seed.credential, profile=PROFILE)
    assert verified is not None
    assert verified.key_id == seed.credential.key_id
    assert verified.principal_id == seed.account.principal_id
    assert (
        await verifier.verify(
            seed.credential, profile=replace(PROFILE, adapter=ApplicationKeyAdapter.MCP)
        )
        is None
    )
    assert (
        await verifier.verify(
            seed.credential,
            profile=replace(PROFILE, audience=ApplicationKeyAudience("https://other.test")),
        )
        is None
    )

    async with database.session() as session, session.begin():
        await session.execute(
            update(ApplicationKeyRow)
            .where(ApplicationKeyRow.key_id == seed.credential.key_id.value)
            .values(revoked_at=func.clock_timestamp(type_=DateTime(timezone=True)))
        )
    assert await verifier.verify(seed.credential, profile=PROFILE) is None


async def test_verified_key_is_separately_admitted_and_local_suspension_is_403(
    database: Database,
) -> None:
    seed = await seed_application_key(database)
    service = ApplicationAuthenticationService(
        key_verifier=PostgresApplicationKeyVerifier(database),
        authentication_facts_reader=PostgresApplicationAuthenticationFactsReader(database),
        verification_profile=PROFILE,
    )
    access = await service.authenticate(seed.credential)
    assert access.actor_principal_id == seed.account.principal_id
    assert access.authentication_evidence == ApplicationKeyAuthenticationDTO(seed.credential.key_id)
    assert seed.credential.value not in repr(access)

    async with database.session() as session, session.begin():
        await session.execute(
            update(PrincipalRow)
            .where(PrincipalRow.id == seed.account.principal_id.value)
            .values(status=PrincipalStatus.SUSPENDED)
        )
    with pytest.raises(AccessDeniedError):
        await service.authenticate(seed.credential)


@pytest.mark.parametrize("remove_membership", [True, False], ids=["membership", "project"])
async def test_verified_key_needs_current_project_membership_and_active_project(
    database: Database, remove_membership: bool
) -> None:
    seed = await seed_application_key(database)
    async with database.session() as session, session.begin():
        if remove_membership:
            await session.execute(
                delete(ProjectMembershipRow).where(
                    ProjectMembershipRow.project_id == seed.account.project_id.value,
                    ProjectMembershipRow.principal_id == seed.account.principal_id.value,
                )
            )
        else:
            await session.execute(
                update(ProjectRow)
                .where(ProjectRow.id == seed.account.project_id.value)
                .values(status=ProjectStatus.DELETING)
            )
    service = ApplicationAuthenticationService(
        key_verifier=PostgresApplicationKeyVerifier(database),
        authentication_facts_reader=PostgresApplicationAuthenticationFactsReader(database),
        verification_profile=PROFILE,
    )
    with pytest.raises(AccessDeniedError):
        await service.authenticate(seed.credential)


async def test_application_session_rechecks_persisted_key_before_disclosure(
    database: Database,
) -> None:
    seed = await seed_application_key(database)
    reader = PostgresApplicationAuthenticationFactsReader(database)
    access = await ApplicationAuthenticationService(
        key_verifier=PostgresApplicationKeyVerifier(database),
        authentication_facts_reader=reader,
        verification_profile=PROFILE,
    ).authenticate(seed.credential)
    session_reader = ApplicationSessionService(
        authentication_facts_reader=reader, verification_profile=PROFILE
    )
    assert await session_reader.read(access=access) == CurrentApplicationSessionDTO(
        principal_id=seed.account.principal_id, project_id=seed.account.project_id
    )
    assert seed.credential.value not in repr(access)

    async with database.session() as session, session.begin():
        await session.execute(
            update(ApplicationKeyRow)
            .where(ApplicationKeyRow.key_id == seed.credential.key_id.value)
            .values(revoked_at=func.clock_timestamp(type_=DateTime(timezone=True)))
        )
    with pytest.raises(ApplicationKeyCredentialRejectedError):
        await session_reader.read(access=access)


@pytest.mark.parametrize(
    "profile",
    [
        replace(PROFILE, adapter=ApplicationKeyAdapter.MCP),
        replace(PROFILE, audience=ApplicationKeyAudience("https://other.test")),
    ],
    ids=["adapter", "audience"],
)
async def test_current_session_compares_the_independent_trusted_profile(
    database: Database, profile: ApplicationKeyVerificationProfileDTO
) -> None:
    seed = await seed_application_key(database)
    reader = PostgresApplicationAuthenticationFactsReader(database)
    access = await ApplicationAuthenticationService(
        key_verifier=PostgresApplicationKeyVerifier(database),
        authentication_facts_reader=reader,
        verification_profile=PROFILE,
    ).authenticate(seed.credential)

    with pytest.raises(ApplicationKeyCredentialRejectedError):
        await ApplicationSessionService(
            authentication_facts_reader=reader, verification_profile=profile
        ).read(access=access)


@pytest.mark.parametrize("change", ["missing", "foreign", "expired"])
async def test_current_session_rejects_missing_foreign_or_expired_key_evidence(
    database: Database, change: str
) -> None:
    seed = await seed_application_key(database)
    reader = PostgresApplicationAuthenticationFactsReader(database)
    authenticator = ApplicationAuthenticationService(
        key_verifier=PostgresApplicationKeyVerifier(database),
        authentication_facts_reader=reader,
        verification_profile=PROFILE,
    )
    access = await authenticator.authenticate(seed.credential)
    if change == "foreign":
        async with database.session() as session:
            revision = await session.scalar(
                select(ProjectRow.access_revision).where(
                    ProjectRow.id == seed.account.project_id.value
                )
            )
        assert revision is not None
        foreign = await create_account(
            database,
            seed.creator_access,
            seed.account.project_id,
            revision=revision,
            name="foreign-bot",
            key="create-foreign-bot",
        )
        # Controlled setup makes the stored key foreign to the original actor context.
        async with database.session() as session, session.begin():
            await session.execute(
                update(ApplicationKeyRow)
                .where(ApplicationKeyRow.key_id == seed.credential.key_id.value)
                .values(application_principal_id=foreign.account.principal_id.value)
            )
        foreign_access = await authenticator.authenticate(seed.credential)
        assert foreign_access.actor_principal_id == foreign.account.principal_id
        assert foreign_access.actor_principal_id != access.actor_principal_id
    else:
        async with database.session() as session, session.begin():
            if change == "missing":
                await session.execute(
                    delete(ApplicationKeyRow).where(
                        ApplicationKeyRow.key_id == seed.credential.key_id.value
                    )
                )
            else:
                await session.execute(
                    update(ApplicationKeyRow)
                    .where(ApplicationKeyRow.key_id == seed.credential.key_id.value)
                    .values(expires_at=func.clock_timestamp(type_=DateTime(timezone=True)))
                )

    with pytest.raises(ApplicationKeyCredentialRejectedError):
        await ApplicationSessionService(
            authentication_facts_reader=reader, verification_profile=PROFILE
        ).read(access=access)


@pytest.mark.parametrize("change", ["membership", "project", "principal"])
async def test_current_session_rechecks_local_eligibility_after_authentication(
    database: Database, change: str
) -> None:
    seed = await seed_application_key(database)
    reader = PostgresApplicationAuthenticationFactsReader(database)
    access = await ApplicationAuthenticationService(
        key_verifier=PostgresApplicationKeyVerifier(database),
        authentication_facts_reader=reader,
        verification_profile=PROFILE,
    ).authenticate(seed.credential)
    async with database.session() as session, session.begin():
        if change == "membership":
            await session.execute(
                delete(ProjectMembershipRow).where(
                    ProjectMembershipRow.project_id == seed.account.project_id.value,
                    ProjectMembershipRow.principal_id == seed.account.principal_id.value,
                )
            )
        elif change == "project":
            await session.execute(
                update(ProjectRow)
                .where(ProjectRow.id == seed.account.project_id.value)
                .values(status=ProjectStatus.DELETING)
            )
        else:
            await session.execute(
                update(PrincipalRow)
                .where(PrincipalRow.id == seed.account.principal_id.value)
                .values(status=PrincipalStatus.SUSPENDED)
            )

    with pytest.raises(AccessDeniedError):
        await ApplicationSessionService(
            authentication_facts_reader=reader, verification_profile=PROFILE
        ).read(access=access)


@pytest.mark.parametrize("expire", [False, True], ids=["revocation", "post-wait-expiry"])
async def test_current_session_waits_for_non_key_update_and_uses_post_wait_database_time(
    database: Database, expire: bool
) -> None:
    seed = await seed_application_key(database)
    reader = PostgresApplicationAuthenticationFactsReader(database)
    access = await ApplicationAuthenticationService(
        key_verifier=PostgresApplicationKeyVerifier(database),
        authentication_facts_reader=reader,
        verification_profile=PROFILE,
    ).authenticate(seed.credential)
    session_reader = ApplicationSessionService(
        authentication_facts_reader=reader, verification_profile=PROFILE
    )
    pid, name = column("pid", Integer), column("datname", String)
    activity = table("pg_stat_activity", pid, name)
    task: asyncio.Task[CurrentApplicationSessionDTO] | None = None
    try:
        async with database.session() as holder, holder.begin():
            holder_pid = await holder.scalar(select(func.pg_backend_pid(type_=Integer)))
            assert holder_pid is not None
            await holder.execute(
                update(ApplicationKeyRow)
                .where(ApplicationKeyRow.key_id == seed.credential.key_id.value)
                .values(http_audience=PROFILE.audience.value)
            )
            task = asyncio.create_task(session_reader.read(access=access))
            blocked_pid = None
            async with asyncio.timeout(3):
                while not task.done():
                    async with database.session() as observer:
                        blocked_pid = await observer.scalar(
                            select(pid)
                            .select_from(activity)
                            .where(
                                name == func.current_database(type_=String()),
                                func.pg_blocking_pids(pid, type_=ARRAY(Integer)).contains(
                                    [holder_pid]
                                ),
                            )
                        )
                    if blocked_pid is not None:
                        break
                    await asyncio.sleep(0.01)
            if blocked_pid is None:
                task.result()
                pytest.fail("The current-key read bypassed an ordinary non-key revocation lock.")

            clock = func.clock_timestamp(type_=DateTime(timezone=True))
            await holder.execute(
                update(ApplicationKeyRow)
                .where(ApplicationKeyRow.key_id == seed.credential.key_id.value)
                .values(
                    {
                        ApplicationKeyRow.expires_at
                        if expire
                        else ApplicationKeyRow.revoked_at: clock
                    }
                )
            )
        with pytest.raises(ApplicationKeyCredentialRejectedError):
            await task
    finally:
        if task is not None:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)


@pytest.mark.parametrize("isolation", ["REPEATABLE READ", "SERIALIZABLE"])
async def test_current_session_rejects_snapshot_isolation_before_observing_facts(
    database: Database, isolation: str
) -> None:
    seed = await seed_application_key(database)
    reader = PostgresApplicationAuthenticationFactsReader(database)
    access = await ApplicationAuthenticationService(
        key_verifier=PostgresApplicationKeyVerifier(database),
        authentication_facts_reader=reader,
        verification_profile=PROFILE,
    ).authenticate(seed.credential)

    async with database.session() as configured_session:
        connection = await configured_session.connection(
            execution_options={"isolation_level": isolation}
        )
        assert (
            await configured_session.scalar(
                select(func.current_setting("transaction_isolation", type_=String()))
            )
            == isolation.lower()
        )

        @asynccontextmanager
        async def isolated_session() -> AsyncGenerator[AsyncSession]:
            # The outer session owns this real connection and rolls it back on exit.
            async with AsyncSession(bind=connection) as session:
                yield session

        with (
            patch.object(database, "session", isolated_session),
            pytest.raises(RuntimeError, match="READ COMMITTED"),
        ):
            await reader.read_current(access=access, profile=PROFILE)


async def test_ordinary_action_authorizer_reads_current_application_key_and_exact_grant(
    database: Database,
) -> None:
    seed = await seed_application_key(database)
    access = await ApplicationAuthenticationService(
        key_verifier=PostgresApplicationKeyVerifier(database),
        authentication_facts_reader=PostgresApplicationAuthenticationFactsReader(database),
        verification_profile=PROFILE,
    ).authenticate(seed.credential)
    action = ActionId(ProjectAction.INSPECT_BUDGET.value)
    request = ProjectActionAuthorizationRequestDTO(
        project_id=seed.account.project_id, action_id=action
    )
    async with database.session() as session, session.begin():
        session.add(
            ProjectActionGrantRow(
                project_id=seed.account.project_id.value,
                recipient_principal_id=seed.account.principal_id.value,
                recipient_kind=PrincipalKind.APPLICATION,
                action=action.value,
                can_grant=False,
            )
        )

    async with database.session() as session:
        scope = await ActionAuthorizationService(
            PostgresProjectActionFactsReader(session, application_key_profile=PROFILE)
        ).require_authorization(access=access, request=request)
    assert scope.project_id == seed.account.project_id
    assert scope.organization_id == seed.account.organization_id

    async with database.session() as session, session.begin():
        await session.execute(
            update(ApplicationKeyRow)
            .where(ApplicationKeyRow.key_id == seed.credential.key_id.value)
            .values(revoked_at=func.clock_timestamp(type_=DateTime(timezone=True)))
        )
    async with database.session() as session:
        with pytest.raises(ApplicationKeyCredentialRejectedError):
            await ActionAuthorizationService(
                PostgresProjectActionFactsReader(session, application_key_profile=PROFILE)
            ).require_authorization(access=access, request=request)


async def test_foreign_target_metadata_does_not_wait_for_the_bound_project(
    database: Database,
) -> None:
    seed = await seed_application_key(database)
    access = await ApplicationAuthenticationService(
        key_verifier=PostgresApplicationKeyVerifier(database),
        authentication_facts_reader=PostgresApplicationAuthenticationFactsReader(database),
        verification_profile=PROFILE,
    ).authenticate(seed.credential)
    foreign_project = ProjectId(uuid4())
    async with database.session() as session, session.begin():
        session.add(
            ProjectRow(
                id=foreign_project.value,
                organization_id=seed.account.organization_id.value,
                name="Other Project",
                status=ProjectStatus.ACTIVE,
            )
        )

    pid, name = column("pid", Integer), column("datname", String)
    activity = table("pg_stat_activity", pid, name)
    async with database.session() as holder, holder.begin():
        holder_pid = await holder.scalar(select(func.pg_backend_pid(type_=Integer)))
        assert holder_pid is not None
        assert (
            await holder.scalar(
                select(ProjectRow.id)
                .where(ProjectRow.id == seed.account.project_id.value)
                .with_for_update()
            )
            == seed.account.project_id.value
        )
        async with database.session() as caller, caller.begin():
            task = asyncio.create_task(
                PostgresProjectMetadataFactsReader(
                    caller, application_key_profile=PROFILE
                ).read_for_change(access=access, project_id=foreign_project)
            )
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
                            "Foreign-target metadata tried to lock the application's bound Project."
                        )
                        await asyncio.sleep(0.01)
                assert await task is None
            finally:
                async with asyncio.timeout(3):
                    if not task.done():
                        task.cancel()
                    # Bound the join independently of the child's cancellation response.
                    outcome = (await asyncio.shield(asyncio.gather(task, return_exceptions=True)))[
                        0
                    ]
                if isinstance(outcome, BaseException) and not isinstance(
                    outcome, asyncio.CancelledError
                ):
                    raise outcome
