"""Qualify Revoke-only observations against a key issued by the delivered workflow."""

import asyncio
import os
from dataclasses import replace
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import DateTime, Integer, String, column, delete, func, select, table, update
from sqlalchemy.dialects.postgresql import ARRAY
from tests.support.application_account_scenarios import create_account
from tests.support.authentication_evidence import MockAuthenticationEvidence
from tests.support.project_creation_scenarios import ProjectCreationSeedDTO, create_project
from tests.support.project_membership_postgres_scenarios import (
    change_membership,
    seed_membership_project,
)

from inframeld_backend.access.application.commands.issue_application_key_command import (
    IssueApplicationKeyCommand,
)
from inframeld_backend.access.application.commands.revoke_application_key_command import (
    RevokeApplicationKeyCommand,
)
from inframeld_backend.access.application.commands.set_application_account_action_grant_command import (
    SetApplicationAccountActionGrantCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.application_key_issue_result_dto import (
    ApplicationKeyIssueResultDTO,
)
from inframeld_backend.access.application.dtos.application_key_revocation_facts_dto import (
    ApplicationKeyRevocationFactsDTO,
)
from inframeld_backend.access.application.dtos.application_key_verification_profile_dto import (
    ApplicationKeyVerificationProfileDTO,
)
from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
    HumanOAuthCredentialBindingDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_event_dto import (
    IdentityRecoveryEventDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.enums.identity_recovery_event_kind import (
    IdentityRecoveryEventKind,
)
from inframeld_backend.access.application.services.application_key_issuance_fingerprint_service import (
    ApplicationKeyIssuanceFingerprintService,
)
from inframeld_backend.access.application.services.identity_recovery_admission_service import (
    IdentityRecoveryAdmissionService,
)
from inframeld_backend.access.domain.enums.application_account_action import (
    ApplicationAccountAction,
)
from inframeld_backend.access.domain.enums.application_key_adapter import ApplicationKeyAdapter
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.application_key_audience import (
    ApplicationKeyAudience,
)
from inframeld_backend.access.domain.value_objects.application_key_id import ApplicationKeyId
from inframeld_backend.access.domain.value_objects.identity_recovery_flow_id import (
    IdentityRecoveryFlowId,
)
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.infrastructure.readers.postgres_application_key_revocation_facts_reader import (
    PostgresApplicationKeyRevocationFactsReader,
)
from inframeld_backend.access.infrastructure.rows.application_action_grant_row import (
    ApplicationActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.application_key_row import ApplicationKeyRow
from inframeld_backend.access.infrastructure.rows.group_manager_row import GroupManagerRow
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.project_membership_row import ProjectMembershipRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.access.infrastructure.settings.application_key_issuance_settings import (
    ApplicationKeyIssuanceSettings,
)
from inframeld_backend.access.infrastructure.verifiers.postgres_application_key_verifier import (
    PostgresApplicationKeyVerifier,
)
from inframeld_backend.access.infrastructure.writers.postgres_human_credential_state_initializer import (
    PostgresHumanCredentialStateInitializer,
)
from inframeld_backend.access.infrastructure.writers.postgres_identity_recovery_admission_writer import (
    PostgresIdentityRecoveryAdmissionWriter,
)
from inframeld_backend.bootstrap.application_account_grant_composition import (
    open_application_account_grant_change,
)
from inframeld_backend.bootstrap.application_key_composition import open_application_key_issuance
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.request_fingerprint_key import (
    RequestFingerprintKey,
)
from inframeld_backend.shared.infrastructure.resources.database import Database

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
        reason="Requires isolated PostgreSQL integration services",
    ),
]
HTTP = ApplicationKeyVerificationProfileDTO(
    ApplicationKeyAudience("https://api.test"), ApplicationKeyAdapter.HTTP
)


@pytest_asyncio.fixture
async def revocation_scope(
    database: Database,
) -> tuple[ProjectCreationSeedDTO, AccessContextDTO, ApplicationKeyIssueResultDTO, int]:
    seed = await seed_membership_project(database)
    joined = await change_membership(
        database, seed, revision=seed.project.access_revision, key="join-revoker"
    )
    account = (
        await create_account(
            database, seed.actor.access, seed.project.project_id, revision=joined.access_revision
        )
    ).account
    route = (
        f"/v1/projects/{account.project_id.value}/application-accounts/{account.principal_id.value}"
    )
    fingerprints = RequestFingerprintService(RequestFingerprintKey(b"r" * 32))
    async with open_application_key_issuance(
        database,
        ApplicationKeyIssuanceFingerprintService(fingerprints),
        http_profile=HTTP,
        mcp_profile=None,
        settings=ApplicationKeyIssuanceSettings(),
    ) as issuer:
        issued = await issuer.issue(
            access=seed.actor.access,
            command=IssueApplicationKeyCommand(
                account.project_id,
                account.principal_id,
                (ApplicationKeyAdapter.HTTP,),
                account.access_revision,
            ),
            context=IdempotencyContextDTO(
                HttpMethod.POST, route + "/keys", IdempotencyKey("issue-revocation-target")
            ),
        )
    assert issued.credential is not None
    verified = await PostgresApplicationKeyVerifier(database).verify(
        issued.credential, profile=HTTP
    )
    assert verified is not None
    assert verified.key_id == issued.original.metadata.key_id
    assert verified.principal_id == account.principal_id

    action = ActionId(ApplicationAccountAction.REVOKE_KEYS.value)
    async with open_application_account_grant_change(database, fingerprints) as grants:
        granted = await grants.set_grant(
            access=seed.actor.access,
            command=SetApplicationAccountActionGrantCommand(
                account.project_id,
                account.principal_id,
                seed.bob_id,
                action,
                False,
                issued.original.access_revision,
            ),
            context=IdempotencyContextDTO(
                HttpMethod.PUT,
                route + f"/grants/{seed.bob_id.value}/{action.value}",
                IdempotencyKey("grant-revoke-only"),
            ),
        )
    revoker = AccessContextDTO(
        seed.bob_id,
        MockAuthenticationEvidence.browser(
            VerifiedHumanIdentityDTO(
                seed.actor.binding.identity.authority, IdentitySubject(str(UUID(int=200)))
            )
        ),
    )

    async with database.session() as session, session.begin():
        assignments = (
            (
                await session.execute(
                    select(
                        ApplicationActionGrantRow.action, ApplicationActionGrantRow.can_grant
                    ).where(
                        ApplicationActionGrantRow.project_id == account.project_id.value,
                        ApplicationActionGrantRow.application_principal_id
                        == account.principal_id.value,
                        ApplicationActionGrantRow.recipient_principal_id == seed.bob_id.value,
                    )
                )
            )
            .tuples()
            .all()
        )
        assert assignments == [(ApplicationAccountAction.REVOKE_KEYS.value, False)]
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ProjectActionGrantRow)
                .where(
                    ProjectActionGrantRow.project_id == account.project_id.value,
                    ProjectActionGrantRow.recipient_principal_id == seed.bob_id.value,
                )
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(GroupManagerRow)
                .where(
                    GroupManagerRow.project_id == account.project_id.value,
                    GroupManagerRow.principal_id == seed.bob_id.value,
                )
            )
            == 0
        )

    return seed.actor, revoker, issued, granted.access_revision


async def test_revoke_only_human_observes_the_exact_issued_key_under_coordination(
    database: Database,
    revocation_scope: tuple[
        ProjectCreationSeedDTO, AccessContextDTO, ApplicationKeyIssueResultDTO, int
    ],
) -> None:
    _, revoker, issued, revision = revocation_scope
    metadata = issued.original.metadata
    async with database.session() as session, session.begin():
        before = await session.scalar(select(func.clock_timestamp(type_=DateTime(timezone=True))))
        assert before is not None
        facts = await PostgresApplicationKeyRevocationFactsReader(session).lock_for_revoke(
            access=revoker,
            command=RevokeApplicationKeyCommand(
                metadata.project_id, metadata.application_principal_id, metadata.key_id, revision
            ),
        )
        assert facts is not None
        assert facts.organization_id == issued.original.organization_id
        assert facts.project_id == metadata.project_id
        assert facts.actor.principal.id == revoker.actor_principal_id
        assert facts.actor.has_exact_action_grant and facts.actor.is_project_member
        assert facts.application_principal.id == metadata.application_principal_id
        assert facts.metadata == metadata and facts.access_revision == revision
        assert facts.checked_at >= before and facts.checked_at.utcoffset() == timedelta(0)


@pytest.mark.parametrize("loss", ["revoke", "membership", "status", "project"])
async def test_current_revoker_losses_remain_explicit_observations(
    database: Database,
    revocation_scope: tuple[
        ProjectCreationSeedDTO, AccessContextDTO, ApplicationKeyIssueResultDTO, int
    ],
    loss: str,
) -> None:
    _, revoker, issued, revision = revocation_scope
    metadata = issued.original.metadata
    async with database.session() as session, session.begin():
        if loss in ("revoke", "membership"):
            await session.execute(
                delete(ApplicationActionGrantRow).where(
                    ApplicationActionGrantRow.project_id == metadata.project_id.value,
                    ApplicationActionGrantRow.application_principal_id
                    == metadata.application_principal_id.value,
                    ApplicationActionGrantRow.recipient_principal_id
                    == revoker.actor_principal_id.value,
                    ApplicationActionGrantRow.action == ApplicationAccountAction.REVOKE_KEYS.value,
                )
            )
            if loss == "membership":
                await session.execute(
                    delete(ProjectMembershipRow).where(
                        ProjectMembershipRow.project_id == metadata.project_id.value,
                        ProjectMembershipRow.principal_id == revoker.actor_principal_id.value,
                    )
                )
        elif loss == "status":
            await session.execute(
                update(PrincipalRow)
                .where(PrincipalRow.id == revoker.actor_principal_id.value)
                .values(status=PrincipalStatus.SUSPENDED)
            )
        else:
            await session.execute(
                update(ProjectRow)
                .where(ProjectRow.id == metadata.project_id.value)
                .values(status=ProjectStatus.DELETING)
            )

    async with database.session() as session, session.begin():
        facts = await PostgresApplicationKeyRevocationFactsReader(session).lock_for_revoke(
            access=revoker,
            command=RevokeApplicationKeyCommand(
                metadata.project_id, metadata.application_principal_id, metadata.key_id, revision
            ),
        )
    assert facts is not None and facts.metadata == metadata
    assert facts.actor.has_exact_action_grant is (loss not in ("revoke", "membership"))
    assert facts.actor.is_project_member is (loss != "membership")
    assert facts.actor.principal.status is (
        PrincipalStatus.SUSPENDED if loss == "status" else PrincipalStatus.ACTIVE
    )
    assert facts.actor.project_status is (
        ProjectStatus.DELETING if loss == "project" else ProjectStatus.ACTIVE
    )


@pytest.mark.parametrize("mismatch", ["absent-key", "another-account"])
async def test_unmatched_key_scope_is_hidden(
    database: Database,
    revocation_scope: tuple[
        ProjectCreationSeedDTO, AccessContextDTO, ApplicationKeyIssueResultDTO, int
    ],
    mismatch: str,
) -> None:
    creator, revoker, issued, revision = revocation_scope
    metadata = issued.original.metadata
    command = RevokeApplicationKeyCommand(
        metadata.project_id, metadata.application_principal_id, ApplicationKeyId(uuid4()), revision
    )
    if mismatch == "another-account":
        other = (
            await create_account(
                database,
                creator.access,
                metadata.project_id,
                revision=revision,
                name="another-bot",
                key="another-account",
            )
        ).account
        command = replace(
            command,
            application_principal_id=other.principal_id,
            key_id=metadata.key_id,
            expected_access_revision=other.access_revision,
        )
        revoker = creator.access
    async with database.session() as session, session.begin():
        assert (
            await PostgresApplicationKeyRevocationFactsReader(session).lock_for_revoke(
                access=revoker, command=command
            )
            is None
        )


@pytest.mark.parametrize("recovering", [False, True], ids=["current", "recovery-invalidated"])
async def test_current_human_credential_and_recovery_facts_are_preserved(
    database: Database,
    revocation_scope: tuple[
        ProjectCreationSeedDTO, AccessContextDTO, ApplicationKeyIssueResultDTO, int
    ],
    recovering: bool,
) -> None:
    creator, revoker, issued, revision = revocation_scope
    metadata = issued.original.metadata
    identity = VerifiedHumanIdentityDTO(
        creator.binding.identity.authority, IdentitySubject(str(UUID(int=200)))
    )
    initialized = await PostgresHumanCredentialStateInitializer(database).initialize(identity)
    assert initialized.version is not None
    binding = HumanOAuthCredentialBindingDTO(
        identity, initialized.installation_id, initialized.version
    )
    if recovering:
        async with database.session() as session, session.begin():
            await IdentityRecoveryAdmissionService(
                PostgresIdentityRecoveryAdmissionWriter(
                    session,
                    installation_id=initialized.installation_id,
                    authority=identity.authority,
                )
            ).admit(
                IdentityRecoveryEventDTO(
                    flow_id=IdentityRecoveryFlowId(uuid4()),
                    identity=identity,
                    event_kind=IdentityRecoveryEventKind.RECOVERY,
                )
            )
    async with database.session() as session, session.begin():
        facts = await PostgresApplicationKeyRevocationFactsReader(session).lock_for_revoke(
            access=AccessContextDTO(revoker.actor_principal_id, binding),
            command=RevokeApplicationKeyCommand(
                metadata.project_id, metadata.application_principal_id, metadata.key_id, revision
            ),
        )
    assert facts is not None
    assert facts.actor.has_pending_recovery is recovering
    credential = facts.actor.oauth_credential_facts
    assert credential is not None and credential.binding_matches_actor
    assert credential.current_version is not None
    assert credential.current_version.value == binding.version.value + int(recovering)


@pytest.mark.parametrize("isolation", ["REPEATABLE READ", "SERIALIZABLE"])
async def test_snapshot_isolation_is_refused_before_current_facts(
    database: Database,
    revocation_scope: tuple[
        ProjectCreationSeedDTO, AccessContextDTO, ApplicationKeyIssueResultDTO, int
    ],
    isolation: str,
) -> None:
    _, revoker, issued, revision = revocation_scope
    metadata = issued.original.metadata
    async with database.session() as session:
        await session.connection(execution_options={"isolation_level": isolation})
        with pytest.raises(RuntimeError, match="READ COMMITTED"):
            await PostgresApplicationKeyRevocationFactsReader(session).lock_for_revoke(
                access=revoker,
                command=RevokeApplicationKeyCommand(
                    metadata.project_id,
                    metadata.application_principal_id,
                    metadata.key_id,
                    revision,
                ),
            )


async def test_facts_require_the_active_caller_transaction(
    database: Database,
    revocation_scope: tuple[
        ProjectCreationSeedDTO, AccessContextDTO, ApplicationKeyIssueResultDTO, int
    ],
) -> None:
    _, revoker, issued, revision = revocation_scope
    metadata = issued.original.metadata
    async with database.session() as session:
        with pytest.raises(RuntimeError, match="caller transaction"):
            await PostgresApplicationKeyRevocationFactsReader(session).lock_for_revoke(
                access=revoker,
                command=RevokeApplicationKeyCommand(
                    metadata.project_id,
                    metadata.application_principal_id,
                    metadata.key_id,
                    revision,
                ),
            )


@pytest.mark.parametrize("coordination", ["organization", "project", "key-revoked", "key-expired"])
async def test_coordination_order_and_post_wait_database_observation(
    database: Database,
    revocation_scope: tuple[
        ProjectCreationSeedDTO, AccessContextDTO, ApplicationKeyIssueResultDTO, int
    ],
    coordination: str,
) -> None:
    _, revoker, issued, revision = revocation_scope
    metadata = issued.original.metadata
    pid, name = column("pid", Integer), column("datname", String)
    activity = table("pg_stat_activity", pid, name)
    task: asyncio.Task[ApplicationKeyRevocationFactsDTO | None] | None = None
    work_error: BaseException | None = None
    async with database.session() as caller, caller.begin():
        try:
            async with database.session() as holder, holder.begin():
                holder_pid = await holder.scalar(select(func.pg_backend_pid(type_=Integer)))
                assert holder_pid is not None
                if coordination == "organization":
                    await holder.scalar(
                        select(OrganizationRow.id)
                        .where(OrganizationRow.id == issued.original.organization_id.value)
                        .with_for_update()
                    )
                elif coordination == "project":
                    await holder.scalar(
                        select(ProjectRow.id)
                        .where(ProjectRow.id == metadata.project_id.value)
                        .with_for_update()
                    )
                else:
                    await holder.execute(
                        update(ApplicationKeyRow)
                        .where(ApplicationKeyRow.key_id == metadata.key_id.value)
                        .values(http_audience=HTTP.audience.value)
                    )
                task = asyncio.create_task(
                    PostgresApplicationKeyRevocationFactsReader(caller).lock_for_revoke(
                        access=revoker,
                        command=RevokeApplicationKeyCommand(
                            metadata.project_id,
                            metadata.application_principal_id,
                            metadata.key_id,
                            revision,
                        ),
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
                    pytest.fail("Revocation facts bypassed their required coordination lock.")

                if coordination in ("organization", "project"):
                    async with database.session() as later, later.begin():
                        if coordination == "organization":
                            await later.scalar(
                                select(ProjectRow.id)
                                .where(ProjectRow.id == metadata.project_id.value)
                                .with_for_update(nowait=True)
                            )
                        await later.scalar(
                            select(ApplicationKeyRow.key_id)
                            .where(ApplicationKeyRow.key_id == metadata.key_id.value)
                            .with_for_update(nowait=True)
                        )
                released_at = await holder.scalar(
                    select(func.clock_timestamp(type_=DateTime(timezone=True)))
                )
                assert released_at is not None
                if coordination in ("organization", "project"):
                    await holder.execute(
                        delete(ApplicationActionGrantRow).where(
                            ApplicationActionGrantRow.project_id == metadata.project_id.value,
                            ApplicationActionGrantRow.application_principal_id
                            == metadata.application_principal_id.value,
                            ApplicationActionGrantRow.recipient_principal_id
                            == revoker.actor_principal_id.value,
                            ApplicationActionGrantRow.action
                            == ApplicationAccountAction.REVOKE_KEYS.value,
                        )
                    )
                elif coordination == "key-revoked":
                    await holder.execute(
                        update(ApplicationKeyRow)
                        .where(ApplicationKeyRow.key_id == metadata.key_id.value)
                        .values(revoked_at=released_at)
                    )
                else:
                    await holder.execute(
                        update(ApplicationKeyRow)
                        .where(ApplicationKeyRow.key_id == metadata.key_id.value)
                        .values(expires_at=released_at)
                    )
            async with asyncio.timeout(3):
                facts = await task
            assert facts is not None and facts.metadata is not None
            assert facts.checked_at >= released_at
            assert facts.actor.has_exact_action_grant is (
                coordination not in ("organization", "project")
            )
            if coordination == "key-revoked":
                assert facts.metadata.revoked_at == released_at
            elif coordination == "key-expired":
                assert facts.metadata.expires_at == released_at
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
                            "Revocation observation and task cleanup failed",
                            [work_error, cleanup_error],
                        ) from None
                    raise


async def test_foreign_target_does_not_lock_the_keys_bound_project(
    database: Database,
    revocation_scope: tuple[
        ProjectCreationSeedDTO, AccessContextDTO, ApplicationKeyIssueResultDTO, int
    ],
) -> None:
    creator, _, issued, _ = revocation_scope
    metadata = issued.original.metadata
    foreign = (
        await create_project(database, creator, name="foreign-project", key="foreign-project")
    ).project
    pid, name = column("pid", Integer), column("datname", String)
    activity = table("pg_stat_activity", pid, name)
    async with database.session() as holder, holder.begin():
        holder_pid = await holder.scalar(select(func.pg_backend_pid(type_=Integer)))
        assert holder_pid is not None
        await holder.scalar(
            select(ProjectRow.id)
            .where(ProjectRow.id == metadata.project_id.value)
            .with_for_update()
        )
        async with database.session() as caller, caller.begin():
            await caller.scalar(
                select(OrganizationRow.id)
                .where(OrganizationRow.id == issued.original.organization_id.value)
                .with_for_update(read=True)
            )
            await caller.scalar(
                select(ProjectRow.id)
                .where(ProjectRow.id == foreign.project_id.value)
                .with_for_update()
            )
            task = asyncio.create_task(
                PostgresApplicationKeyRevocationFactsReader(caller).lock_for_revoke(
                    access=creator.access,
                    command=RevokeApplicationKeyCommand(
                        foreign.project_id,
                        metadata.application_principal_id,
                        metadata.key_id,
                        foreign.access_revision,
                    ),
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
                            "Foreign key scope tried to lock the key's bound Project."
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
                            "Foreign key scope and task cleanup failed",
                            [work_error, cleanup_error],
                        ) from None
                    raise


@pytest.mark.parametrize("coordination", ["organization", "project", "key"])
async def test_observation_retains_each_guard_until_caller_transaction_ends(
    database: Database,
    revocation_scope: tuple[
        ProjectCreationSeedDTO, AccessContextDTO, ApplicationKeyIssueResultDTO, int
    ],
    coordination: str,
) -> None:
    _, revoker, issued, revision = revocation_scope
    metadata = issued.original.metadata
    pid, name = column("pid", Integer), column("datname", String)
    activity = table("pg_stat_activity", pid, name)
    task: asyncio.Task[None] | None = None
    work_error: BaseException | None = None
    async with database.session() as contender, contender.begin():
        try:
            async with database.session() as caller, caller.begin():
                caller_pid = await caller.scalar(select(func.pg_backend_pid(type_=Integer)))
                assert caller_pid is not None
                facts = await PostgresApplicationKeyRevocationFactsReader(caller).lock_for_revoke(
                    access=revoker,
                    command=RevokeApplicationKeyCommand(
                        metadata.project_id,
                        metadata.application_principal_id,
                        metadata.key_id,
                        revision,
                    ),
                )
                assert facts is not None

                async def change_guarded_state() -> None:
                    if coordination == "organization":
                        await contender.scalar(
                            select(OrganizationRow.id)
                            .where(OrganizationRow.id == issued.original.organization_id.value)
                            .with_for_update()
                        )
                    elif coordination == "project":
                        await contender.scalar(
                            select(ProjectRow.id)
                            .where(ProjectRow.id == metadata.project_id.value)
                            .with_for_update()
                        )
                    else:
                        await contender.execute(
                            update(ApplicationKeyRow)
                            .where(ApplicationKeyRow.key_id == metadata.key_id.value)
                            .values(http_audience=HTTP.audience.value)
                        )

                task = asyncio.create_task(change_guarded_state())
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
                                        [caller_pid]
                                    ),
                                )
                            )
                        if blocked is not None:
                            break
                        await asyncio.sleep(0.01)
                if blocked is None:
                    await task
                    pytest.fail("The revocation reader released a caller-owned guard early.")
            async with asyncio.timeout(3):
                await task
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
                            "Revocation guard observation and task cleanup failed",
                            [work_error, cleanup_error],
                        ) from None
                    raise
