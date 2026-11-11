"""Verify project-action authorization reads current facts from PostgreSQL."""

import os
from uuid import uuid4

import pytest
from sqlalchemy import update
from tests.support.access_scenarios import (
    MockAccessScenarios,
    MultiProjectAuthorizationSeedDTO,
    ProjectAuthorizationSeedDTO,
)
from tests.support.application_key_scenarios import verified_application_access
from tests.support.authentication_evidence import MockAuthenticationEvidence

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.application_key_verification_profile_dto import (
    ApplicationKeyVerificationProfileDTO,
)
from inframeld_backend.access.application.dtos.browser_session_authentication_dto import (
    BrowserSessionAuthenticationDTO,
)
from inframeld_backend.access.application.dtos.project_action_authorization_request_dto import (
    ProjectActionAuthorizationRequestDTO,
)
from inframeld_backend.access.application.dtos.project_action_target_dto import (
    ProjectActionTargetDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.services.action_authorization_service import (
    ActionAuthorizationService,
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
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.readers.postgres_project_action_facts_reader import (
    PostgresProjectActionFactsReader,
)
from inframeld_backend.access.infrastructure.rows.human_identity_link_row import (
    HumanIdentityLinkRow,
)
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.writers.postgres_human_credential_state_initializer import (
    PostgresHumanCredentialStateInitializer,
)
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ResourceNotFoundError,
)
from inframeld_backend.shared.infrastructure.resources.database import Database

pytestmark = pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
    reason="Set INFRAMELD_RUN_DB_INTEGRATION=1 to run PostgreSQL integration tests",
)
APPLICATION_PROFILE = ApplicationKeyVerificationProfileDTO(
    ApplicationKeyAudience("https://api.test"), ApplicationKeyAdapter.HTTP
)


async def _capture_browser(
    database: Database, scenario: ProjectAuthorizationSeedDTO | MultiProjectAuthorizationSeedDTO
) -> AccessContextDTO:
    identity = VerifiedHumanIdentityDTO(
        IdentityAuthority("kratos:test"), IdentitySubject(str(uuid4()))
    )
    async with database.session() as session, session.begin():
        principal = await session.get(PrincipalRow, scenario.principal_id.value)
        assert principal is not None
        session.add(
            HumanIdentityLinkRow(
                authority=identity.authority.value,
                subject=identity.subject.value,
                organization_id=principal.organization_id,
                principal_id=scenario.principal_id.value,
                principal_kind=PrincipalKind.HUMAN,
            )
        )
    state = await PostgresHumanCredentialStateInitializer(database).initialize(identity)
    assert state.version is not None
    access = AccessContextDTO(
        scenario.principal_id,
        BrowserSessionAuthenticationDTO(identity, state.installation_id, state.version),
    )
    return access


@pytest.mark.asyncio
async def test_allows_member_with_exact_project_action_grant(database: Database) -> None:
    """Allow a current project member whose exact action grant is stored in PostgreSQL."""
    async with database.session() as session, session.begin():
        scenario = await MockAccessScenarios.seed_project_authorization(
            session,
            is_project_member=True,
            has_action_grant=True,
        )
    access = await _capture_browser(database, scenario)
    async with database.session() as session, session.begin():
        authorizer = ActionAuthorizationService(PostgresProjectActionFactsReader(session))
        authorization = await authorizer.require_authorization(
            access=access,
            request=ProjectActionAuthorizationRequestDTO(
                project_id=scenario.project_id, action_id=scenario.action
            ),
        )

    assert authorization.organization_id == scenario.organization_id
    assert authorization.project_id == scenario.project_id


@pytest.mark.asyncio
async def test_hides_project_from_active_nonmember(database: Database) -> None:
    """Hide an existing project from an active principal who is not its member."""
    async with database.session() as session, session.begin():
        scenario = await MockAccessScenarios.seed_project_authorization(
            session,
            is_project_member=False,
            has_action_grant=False,
        )
    access = await _capture_browser(database, scenario)
    async with database.session() as session, session.begin():
        reader = PostgresProjectActionFactsReader(session)
        authorizer = ActionAuthorizationService(reader)
        target = ProjectActionTargetDTO(project_id=scenario.project_id)

        with pytest.raises(ResourceNotFoundError):
            await authorizer.require_authorization(
                access=access,
                request=ProjectActionAuthorizationRequestDTO(
                    project_id=target.project_id, action_id=scenario.action
                ),
            )

        facts = await reader.read_action_facts(
            access=access,
            action_id=scenario.action,
            target=target,
        )

    assert facts is not None
    assert facts.principal.id == scenario.principal_id
    assert facts.principal.organization_id == scenario.organization_id
    assert facts.principal.kind is PrincipalKind.HUMAN
    assert facts.principal.status is PrincipalStatus.ACTIVE
    assert facts.has_pending_recovery is False
    assert isinstance(access.authentication_evidence, BrowserSessionAuthenticationDTO)
    assert facts.oauth_credential_facts is not None
    assert facts.oauth_credential_facts.binding_matches_actor
    assert facts.oauth_credential_facts.current_version == access.authentication_evidence.version
    assert facts.project_status is ProjectStatus.ACTIVE
    assert facts.is_project_member is False
    assert facts.has_exact_action_grant is False


@pytest.mark.asyncio
async def test_denies_project_member_without_exact_action_grant(database: Database) -> None:
    """Deny a visible project member who lacks the requested action grant."""
    async with database.session() as session, session.begin():
        scenario = await MockAccessScenarios.seed_project_authorization(
            session,
            is_project_member=True,
            has_action_grant=False,
        )
    access = await _capture_browser(database, scenario)
    async with database.session() as session, session.begin():
        authorizer = ActionAuthorizationService(PostgresProjectActionFactsReader(session))

        with pytest.raises(AccessDeniedError):
            await authorizer.require_authorization(
                access=access,
                request=ProjectActionAuthorizationRequestDTO(
                    project_id=scenario.project_id, action_id=scenario.action
                ),
            )


@pytest.mark.asyncio
async def test_hides_suspended_project_member_even_with_an_action_grant(
    database: Database,
) -> None:
    """Stop a suspended principal even when its old membership and grant remain stored."""
    async with database.session() as session, session.begin():
        scenario = await MockAccessScenarios.seed_project_authorization(
            session,
            is_project_member=True,
            has_action_grant=True,
            principal_status=PrincipalStatus.SUSPENDED,
        )
    access = await _capture_browser(database, scenario)
    async with database.session() as session, session.begin():
        authorizer = ActionAuthorizationService(PostgresProjectActionFactsReader(session))

        with pytest.raises(ResourceNotFoundError):
            await authorizer.require_authorization(
                access=access,
                request=ProjectActionAuthorizationRequestDTO(
                    project_id=scenario.project_id, action_id=scenario.action
                ),
            )


@pytest.mark.asyncio
async def test_project_action_grant_does_not_carry_to_another_project(database: Database) -> None:
    """Keep Alice's exact action grant limited to the project where it was assigned."""
    async with database.session() as session, session.begin():
        scenario = await MockAccessScenarios.seed_multi_project_authorization(session)
    access = await _capture_browser(database, scenario)
    async with database.session() as session, session.begin():
        authorizer = ActionAuthorizationService(PostgresProjectActionFactsReader(session))

        await authorizer.require_authorization(
            access=access,
            request=ProjectActionAuthorizationRequestDTO(
                project_id=scenario.granted_project_id, action_id=scenario.action
            ),
        )

        with pytest.raises(AccessDeniedError):
            await authorizer.require_authorization(
                access=access,
                request=ProjectActionAuthorizationRequestDTO(
                    project_id=scenario.ungranted_project_id, action_id=scenario.action
                ),
            )


@pytest.mark.asyncio
async def test_allows_application_principal_with_its_exact_project_action_grant(
    database: Database,
) -> None:
    """Apply current project action checks to an application principal as well as a human."""
    action = ActionId(ProjectAction.INSPECT_FEEDBACK.value)
    async with database.session() as session, session.begin():
        scenario = await MockAccessScenarios.seed_project_authorization(
            session,
            is_project_member=True,
            has_action_grant=True,
            principal_kind=PrincipalKind.APPLICATION,
        )
        await session.execute(
            update(ProjectActionGrantRow)
            .where(
                ProjectActionGrantRow.project_id == scenario.project_id.value,
                ProjectActionGrantRow.recipient_principal_id == scenario.principal_id.value,
            )
            .values(action=action.value)
        )
    access = await verified_application_access(
        database,
        principal_id=scenario.principal_id,
        organization_id=scenario.organization_id,
        project_id=scenario.project_id,
        profile=APPLICATION_PROFILE,
    )
    async with database.session() as session, session.begin():
        authorizer = ActionAuthorizationService(
            PostgresProjectActionFactsReader(session, application_key_profile=APPLICATION_PROFILE)
        )

        authorized = await authorizer.require_authorization(
            access=access,
            request=ProjectActionAuthorizationRequestDTO(
                project_id=scenario.project_id, action_id=action
            ),
        )
    assert authorized.organization_id == scenario.organization_id
    assert authorized.project_id == scenario.project_id


@pytest.mark.asyncio
async def test_missing_project_returns_no_facts_and_is_hidden(database: Database) -> None:
    """Keep an absent project on the same not-found path as other hidden targets."""
    async with database.session() as session, session.begin():
        caller = await MockAccessScenarios.seed_project_authorization(
            session,
            is_project_member=True,
            has_action_grant=True,
        )
        reader = PostgresProjectActionFactsReader(session)
        access = AccessContextDTO(
            caller.principal_id, authentication_evidence=MockAuthenticationEvidence.browser()
        )
        target = ProjectActionTargetDTO(ProjectId(uuid4()))

        facts = await reader.read_action_facts(
            access=access,
            action_id=caller.action,
            target=target,
        )

        assert facts is None

        with pytest.raises(ResourceNotFoundError):
            await ActionAuthorizationService(reader).require_authorization(
                access=access,
                request=ProjectActionAuthorizationRequestDTO(
                    project_id=target.project_id, action_id=caller.action
                ),
            )


@pytest.mark.asyncio
async def test_another_organizations_project_is_hidden(database: Database) -> None:
    """Keep organization scoping in SQL even when both projects and grants exist."""
    async with database.session() as session, session.begin():
        caller = await MockAccessScenarios.seed_project_authorization(
            session,
            is_project_member=True,
            has_action_grant=True,
        )
        foreign = await MockAccessScenarios.seed_project_authorization(
            session,
            is_project_member=True,
            has_action_grant=True,
        )
        reader = PostgresProjectActionFactsReader(session)
        access = AccessContextDTO(
            caller.principal_id, authentication_evidence=MockAuthenticationEvidence.browser()
        )
        target = ProjectActionTargetDTO(foreign.project_id)

        facts = await reader.read_action_facts(
            access=access,
            action_id=caller.action,
            target=target,
        )

        assert facts is None

        with pytest.raises(ResourceNotFoundError):
            await ActionAuthorizationService(reader).require_authorization(
                access=access,
                request=ProjectActionAuthorizationRequestDTO(
                    project_id=target.project_id, action_id=caller.action
                ),
            )
