"""Keep human observations stable and require distinct application-key authority."""

import asyncio
import os
from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy import Integer, String, column, event, func, select, table, update
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import ORMExecuteState
from tests.support.access_scenarios import MockAccessScenarios
from tests.support.application_key_scenarios import verified_application_access
from tests.support.authentication_evidence import MockAuthenticationEvidence

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.application_key_authentication_dto import (
    ApplicationKeyAuthenticationDTO,
)
from inframeld_backend.access.application.dtos.application_key_current_facts_dto import (
    ApplicationKeyCurrentFactsDTO,
)
from inframeld_backend.access.application.dtos.application_key_verification_profile_dto import (
    ApplicationKeyVerificationProfileDTO,
)
from inframeld_backend.access.application.dtos.browser_session_authentication_dto import (
    BrowserSessionAuthenticationDTO,
)
from inframeld_backend.access.application.dtos.human_credential_facts_dto import (
    HumanCredentialFactsDTO,
)
from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
    HumanOAuthCredentialBindingDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_event_dto import (
    IdentityRecoveryEventDTO,
)
from inframeld_backend.access.application.dtos.project_action_target_dto import (
    ProjectActionTargetDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.enums.identity_recovery_event_kind import (
    IdentityRecoveryEventKind,
)
from inframeld_backend.access.application.services.principal_access_evaluation_service import (
    PrincipalAccessEvaluationService,
)
from inframeld_backend.access.domain.enums.application_key_adapter import ApplicationKeyAdapter
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.enums.project_action import ProjectAction
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.application_key_audience import (
    ApplicationKeyAudience,
)
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_recovery_flow_id import (
    IdentityRecoveryFlowId,
)
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.infrastructure.mappers.postgres_project_actor_mapper import (
    PostgresProjectActorMapper,
)
from inframeld_backend.access.infrastructure.readers.postgres_deletion_status_facts_reader import (
    PostgresDeletionStatusFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_my_project_access_facts_reader import (
    PostgresMyProjectAccessFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_operation_lookup_facts_reader import (
    PostgresOperationLookupFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_organization_access_facts_reader import (
    PostgresOrganizationAccessFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_organization_action_grants_facts_reader import (
    PostgresOrganizationActionGrantsFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_organization_grant_management_facts_reader import (
    PostgresOrganizationGrantManagementFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_project_action_facts_reader import (
    PostgresProjectActionFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_project_action_grants_facts_reader import (
    PostgresProjectActionGrantsFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_project_grant_change_facts_reader import (
    PostgresProjectGrantChangeFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_project_members_facts_reader import (
    PostgresProjectMembersFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_project_membership_change_facts_reader import (
    PostgresProjectMembershipChangeFactsReader,
)
from inframeld_backend.access.infrastructure.readers.project_actor_queries import (
    ProjectActorQueries,
)
from inframeld_backend.access.infrastructure.rows.human_identity_link_row import (
    HumanIdentityLinkRow,
)
from inframeld_backend.access.infrastructure.rows.organization_action_grant_row import (
    OrganizationActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.access.infrastructure.writers.postgres_human_credential_state_initializer import (
    PostgresHumanCredentialStateInitializer,
)
from inframeld_backend.access.infrastructure.writers.postgres_identity_recovery_admission_writer import (
    PostgresIdentityRecoveryAdmissionWriter,
)
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.enums.operation_lookup_authority_family import (
    OperationLookupAuthorityFamily,
)
from inframeld_backend.shared.application.errors.application_errors import AccessDeniedError
from inframeld_backend.shared.application.queries.lookup_original_operation_query import (
    LookupOriginalOperationQuery,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.operation_lookup_authority import (
    OperationLookupAuthority,
)
from inframeld_backend.shared.infrastructure.resources.database import Database

pytestmark = pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
    reason="Requires PostgreSQL integration services",
)
APPLICATION_PROFILE = ApplicationKeyVerificationProfileDTO(
    ApplicationKeyAudience("https://api.test"), ApplicationKeyAdapter.HTTP
)


@pytest.mark.asyncio
@pytest.mark.parametrize("family", ["action", "grant"])
@pytest.mark.parametrize(
    "evidence",
    [
        MockAuthenticationEvidence.browser(),
        MockAuthenticationEvidence.human_oauth(),
        MockAuthenticationEvidence.application_key(),
    ],
)
async def test_observations_keep_the_existing_database_round_trips(
    database: Database,
    family: str,
    evidence: BrowserSessionAuthenticationDTO
    | HumanOAuthCredentialBindingDTO
    | ApplicationKeyAuthenticationDTO,
) -> None:
    """Preserve human query bounds, current app facts and human-only grant denial."""
    kind = (
        PrincipalKind.APPLICATION
        if isinstance(evidence, ApplicationKeyAuthenticationDTO)
        else PrincipalKind.HUMAN
    )
    async with database.session() as session, session.begin():
        seed = await MockAccessScenarios.seed_project_authorization(
            session, is_project_member=True, has_action_grant=True, principal_kind=kind
        )
        if isinstance(evidence, ApplicationKeyAuthenticationDTO):
            seed = replace(seed, action=ActionId(ProjectAction.INSPECT_FEEDBACK.value))
            await session.execute(
                update(ProjectActionGrantRow)
                .where(
                    ProjectActionGrantRow.project_id == seed.project_id.value,
                    ProjectActionGrantRow.recipient_principal_id == seed.principal_id.value,
                )
                .values(action=seed.action.value)
            )
        if isinstance(evidence, HumanOAuthCredentialBindingDTO | BrowserSessionAuthenticationDTO):
            session.add(
                HumanIdentityLinkRow(
                    authority=evidence.identity.authority.value,
                    subject=evidence.identity.subject.value,
                    organization_id=seed.organization_id.value,
                    principal_id=seed.principal_id.value,
                    principal_kind=PrincipalKind.HUMAN,
                )
            )

    if isinstance(evidence, HumanOAuthCredentialBindingDTO | BrowserSessionAuthenticationDTO):
        state = await PostgresHumanCredentialStateInitializer(database).initialize(
            evidence.identity
        )
        assert state.version is not None
        evidence = replace(evidence, installation_id=state.installation_id, version=state.version)
    access = AccessContextDTO(seed.principal_id, evidence)
    if isinstance(evidence, ApplicationKeyAuthenticationDTO):
        access = await verified_application_access(
            database,
            principal_id=seed.principal_id,
            organization_id=seed.organization_id,
            project_id=seed.project_id,
            profile=APPLICATION_PROFILE,
        )
        assert isinstance(access.authentication_evidence, ApplicationKeyAuthenticationDTO)
        evidence = access.authentication_evidence

    async with database.session() as session, session.begin():
        executions = 0
        application_key_facts: ApplicationKeyCurrentFactsDTO | None = None

        def count_execution(_state: ORMExecuteState) -> None:
            nonlocal executions
            executions += 1

        event.listen(session.sync_session, "do_orm_execute", count_execution)
        try:
            if family == "action":
                facts = await PostgresProjectActionFactsReader(
                    session, application_key_profile=APPLICATION_PROFILE
                ).read_action_facts(
                    access=access,
                    action_id=seed.action,
                    target=ProjectActionTargetDTO(seed.project_id),
                )
                assert facts is not None
                principal = facts.principal
                application_key_facts = facts.application_key_facts
            else:
                facts = await PostgresProjectGrantChangeFactsReader(session).read_for_change(
                    access=access,
                    project_id=seed.project_id,
                    recipient_principal_id=seed.principal_id,
                    action_id=seed.action,
                )
                assert facts is not None
                principal = facts.actor
        finally:
            event.remove(session.sync_session, "do_orm_execute", count_execution)

        if not isinstance(evidence, ApplicationKeyAuthenticationDTO) or family == "grant":
            assert executions == (1 if family == "action" else 4)
        if isinstance(evidence, HumanOAuthCredentialBindingDTO | BrowserSessionAuthenticationDTO):
            assert facts.oauth_credential_facts is not None
            assert facts.oauth_credential_facts.binding_matches_actor
            assert facts.oauth_credential_facts.current_version == evidence.version
        else:
            assert facts.oauth_credential_facts is None
        if isinstance(evidence, ApplicationKeyAuthenticationDTO) and family == "grant":
            with pytest.raises(AccessDeniedError):
                PrincipalAccessEvaluationService.require_human(access=access, principal=principal)
        else:
            if isinstance(evidence, ApplicationKeyAuthenticationDTO):
                assert application_key_facts is not None
                assert application_key_facts.key_id == evidence.key_id
            evaluated = PrincipalAccessEvaluationService.evaluate(
                access=access,
                principal=principal,
                has_pending_recovery=facts.has_pending_recovery,
                oauth_credential_facts=facts.oauth_credential_facts,
                application_key_facts=application_key_facts,
            )
            assert evaluated.credential_is_current
            assert not evaluated.has_pending_recovery


@pytest.mark.asyncio
async def test_action_facts_refresh_a_principal_already_loaded_in_the_session(
    database: Database,
) -> None:
    """An earlier ORM load must not hide an account suspension committed before authorization."""
    identity = VerifiedHumanIdentityDTO(
        IdentityAuthority("kratos:refresh"), IdentitySubject(str(uuid4()))
    )
    async with database.session() as session, session.begin():
        seed = await MockAccessScenarios.seed_project_authorization(
            session, is_project_member=True, has_action_grant=True
        )
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
    access = AccessContextDTO(
        seed.principal_id,
        BrowserSessionAuthenticationDTO(identity, state.installation_id, state.version),
    )
    async with database.session() as session, session.begin():
        cached_principal = await session.get(PrincipalRow, seed.principal_id.value)
        assert cached_principal is not None
        assert cached_principal.status is PrincipalStatus.ACTIVE
        async with database.session() as other_session, other_session.begin():
            await other_session.execute(
                update(PrincipalRow)
                .where(PrincipalRow.id == seed.principal_id.value)
                .values(status=PrincipalStatus.SUSPENDED)
            )

        facts = await PostgresProjectActionFactsReader(session).read_action_facts(
            access=access,
            action_id=seed.action,
            target=ProjectActionTargetDTO(seed.project_id),
        )

        assert facts is not None
        assert facts.principal.status is PrincipalStatus.SUSPENDED


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "family",
    [
        "organization",
        "organization-grants",
        "organization-management",
        "project-action",
        "project-grants",
        "project-grant-change",
        "project-members",
        "project-membership-change",
        "my-project",
        "operation-lookup",
        "deletion-status",
        "project-header",
    ],
)
async def test_browser_evidence_observes_current_credential_facts(
    database: Database, family: str
) -> None:
    """Each public SQL producer binds browser evidence to real current identity/version rows."""
    identity = VerifiedHumanIdentityDTO(
        IdentityAuthority("kratos:browser-facts"), IdentitySubject(str(uuid4()))
    )
    org_action = ActionId("create-projects")
    async with database.session() as session, session.begin():
        seed = await MockAccessScenarios.seed_project_authorization(
            session, is_project_member=True, has_action_grant=True
        )
        seed = replace(seed, action=ActionId(ProjectAction.MANAGE_PROJECT_MEMBERS.value))
        await session.execute(
            update(ProjectActionGrantRow)
            .where(
                ProjectActionGrantRow.project_id == seed.project_id.value,
                ProjectActionGrantRow.recipient_principal_id == seed.principal_id.value,
            )
            .values(action=seed.action.value, can_grant=True)
        )
        session.add(
            HumanIdentityLinkRow(
                authority=identity.authority.value,
                subject=identity.subject.value,
                organization_id=seed.organization_id.value,
                principal_id=seed.principal_id.value,
                principal_kind=PrincipalKind.HUMAN,
            )
        )
        session.add(
            OrganizationActionGrantRow(
                organization_id=seed.organization_id.value,
                recipient_principal_id=seed.principal_id.value,
                recipient_kind=PrincipalKind.HUMAN,
                action=org_action.value,
                can_grant=True,
            )
        )
    state = await PostgresHumanCredentialStateInitializer(database).initialize(identity)
    assert state.version is not None
    access = AccessContextDTO(
        seed.principal_id,
        BrowserSessionAuthenticationDTO(identity, state.installation_id, state.version),
    )
    observed: HumanCredentialFactsDTO | None
    async with database.session() as session, session.begin():
        match family:
            case "organization":
                org = await PostgresOrganizationAccessFactsReader(session).read(access=access)
                assert org is not None
                assert org.principal.id == seed.principal_id
                assert org.principal.organization_id == seed.organization_id
                assert any(grant.action_id == org_action for grant in org.grants)
                observed = org.oauth_credential_facts
            case "organization-grants":
                org_page = await PostgresOrganizationActionGrantsFactsReader(session).read_page(
                    access=access,
                    organization_id=seed.organization_id,
                    action_id=org_action,
                    after=None,
                    limit=2,
                )
                assert org_page is not None
                assert org_page.organization_id == seed.organization_id
                assert org_page.action_id == org_action and org_page.actor.id == seed.principal_id
                assert org_page.actor_can_grant
                observed = org_page.actor_oauth_credential_facts
            case "organization-management":
                org_grant = await PostgresOrganizationGrantManagementFactsReader(
                    session
                ).lock_for_management(
                    access=access,
                    organization_id=seed.organization_id,
                    recipient_principal_id=seed.principal_id,
                    action_id=org_action,
                )
                assert org_grant is not None
                assert org_grant.organization_id == seed.organization_id
                assert org_grant.actor.id == seed.principal_id and org_grant.action_id == org_action
                assert (
                    org_grant.recipient is not None and org_grant.recipient.id == seed.principal_id
                )
                observed = org_grant.actor_oauth_credential_facts
            case "project-action":
                action = await PostgresProjectActionFactsReader(session).read_action_facts(
                    access=access,
                    action_id=seed.action,
                    target=ProjectActionTargetDTO(seed.project_id),
                )
                assert action is not None
                assert action.principal.id == seed.principal_id
                assert action.principal.organization_id == seed.organization_id
                assert action.is_project_member and action.has_exact_action_grant
                observed = action.oauth_credential_facts
            case "project-grants":
                project_page = await PostgresProjectActionGrantsFactsReader(session).read_page(
                    access=access,
                    project_id=seed.project_id,
                    action_id=seed.action,
                    after=None,
                    limit=2,
                )
                assert project_page is not None
                assert (
                    project_page.project_id == seed.project_id
                    and project_page.action_id == seed.action
                )
                assert project_page.action.principal.id == seed.principal_id
                observed = project_page.action.oauth_credential_facts
            case "project-grant-change":
                change = await PostgresProjectGrantChangeFactsReader(session).read_for_management(
                    access=access,
                    project_id=seed.project_id,
                    recipient_principal_id=seed.principal_id,
                    action_id=seed.action,
                )
                assert change is not None
                assert change.organization_id == seed.organization_id
                assert change.project_id == seed.project_id and change.action_id == seed.action
                assert change.grant.actor.id == seed.principal_id
                assert change.grant.recipient is not None
                assert change.grant.recipient.id == seed.principal_id
                assert change.grant.actor_is_project_member and change.grant.actor_can_grant_action
                observed = change.grant.oauth_credential_facts
            case "project-members":
                members = await PostgresProjectMembersFactsReader(session).read_page(
                    access=access, project_id=seed.project_id, after=None, limit=2
                )
                assert members is not None
                assert members.project_id == seed.project_id
                assert members.action.principal.id == seed.principal_id
                assert members.action.has_exact_action_grant
                observed = members.action.oauth_credential_facts
            case "project-membership-change":
                membership = await PostgresProjectMembershipChangeFactsReader(
                    session
                ).lock_and_load_membership_state(
                    access=access, project_id=seed.project_id, principal_id=seed.principal_id
                )
                assert membership is not None
                assert membership.project_id == seed.project_id
                assert membership.action.principal.id == seed.principal_id
                assert membership.action.has_exact_action_grant
                assert (
                    membership.recipient is not None
                    and membership.recipient.id == seed.principal_id
                )
                observed = membership.action.oauth_credential_facts
            case "my-project":
                own = await PostgresMyProjectAccessFactsReader(session).read_page(
                    access=access, project_id=seed.project_id, after=None, limit=2
                )
                assert own is not None
                assert (
                    own.project_id == seed.project_id
                    and own.organization_id == seed.organization_id
                )
                assert own.actor.id == seed.principal_id
                observed = own.oauth_credential_facts
            case "operation-lookup":
                query = LookupOriginalOperationQuery(
                    state.installation_id,
                    seed.organization_id,
                    seed.project_id,
                    HttpMethod.POST,
                    "/v1/projects/{project_id}/grants",
                    IdempotencyKey("browser-current-facts"),
                    OperationLookupAuthority(
                        OperationLookupAuthorityFamily.PROJECT_ACTION_USE, seed.action
                    ),
                )
                lookup = await PostgresOperationLookupFactsReader(session).read(
                    access=access, query=query
                )
                assert lookup is not None
                assert lookup.installation_id == state.installation_id
                assert lookup.principal.id == seed.principal_id
                assert lookup.principal.organization_id == seed.organization_id
                assert lookup.is_project_member and lookup.has_exact_action_grant
                observed = lookup.oauth_credential_facts
            case "deletion-status":
                deletion = await PostgresDeletionStatusFactsReader(session).read(access=access)
                assert deletion is not None
                assert deletion.installation_id == state.installation_id
                assert deletion.principal.id == seed.principal_id
                assert deletion.principal.organization_id == seed.organization_id
                observed = deletion.oauth_credential_facts
            case "project-header":
                principal, project, installed, member, pending, linked, version = (
                    (await session.execute(ProjectActorQueries.header(access, seed.project_id)))
                    .tuples()
                    .one()
                )
                assert principal.id == seed.principal_id.value
                assert principal.organization_id == seed.organization_id.value
                assert project.id == seed.project_id.value
                assert installed == state.installation_id.value and member
                mapped = PostgresProjectActorMapper.action(
                    access=access,
                    principal=principal,
                    project=project,
                    member=member,
                    recovering=pending,
                    linked=linked,
                    version=version,
                    granted=False,
                )
                observed = mapped.oauth_credential_facts
            case _:
                raise AssertionError("Unknown explicit reader case.")
        assert observed is not None
        assert observed.binding_matches_actor
        assert observed.current_version == state.version


@pytest.mark.asyncio
@pytest.mark.parametrize("family", ["organization", "project", "deletion-status"])
async def test_browser_facts_refresh_after_wait_and_keep_the_callers_lock(
    database: Database, family: str
) -> None:
    """Read post-wait security facts and retain coordination until the caller finishes."""
    identity = VerifiedHumanIdentityDTO(
        IdentityAuthority("kratos:wait"), IdentitySubject(str(uuid4()))
    )
    async with database.session() as session, session.begin():
        seed = await MockAccessScenarios.seed_project_authorization(
            session, is_project_member=True, has_action_grant=True
        )
        seed = replace(seed, action=ActionId(ProjectAction.MANAGE_PROJECT_MEMBERS.value))
        await session.execute(
            update(ProjectActionGrantRow)
            .where(
                ProjectActionGrantRow.project_id == seed.project_id.value,
                ProjectActionGrantRow.recipient_principal_id == seed.principal_id.value,
            )
            .values(action=seed.action.value, can_grant=True)
        )
        session.add(
            OrganizationActionGrantRow(
                organization_id=seed.organization_id.value,
                recipient_principal_id=seed.principal_id.value,
                recipient_kind=PrincipalKind.HUMAN,
                action="create-projects",
                can_grant=True,
            )
        )
        session.add(
            HumanIdentityLinkRow(
                authority=identity.authority.value,
                subject=identity.subject.value,
                organization_id=seed.organization_id.value,
                principal_id=seed.principal_id.value,
                principal_kind=PrincipalKind.HUMAN,
            )
        )
    initial = await PostgresHumanCredentialStateInitializer(database).initialize(identity)
    assert initial.version is not None
    access = AccessContextDTO(
        seed.principal_id,
        BrowserSessionAuthenticationDTO(identity, initial.installation_id, initial.version),
    )
    ready, finish = asyncio.Event(), asyncio.Event()
    caller_pid: int | None = None

    async def read_facts() -> tuple[HumanCredentialFactsDTO | None, PrincipalStatus, bool]:
        nonlocal caller_pid
        async with database.session() as caller:
            caller_error: BaseException | None = None
            try:
                await caller.begin()
                caller_pid = await caller.scalar(select(func.pg_backend_pid(type_=Integer)))
                assert caller_pid is not None
                if family == "organization":
                    org = await PostgresOrganizationGrantManagementFactsReader(
                        caller
                    ).lock_for_management(
                        access=access,
                        organization_id=seed.organization_id,
                        recipient_principal_id=seed.principal_id,
                        action_id=ActionId("create-projects"),
                    )
                    assert org is not None and org.actor.id == seed.principal_id
                    observed = (
                        org.actor_oauth_credential_facts,
                        org.actor.status,
                        org.actor_has_pending_recovery,
                    )
                elif family == "project":
                    project = await PostgresProjectGrantChangeFactsReader(
                        caller
                    ).read_for_management(
                        access=access,
                        project_id=seed.project_id,
                        recipient_principal_id=seed.principal_id,
                        action_id=seed.action,
                    )
                    assert project is not None and project.grant.actor.id == seed.principal_id
                    observed = (
                        project.grant.oauth_credential_facts,
                        project.grant.actor.status,
                        project.grant.has_pending_recovery,
                    )
                else:
                    status = await PostgresDeletionStatusFactsReader(caller).read(access=access)
                    assert status is not None and status.principal.id == seed.principal_id
                    observed = (
                        status.oauth_credential_facts,
                        status.principal.status,
                        status.has_pending_recovery,
                    )
                ready.set()
                await finish.wait()
                return observed

            except BaseException as error:
                caller_error = error
                raise
            finally:
                try:
                    async with asyncio.timeout(3):
                        await caller.rollback()
                except BaseException as cleanup_error:
                    if caller_error is not None and cleanup_error is not caller_error:
                        raise BaseExceptionGroup(
                            "Browser fact reader and transaction cleanup failed",
                            [caller_error, cleanup_error],
                        ) from None
                    raise

    task: asyncio.Task[tuple[HumanCredentialFactsDTO | None, PrincipalStatus, bool]] | None = None
    work_error: BaseException | None = None
    async with database.session() as holder:
        try:
            await holder.begin()
            holder_pid = await holder.scalar(select(func.pg_backend_pid(type_=Integer)))
            assert holder_pid is not None
            if family == "project":
                await holder.scalar(
                    select(OrganizationRow.id)
                    .where(OrganizationRow.id == seed.organization_id.value)
                    .with_for_update()
                )
                await holder.scalar(
                    select(ProjectRow.id)
                    .where(ProjectRow.id == seed.project_id.value)
                    .with_for_update()
                )
            else:
                await holder.scalar(
                    select(OrganizationRow.id)
                    .where(OrganizationRow.id == seed.organization_id.value)
                    .with_for_update()
                )
            task = asyncio.create_task(read_facts())
            pid, name = column("pid", Integer), column("datname", String)
            activity = table("pg_stat_activity", pid, name)
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
                pytest.fail("Browser current-facts read bypassed its owning turn.")
            await PostgresIdentityRecoveryAdmissionWriter(
                holder, installation_id=initial.installation_id, authority=identity.authority
            ).reserve(
                IdentityRecoveryEventDTO(
                    IdentityRecoveryFlowId(uuid4()), identity, IdentityRecoveryEventKind.RECOVERY
                )
            )
            await holder.execute(
                update(PrincipalRow)
                .where(PrincipalRow.id == seed.principal_id.value)
                .values(status=PrincipalStatus.SUSPENDED)
            )
            async with asyncio.timeout(3):
                await holder.commit()
                while not ready.is_set():
                    if task.done():
                        await task
                        pytest.fail("Browser current-facts read ended before caller release.")
                    await asyncio.sleep(0.01)
            assert caller_pid is not None
            async with database.session() as contender:
                contender_error: BaseException | None = None
                try:
                    async with asyncio.timeout(3):
                        await contender.begin()
                        with pytest.raises(OperationalError) as unavailable:
                            if family == "project":
                                await contender.scalar(
                                    select(ProjectRow.id)
                                    .where(ProjectRow.id == seed.project_id.value)
                                    .with_for_update(nowait=True)
                                )
                            else:
                                await contender.scalar(
                                    select(OrganizationRow.id)
                                    .where(OrganizationRow.id == seed.organization_id.value)
                                    .with_for_update(nowait=True)
                                )
                        assert getattr(unavailable.value.orig, "sqlstate", None) == "55P03"
                except BaseException as error:
                    contender_error = error
                    raise
                finally:
                    try:
                        async with asyncio.timeout(3):
                            await contender.rollback()
                    except BaseException as cleanup_error:
                        if contender_error is not None and cleanup_error is not contender_error:
                            raise BaseExceptionGroup(
                                "Lock contender and transaction cleanup failed",
                                [contender_error, cleanup_error],
                            ) from None
                        raise
            finish.set()
            async with asyncio.timeout(3):
                credential, status, pending = await task
            assert credential is not None and credential.binding_matches_actor
            assert credential.current_version == HumanCredentialVersion(2)
            assert status is PrincipalStatus.SUSPENDED and pending
        except BaseException as error:
            work_error = error
            raise
        finally:
            finish.set()
            cleanup_errors: list[BaseException] = []
            try:
                async with asyncio.timeout(3):
                    await holder.rollback()
            except BaseException as error:
                cleanup_errors.append(error)
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
                        cleanup_errors.append(outcome)
                except BaseException as error:
                    if error is not work_error:
                        cleanup_errors.append(error)
            if cleanup_errors:
                raise BaseExceptionGroup(
                    "Browser facts and owned cleanup failed",
                    ([work_error] if work_error is not None else []) + cleanup_errors,
                ) from None
