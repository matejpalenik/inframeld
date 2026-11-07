"""Keep human observations stable and require distinct application-key authority."""

import os
from dataclasses import replace

import pytest
from sqlalchemy import event, update
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
from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
    HumanOAuthCredentialBindingDTO,
)
from inframeld_backend.access.application.dtos.project_action_target_dto import (
    ProjectActionTargetDTO,
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
from inframeld_backend.access.infrastructure.readers.postgres_project_action_facts_reader import (
    PostgresProjectActionFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_project_grant_change_facts_reader import (
    PostgresProjectGrantChangeFactsReader,
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
from inframeld_backend.shared.application.errors.application_errors import AccessDeniedError
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
        if isinstance(evidence, HumanOAuthCredentialBindingDTO):
            session.add(
                HumanIdentityLinkRow(
                    authority=evidence.identity.authority.value,
                    subject=evidence.identity.subject.value,
                    organization_id=seed.organization_id.value,
                    principal_id=seed.principal_id.value,
                    principal_kind=PrincipalKind.HUMAN,
                )
            )

    if isinstance(evidence, HumanOAuthCredentialBindingDTO):
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
        if isinstance(evidence, HumanOAuthCredentialBindingDTO):
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
    async with database.session() as session, session.begin():
        seed = await MockAccessScenarios.seed_project_authorization(
            session, is_project_member=True, has_action_grant=True
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
            access=AccessContextDTO(seed.principal_id, MockAuthenticationEvidence.browser()),
            action_id=seed.action,
            target=ProjectActionTargetDTO(seed.project_id),
        )

        assert facts is not None
        assert facts.principal.status is PrincipalStatus.SUSPENDED
