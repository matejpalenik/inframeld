"""Qualify current Access rows using trusted source observations, without Document tables."""

import asyncio
import os
from uuid import uuid4

import pytest
from sqlalchemy import DateTime, Integer, String, column, delete, func, select, table, update
from sqlalchemy.dialects.postgresql import ARRAY
from tests.support.access_scenarios import MockAccessScenarios, ProjectAuthorizationSeedDTO
from tests.support.application_key_scenarios import seed_application_key
from tests.support.authentication_evidence import MockAuthenticationEvidence

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.application_key_verification_profile_dto import (
    ApplicationKeyVerificationProfileDTO,
)
from inframeld_backend.access.application.dtos.current_document_access_dto import (
    CurrentDocumentAccessDTO,
)
from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
    HumanOAuthCredentialBindingDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_event_dto import (
    IdentityRecoveryEventDTO,
)
from inframeld_backend.access.application.dtos.selected_document_source_dto import (
    SelectedDocumentSourceDTO,
)
from inframeld_backend.access.application.enums.identity_recovery_event_kind import (
    IdentityRecoveryEventKind,
)
from inframeld_backend.access.application.errors.application_key_credential_rejected_error import (
    ApplicationKeyCredentialRejectedError,
)
from inframeld_backend.access.application.errors.human_oauth_credential_rejected_error import (
    HumanOAuthCredentialRejectedError,
)
from inframeld_backend.access.application.services.application_authentication_service import (
    ApplicationAuthenticationService,
)
from inframeld_backend.access.application.services.document_access_service import (
    DocumentAccessService,
)
from inframeld_backend.access.application.services.identity_recovery_admission_service import (
    IdentityRecoveryAdmissionService,
)
from inframeld_backend.access.domain.enums.application_key_adapter import ApplicationKeyAdapter
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
from inframeld_backend.access.domain.value_objects.application_key_audience import (
    ApplicationKeyAudience,
)
from inframeld_backend.access.domain.value_objects.document_id import DocumentId
from inframeld_backend.access.domain.value_objects.document_source_id import DocumentSourceId
from inframeld_backend.access.domain.value_objects.document_version_id import DocumentVersionId
from inframeld_backend.access.domain.value_objects.identity_recovery_flow_id import (
    IdentityRecoveryFlowId,
)
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.readers.postgres_application_authentication_facts_reader import (
    PostgresApplicationAuthenticationFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_document_access_facts_reader import (
    PostgresDocumentAccessFactsReader,
)
from inframeld_backend.access.infrastructure.rows.access_group_row import AccessGroupRow
from inframeld_backend.access.infrastructure.rows.application_key_row import ApplicationKeyRow
from inframeld_backend.access.infrastructure.rows.group_membership_row import GroupMembershipRow
from inframeld_backend.access.infrastructure.rows.human_identity_link_row import (
    HumanIdentityLinkRow,
)
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_membership_row import ProjectMembershipRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.access.infrastructure.verifiers.postgres_application_key_verifier import (
    PostgresApplicationKeyVerifier,
)
from inframeld_backend.access.infrastructure.writers.postgres_human_credential_state_initializer import (
    PostgresHumanCredentialStateInitializer,
)
from inframeld_backend.access.infrastructure.writers.postgres_identity_recovery_admission_writer import (
    PostgresIdentityRecoveryAdmissionWriter,
)
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    DependencyUnavailableError,
    ResourceNotFoundError,
)
from inframeld_backend.shared.infrastructure.resources.database import Database

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
        reason="Requires isolated PostgreSQL services",
    ),
]
PROFILE = ApplicationKeyVerificationProfileDTO(
    ApplicationKeyAudience("https://api.test"), ApplicationKeyAdapter.HTTP
)
SOURCE = DocumentSourceId(DocumentId(uuid4()), DocumentVersionId(uuid4()))
SELECTED = (SelectedDocumentSourceDTO(SOURCE, True),)


async def _human(
    database: Database,
) -> tuple[ProjectAuthorizationSeedDTO, AccessContextDTO, AccessGroupId, AccessGroupId]:
    async with database.session() as session, session.begin():
        seed = await MockAccessScenarios.seed_project_authorization(
            session, is_project_member=True, has_action_grant=False
        )
        member, other = AccessGroupId(uuid4()), AccessGroupId(uuid4())
        session.add_all(
            [
                AccessGroupRow(id=g.value, project_id=seed.project_id.value, name=str(g.value))
                for g in (member, other)
            ]
        )
        await session.flush()
        session.add(
            GroupMembershipRow(
                project_id=seed.project_id.value,
                group_id=member.value,
                principal_id=seed.principal_id.value,
            )
        )
    return (
        seed,
        AccessContextDTO(seed.principal_id, MockAuthenticationEvidence.browser()),
        member,
        other,
    )


async def _query(
    database: Database,
    access: AccessContextDTO,
    project_id: ProjectId,
    audience: frozenset[AccessGroupId],
    *,
    profile: ApplicationKeyVerificationProfileDTO | None = None,
) -> tuple[DocumentSourceId, ...]:
    async with database.session() as session, session.begin():
        return await DocumentAccessService(
            PostgresDocumentAccessFactsReader(session, application_key_profile=profile)
        ).permitted_sources(
            access=access,
            project_id=project_id,
            selected=SELECTED,
            documents=(CurrentDocumentAccessDTO(SOURCE.document_id, project_id, audience, True),),
        )


async def _wait(
    database: Database,
    task: asyncio.Task[tuple[DocumentSourceId, ...]] | asyncio.Task[None],
    holder_pid: int,
) -> None:
    pid, name = column("pid", Integer), column("datname", String)
    activity = table("pg_stat_activity", pid, name)
    async with asyncio.timeout(3):
        while not task.done():
            async with database.session() as observer:
                blocked = await observer.scalar(
                    select(pid)
                    .select_from(activity)
                    .where(
                        name == func.current_database(type_=String()),
                        func.pg_blocking_pids(pid, type_=ARRAY(Integer)).contains([holder_pid]),
                    )
                )
            if blocked is not None:
                return
            await asyncio.sleep(0.01)
    await task
    pytest.fail("Document access bypassed the required coordination wait.")


async def test_real_current_group_or_preserves_exact_selected_versions(database: Database) -> None:
    seed, access, member, other = await _human(database)
    async with database.session() as session, session.begin():
        facts = await PostgresDocumentAccessFactsReader(session).read(
            access=access, project_id=seed.project_id, audience_group_ids=frozenset((member, other))
        )
        assert facts is not None
        assert (facts.principal.id, facts.organization_id, facts.project_id) == (
            seed.principal_id,
            seed.organization_id,
            seed.project_id,
        )
        assert facts.valid_group_ids == frozenset((member, other))
        assert facts.member_group_ids == frozenset((member,))
    assert await _query(database, access, seed.project_id, frozenset((member, other))) == (SOURCE,)
    async with database.session() as session, session.begin():
        await session.execute(
            delete(GroupMembershipRow).where(
                GroupMembershipRow.principal_id == seed.principal_id.value
            )
        )
    assert await _query(database, access, seed.project_id, frozenset((member, other))) == ()


@pytest.mark.parametrize("invalid", ["missing", "foreign", "empty"])
async def test_original_audience_is_not_repaired_before_or(
    database: Database, invalid: str
) -> None:
    seed, access, member, _ = await _human(database)
    bad = AccessGroupId(uuid4())
    if invalid == "foreign":
        async with database.session() as session, session.begin():
            foreign = await MockAccessScenarios.seed_project_authorization(
                session, is_project_member=True, has_action_grant=False
            )
            session.add(
                AccessGroupRow(id=bad.value, project_id=foreign.project_id.value, name="Foreign")
            )
    audience: frozenset[AccessGroupId] = (
        frozenset() if invalid == "empty" else frozenset((member, bad))
    )
    assert await _query(database, access, seed.project_id, audience) == ()


@pytest.mark.parametrize("loss", ["membership", "status", "project"])
async def test_current_scope_loss_is_hidden_even_for_empty_selection(
    database: Database, loss: str
) -> None:
    seed, access, _, _ = await _human(database)
    async with database.session() as session, session.begin():
        if loss == "membership":
            await session.execute(
                delete(GroupMembershipRow).where(
                    GroupMembershipRow.project_id == seed.project_id.value,
                    GroupMembershipRow.principal_id == seed.principal_id.value,
                )
            )
            await session.execute(
                delete(ProjectMembershipRow).where(
                    ProjectMembershipRow.principal_id == seed.principal_id.value
                )
            )
        elif loss == "status":
            await session.execute(
                update(PrincipalRow)
                .where(PrincipalRow.id == seed.principal_id.value)
                .values(status=PrincipalStatus.SUSPENDED)
            )
        else:
            await session.execute(
                update(ProjectRow)
                .where(ProjectRow.id == seed.project_id.value)
                .values(status=ProjectStatus.DELETING)
            )
    async with database.session() as session, session.begin():
        with pytest.raises(ResourceNotFoundError):
            await DocumentAccessService(
                PostgresDocumentAccessFactsReader(session)
            ).permitted_sources(
                access=access, project_id=seed.project_id, selected=(), documents=()
            )


@pytest.mark.parametrize("isolation", ["REPEATABLE READ", "SERIALIZABLE"])
async def test_noncurrent_transaction_is_refused(database: Database, isolation: str) -> None:
    seed, access, member, _ = await _human(database)
    async with database.session() as session:
        await session.connection(execution_options={"isolation_level": isolation})
        with pytest.raises(RuntimeError, match="READ COMMITTED"):
            await PostgresDocumentAccessFactsReader(session).read(
                access=access, project_id=seed.project_id, audience_group_ids=frozenset((member,))
            )
        await session.rollback()


async def test_caller_transaction_is_required(database: Database) -> None:
    seed, access, member, _ = await _human(database)
    async with database.session() as session:
        with pytest.raises(RuntimeError, match="transaction"):
            await PostgresDocumentAccessFactsReader(session).read(
                access=access, project_id=seed.project_id, audience_group_ids=frozenset((member,))
            )


@pytest.mark.parametrize("change", ["revoke", "expire", "profile"])
async def test_application_requires_current_key_and_explicit_profile(
    database: Database, change: str
) -> None:
    seed = await seed_application_key(database)
    access = await ApplicationAuthenticationService(
        key_verifier=PostgresApplicationKeyVerifier(database),
        authentication_facts_reader=PostgresApplicationAuthenticationFactsReader(database),
        verification_profile=PROFILE,
    ).authenticate(seed.credential)
    group = AccessGroupId(uuid4())
    async with database.session() as session, session.begin():
        session.add(
            AccessGroupRow(
                id=group.value,
                project_id=seed.account.project_id.value,
                name="ApplicationDocuments",
            )
        )
        await session.flush()
        session.add(
            GroupMembershipRow(
                project_id=seed.account.project_id.value,
                group_id=group.value,
                principal_id=seed.account.principal_id.value,
            )
        )
    assert await _query(
        database, access, seed.account.project_id, frozenset((group,)), profile=PROFILE
    ) == (SOURCE,)
    if change != "profile":
        async with database.session() as session, session.begin():
            await session.execute(
                update(ApplicationKeyRow)
                .where(ApplicationKeyRow.key_id == seed.credential.key_id.value)
                .values(
                    {
                        ApplicationKeyRow.revoked_at
                        if change == "revoke"
                        else ApplicationKeyRow.expires_at: func.clock_timestamp(
                            type_=DateTime(timezone=True)
                        )
                    }
                )
            )
    with pytest.raises(
        DependencyUnavailableError if change == "profile" else ApplicationKeyCredentialRejectedError
    ):
        await _query(
            database,
            access,
            seed.account.project_id,
            frozenset((group,)),
            profile=None if change == "profile" else PROFILE,
        )


@pytest.mark.parametrize("change", ["expire", "suspend"])
async def test_current_state_is_observed_after_key_wait(database: Database, change: str) -> None:
    seed = await seed_application_key(database)
    access = await ApplicationAuthenticationService(
        key_verifier=PostgresApplicationKeyVerifier(database),
        authentication_facts_reader=PostgresApplicationAuthenticationFactsReader(database),
        verification_profile=PROFILE,
    ).authenticate(seed.credential)
    task: asyncio.Task[tuple[DocumentSourceId, ...]] | None = None
    work_error: BaseException | None = None
    observed_rejection: BaseException | None = None
    try:
        async with database.session() as holder, holder.begin():
            holder_pid = await holder.scalar(select(func.pg_backend_pid(type_=Integer)))
            assert holder_pid is not None
            await holder.scalar(
                select(ApplicationKeyRow.key_id)
                .where(ApplicationKeyRow.key_id == seed.credential.key_id.value)
                .with_for_update()
            )
            task = asyncio.create_task(
                _query(database, access, seed.account.project_id, frozenset(), profile=PROFILE)
            )
            await _wait(database, task, holder_pid)
            if change == "expire":
                await holder.execute(
                    update(ApplicationKeyRow)
                    .where(ApplicationKeyRow.key_id == seed.credential.key_id.value)
                    .values(expires_at=func.clock_timestamp(type_=DateTime(timezone=True)))
                )
            else:
                await holder.execute(
                    update(PrincipalRow)
                    .where(PrincipalRow.id == seed.account.principal_id.value)
                    .values(status=PrincipalStatus.SUSPENDED)
                )
        with pytest.raises(
            ApplicationKeyCredentialRejectedError if change == "expire" else ResourceNotFoundError
        ) as rejection:
            async with asyncio.timeout(3):
                await task
        observed_rejection = rejection.value
    except BaseException as error:
        work_error = error
        raise
    finally:
        if task is not None:
            try:
                async with asyncio.timeout(3):
                    if not task.done():
                        task.cancel()
                    outcome = (await asyncio.shield(asyncio.gather(task, return_exceptions=True)))[
                        0
                    ]
                if (
                    isinstance(outcome, BaseException)
                    and not isinstance(outcome, asyncio.CancelledError)
                    and outcome is not observed_rejection
                    and outcome is not work_error
                ):
                    raise outcome
            except BaseException as cleanup_error:
                if work_error is not None and cleanup_error is not work_error:
                    raise BaseExceptionGroup(
                        "Document read and task cleanup failed", [work_error, cleanup_error]
                    ) from None
                raise


@pytest.mark.parametrize("credential", ["browser", "oauth"])
async def test_pending_recovery_is_current_and_blocks_source_disclosure(
    database: Database, credential: str
) -> None:
    seed, access, member, _ = await _human(database)
    identity = MockAuthenticationEvidence.browser().identity
    async with database.session() as session, session.begin():
        session.add(
            HumanIdentityLinkRow(
                authority=identity.authority.value,
                subject=identity.subject.value,
                organization_id=seed.organization_id.value,
                principal_id=seed.principal_id.value,
                principal_kind=PrincipalKind.HUMAN,
            )
        )
    state = await PostgresHumanCredentialStateInitializer(database).initialize(identity)
    assert state.version is not None
    if credential == "oauth":
        access = AccessContextDTO(
            seed.principal_id,
            HumanOAuthCredentialBindingDTO(identity, state.installation_id, state.version),
        )
    assert await _query(database, access, seed.project_id, frozenset((member,))) == (SOURCE,)
    async with database.session() as session, session.begin():
        await IdentityRecoveryAdmissionService(
            PostgresIdentityRecoveryAdmissionWriter(
                session, installation_id=state.installation_id, authority=identity.authority
            )
        ).admit(
            IdentityRecoveryEventDTO(
                IdentityRecoveryFlowId(uuid4()), identity, IdentityRecoveryEventKind.RECOVERY
            )
        )
    async with database.session() as session, session.begin():
        facts = await PostgresDocumentAccessFactsReader(session).read(
            access=access, project_id=seed.project_id, audience_group_ids=frozenset((member,))
        )
        assert facts is not None and facts.has_pending_recovery
    with pytest.raises(
        AccessDeniedError if credential == "browser" else HumanOAuthCredentialRejectedError
    ):
        await _query(database, access, seed.project_id, frozenset((member,)))


async def test_foreign_application_scope_does_not_lock_bound_project(database: Database) -> None:
    seed = await seed_application_key(database)
    access = await ApplicationAuthenticationService(
        key_verifier=PostgresApplicationKeyVerifier(database),
        authentication_facts_reader=PostgresApplicationAuthenticationFactsReader(database),
        verification_profile=PROFILE,
    ).authenticate(seed.credential)
    async with database.session() as holder, holder.begin():
        await holder.scalar(
            select(ProjectRow.id)
            .where(ProjectRow.id == seed.account.project_id.value)
            .with_for_update()
        )
        async with database.session() as caller, caller.begin(), asyncio.timeout(3):
            assert (
                await PostgresDocumentAccessFactsReader(
                    caller, application_key_profile=PROFILE
                ).read(access=access, project_id=ProjectId(uuid4()), audience_group_ids=frozenset())
                is None
            )


@pytest.mark.parametrize("guard", ["organization", "project"])
async def test_read_guards_remain_owned_by_caller_transaction(
    database: Database, guard: str
) -> None:
    seed, access, member, _ = await _human(database)
    task: asyncio.Task[None] | None = None
    work_error: BaseException | None = None

    async def change_guard() -> None:
        async with database.session() as changer, changer.begin():
            if guard == "organization":
                await changer.execute(
                    update(OrganizationRow)
                    .where(OrganizationRow.id == seed.organization_id.value)
                    .values(name="Changed")
                )
            else:
                await changer.execute(
                    update(ProjectRow)
                    .where(ProjectRow.id == seed.project_id.value)
                    .values(name="Changed")
                )

    try:
        async with database.session() as caller, caller.begin():
            facts = await PostgresDocumentAccessFactsReader(caller).read(
                access=access, project_id=seed.project_id, audience_group_ids=frozenset((member,))
            )
            assert facts is not None and facts.member_group_ids == frozenset((member,))
            holder_pid = await caller.scalar(select(func.pg_backend_pid(type_=Integer)))
            assert holder_pid is not None
            task = asyncio.create_task(change_guard())
            await _wait(database, task, holder_pid)
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
                    outcome = (await asyncio.shield(asyncio.gather(task, return_exceptions=True)))[
                        0
                    ]
                if (
                    isinstance(outcome, BaseException)
                    and not isinstance(outcome, asyncio.CancelledError)
                    and outcome is not work_error
                ):
                    raise outcome
            except BaseException as cleanup_error:
                if work_error is not None and cleanup_error is not work_error:
                    raise BaseExceptionGroup(
                        "Document guard and task cleanup failed", [work_error, cleanup_error]
                    ) from None
                raise
