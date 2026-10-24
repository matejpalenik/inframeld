"""Keep recovery invalidation durable without creating a local account."""

import asyncio
import os
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from tests.support.authentication_evidence import MockAuthenticationEvidence

from inframeld_backend.access.application.dtos.identity_recovery_event_dto import (
    IdentityRecoveryEventDTO,
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
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_recovery_flow_id import (
    IdentityRecoveryFlowId,
)
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.infrastructure.readers.postgres_human_credential_state_reader import (
    PostgresHumanCredentialStateReader,
)
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.writers.postgres_human_credential_state_initializer import (
    PostgresHumanCredentialStateInitializer,
)
from inframeld_backend.access.infrastructure.writers.postgres_identity_recovery_admission_writer import (
    PostgresIdentityRecoveryAdmissionWriter,
)
from inframeld_backend.shared.infrastructure.readers.postgres_installation_identity_reader import (
    PostgresInstallationIdentityReader,
)
from inframeld_backend.shared.infrastructure.resources.database import Database

pytestmark = pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
    reason="Requires PostgreSQL integration services",
)
IDENTITY = VerifiedHumanIdentityDTO(IdentityAuthority("kratos:test"), IdentitySubject("alice"))


async def _admit(database: Database, flow: IdentityRecoveryFlowId) -> None:
    installation = await PostgresInstallationIdentityReader(database).read()
    async with database.session() as session, session.begin():
        await PostgresIdentityRecoveryAdmissionWriter(
            session, installation_id=installation, authority=IDENTITY.authority
        ).reserve(IdentityRecoveryEventDTO(flow, IDENTITY, IdentityRecoveryEventKind.RECOVERY))


@pytest.mark.asyncio
async def test_initialization_is_durable_and_does_not_admit_a_human(database: Database) -> None:
    initializer = PostgresHumanCredentialStateInitializer(database)
    reader = PostgresHumanCredentialStateReader(database)
    assert (await reader.read(IDENTITY)).version is None
    initial = await initializer.initialize(IDENTITY)
    assert initial.version is not None and initial.version.value == 1
    assert not initial.has_pending_recovery
    assert await initializer.initialize(IDENTITY) == initial
    assert await reader.read(IDENTITY) == initial
    async with database.session() as session:
        assert await session.scalar(select(func.count()).select_from(PrincipalRow)) == 0


@pytest.mark.asyncio
async def test_each_distinct_recovery_advances_once(database: Database) -> None:
    await PostgresHumanCredentialStateInitializer(database).initialize(IDENTITY)
    flow = IdentityRecoveryFlowId(uuid4())
    await _admit(database, flow)
    await _admit(database, flow)
    state = await PostgresHumanCredentialStateReader(database).read(IDENTITY)
    assert state.version is not None and state.version.value == 2
    assert state.has_pending_recovery
    await _admit(database, IdentityRecoveryFlowId(uuid4()))
    assert (
        await PostgresHumanCredentialStateReader(database).read(IDENTITY)
    ).version != state.version


@pytest.mark.asyncio
async def test_concurrent_duplicate_admission_advances_once(database: Database) -> None:
    flow = IdentityRecoveryFlowId(uuid4())
    await asyncio.gather(*(_admit(database, flow) for _ in range(3)))
    state = await PostgresHumanCredentialStateReader(database).read(IDENTITY)
    assert state.version is not None and state.version.value == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("family", ["action", "grant"])
async def test_facts_recheck_a_binding_after_its_recovery_block_is_released(
    database: Database, family: str
) -> None:
    from sqlalchemy import update
    from tests.support.access_scenarios import MockAccessScenarios

    from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
    from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
        HumanOAuthCredentialBindingDTO,
    )
    from inframeld_backend.access.application.dtos.project_action_target_dto import (
        ProjectActionTargetDTO,
    )
    from inframeld_backend.access.domain.enums.identity_recovery_cleanup_state import (
        IdentityRecoveryCleanupState,
    )
    from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
    from inframeld_backend.access.infrastructure.readers.postgres_project_action_facts_reader import (
        PostgresProjectActionFactsReader,
    )
    from inframeld_backend.access.infrastructure.readers.postgres_project_grant_change_facts_reader import (
        PostgresProjectGrantChangeFactsReader,
    )
    from inframeld_backend.access.infrastructure.rows.human_identity_link_row import (
        HumanIdentityLinkRow,
    )
    from inframeld_backend.access.infrastructure.rows.identity_recovery_admission_row import (
        IdentityRecoveryAdmissionRow,
    )

    async with database.session() as session, session.begin():
        seed = await MockAccessScenarios.seed_project_authorization(
            session, is_project_member=True, has_action_grant=True
        )
        session.add(
            HumanIdentityLinkRow(
                authority=IDENTITY.authority.value,
                subject=IDENTITY.subject.value,
                organization_id=seed.organization_id.value,
                principal_id=seed.principal_id.value,
                principal_kind=PrincipalKind.HUMAN,
            )
        )
    initial = await PostgresHumanCredentialStateInitializer(database).initialize(IDENTITY)
    assert initial.version is not None
    access = AccessContextDTO(
        seed.principal_id,
        HumanOAuthCredentialBindingDTO(IDENTITY, initial.installation_id, initial.version),
    )
    await _admit(database, IdentityRecoveryFlowId(uuid4()))
    # Fixture-only release isolates the version rule from provider qualification.
    async with database.session() as session, session.begin():
        await session.execute(
            update(IdentityRecoveryAdmissionRow).values(
                kratos_cleanup_state=IdentityRecoveryCleanupState.CONFIRMED,
                hydra_cleanup_state=IdentityRecoveryCleanupState.CONFIRMED,
                released_at=func.now(),
            )
        )
    async with database.session() as session, session.begin():
        if family == "action":
            facts = await PostgresProjectActionFactsReader(session).read_action_facts(
                access=access, action_id=seed.action, target=ProjectActionTargetDTO(seed.project_id)
            )
            assert facts is not None
            principal = facts.principal
        else:
            facts = await PostgresProjectGrantChangeFactsReader(session).read_for_change(
                access=access,
                project_id=seed.project_id,
                recipient_principal_id=seed.principal_id,
                action_id=seed.action,
            )
            assert facts is not None
            principal = facts.actor
        assert not facts.has_pending_recovery
        assert facts.oauth_credential_facts is not None
        assert facts.oauth_credential_facts.binding_matches_actor
        assert facts.oauth_credential_facts.current_version is not None
        assert facts.oauth_credential_facts.current_version.value == 2
        observed = PrincipalAccessEvaluationService.evaluate(
            access=access,
            principal=principal,
            has_pending_recovery=facts.has_pending_recovery,
            oauth_credential_facts=facts.oauth_credential_facts,
        )
        assert not observed.credential_is_current


@pytest.mark.asyncio
async def test_distinct_concurrent_recoveries_preserve_every_invalidation(
    database: Database,
) -> None:
    await PostgresHumanCredentialStateInitializer(database).initialize(IDENTITY)
    bob = VerifiedHumanIdentityDTO(IDENTITY.authority, IdentitySubject("bob"))
    before_bob = await PostgresHumanCredentialStateInitializer(database).initialize(bob)
    await asyncio.gather(*(_admit(database, IdentityRecoveryFlowId(uuid4())) for _ in range(4)))
    state = await PostgresHumanCredentialStateReader(database).read(IDENTITY)
    assert state.version is not None and state.version.value == 5
    assert await PostgresHumanCredentialStateReader(database).read(bob) == before_bob


@pytest.mark.asyncio
@pytest.mark.parametrize("cancelled", [False, True])
async def test_failure_before_commit_rolls_back_block_and_version(
    database: Database, cancelled: bool
) -> None:
    from inframeld_backend.access.infrastructure.rows.identity_recovery_admission_row import (
        IdentityRecoveryAdmissionRow,
    )

    before = await PostgresHumanCredentialStateInitializer(database).initialize(IDENTITY)
    error = asyncio.CancelledError if cancelled else RuntimeError
    with pytest.raises(error):
        async with database.session() as session, session.begin():
            await PostgresIdentityRecoveryAdmissionWriter(
                session, installation_id=before.installation_id, authority=IDENTITY.authority
            ).reserve(
                IdentityRecoveryEventDTO(
                    IdentityRecoveryFlowId(uuid4()), IDENTITY, IdentityRecoveryEventKind.RECOVERY
                )
            )
            raise error()
    assert await PostgresHumanCredentialStateReader(database).read(IDENTITY) == before
    async with database.session() as session:
        assert (
            await session.scalar(select(func.count()).select_from(IdentityRecoveryAdmissionRow))
            == 0
        )


@pytest.mark.asyncio
async def test_missing_version_with_recovery_history_cannot_be_reinitialized(
    database: Database,
) -> None:
    from sqlalchemy import delete

    from inframeld_backend.access.infrastructure.rows.human_credential_version_row import (
        HumanCredentialVersionRow,
    )
    from inframeld_backend.shared.application.errors.application_errors import (
        DependencyUnavailableError,
    )

    await _admit(database, IdentityRecoveryFlowId(uuid4()))
    async with database.session() as session, session.begin():
        await session.execute(delete(HumanCredentialVersionRow))
    with pytest.raises(DependencyUnavailableError):
        await PostgresHumanCredentialStateInitializer(database).initialize(IDENTITY)
    with pytest.raises(DependencyUnavailableError):
        await _admit(database, IdentityRecoveryFlowId(uuid4()))
    assert (await PostgresHumanCredentialStateReader(database).read(IDENTITY)).version is None


@pytest.mark.asyncio
async def test_version_overflow_cannot_commit_a_new_recovery(database: Database) -> None:
    from sqlalchemy import update

    from inframeld_backend.access.infrastructure.rows.human_credential_version_row import (
        HumanCredentialVersionRow,
    )
    from inframeld_backend.access.infrastructure.rows.identity_recovery_admission_row import (
        IdentityRecoveryAdmissionRow,
    )
    from inframeld_backend.shared.application.errors.application_errors import (
        DependencyUnavailableError,
    )

    await PostgresHumanCredentialStateInitializer(database).initialize(IDENTITY)
    async with database.session() as session, session.begin():
        await session.execute(update(HumanCredentialVersionRow).values(version=2**63 - 1))
    with pytest.raises(DependencyUnavailableError):
        await _admit(database, IdentityRecoveryFlowId(uuid4()))
    async with database.session() as session:
        assert (
            await session.scalar(select(func.count()).select_from(IdentityRecoveryAdmissionRow))
            == 0
        )
        assert await session.scalar(select(HumanCredentialVersionRow.version)) == 2**63 - 1


@pytest.mark.asyncio
async def test_initialization_racing_admission_cannot_erase_invalidation(
    database: Database,
) -> None:
    initializer = PostgresHumanCredentialStateInitializer(database)
    await asyncio.gather(
        initializer.initialize(IDENTITY),
        _admit(database, IdentityRecoveryFlowId(uuid4())),
        initializer.initialize(IDENTITY),
    )
    state = await PostgresHumanCredentialStateReader(database).read(IDENTITY)
    assert state.version is not None and state.version.value == 2
    assert state.has_pending_recovery


@pytest.mark.asyncio
async def test_missing_installation_never_looks_like_an_uninitialized_identity(
    database: Database,
) -> None:
    from sqlalchemy import delete

    from inframeld_backend.shared.application.errors.application_errors import (
        DependencyUnavailableError,
    )
    from inframeld_backend.shared.infrastructure.rows.installation_identity_row import (
        InstallationIdentityRow,
    )

    async with database.session() as session, session.begin():
        await session.execute(delete(InstallationIdentityRow))
    with pytest.raises(DependencyUnavailableError):
        await PostgresHumanCredentialStateReader(database).read(IDENTITY)
    with pytest.raises(DependencyUnavailableError):
        await PostgresHumanCredentialStateInitializer(database).initialize(IDENTITY)


@pytest.mark.asyncio
@pytest.mark.parametrize("family", ["action", "grant"])
@pytest.mark.parametrize(
    "wrong", ["installation", "authority", "subject", "actor_link", "version", "missing_state"]
)
async def test_actor_lookup_matches_every_binding_component(
    database: Database, wrong: str, family: str
) -> None:
    from dataclasses import replace
    from uuid import UUID

    from sqlalchemy import delete, update
    from tests.support.access_scenarios import MockAccessScenarios

    from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
    from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
        HumanOAuthCredentialBindingDTO,
    )
    from inframeld_backend.access.application.dtos.project_action_authorization_request_dto import (
        ProjectActionAuthorizationRequestDTO,
    )
    from inframeld_backend.access.application.dtos.project_action_target_dto import (
        ProjectActionTargetDTO,
    )
    from inframeld_backend.access.application.dtos.project_use_only_grant_authorization_request_dto import (
        ProjectUseOnlyGrantAuthorizationRequestDTO,
    )
    from inframeld_backend.access.application.errors.human_oauth_credential_rejected_error import (
        HumanOAuthCredentialRejectedError,
    )
    from inframeld_backend.access.application.services.action_authorization_service import (
        ActionAuthorizationService,
    )
    from inframeld_backend.access.application.services.project_grant_authorization_service import (
        ProjectGrantAuthorizationService,
    )
    from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
    from inframeld_backend.access.domain.value_objects.human_credential_version import (
        HumanCredentialVersion,
    )
    from inframeld_backend.access.infrastructure.readers.postgres_project_action_facts_reader import (
        PostgresProjectActionFactsReader,
    )
    from inframeld_backend.access.infrastructure.readers.postgres_project_grant_change_facts_reader import (
        PostgresProjectGrantChangeFactsReader,
    )
    from inframeld_backend.access.infrastructure.rows.human_credential_version_row import (
        HumanCredentialVersionRow,
    )
    from inframeld_backend.access.infrastructure.rows.human_identity_link_row import (
        HumanIdentityLinkRow,
    )
    from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId

    async with database.session() as session, session.begin():
        seed = await MockAccessScenarios.seed_project_authorization(
            session, is_project_member=True, has_action_grant=True
        )
        session.add(
            HumanIdentityLinkRow(
                authority=IDENTITY.authority.value,
                subject=IDENTITY.subject.value,
                organization_id=seed.organization_id.value,
                principal_id=seed.principal_id.value,
                principal_kind=PrincipalKind.HUMAN,
            )
        )
    state = await PostgresHumanCredentialStateInitializer(database).initialize(IDENTITY)
    assert state.version is not None
    binding = HumanOAuthCredentialBindingDTO(IDENTITY, state.installation_id, state.version)
    if wrong == "installation":
        binding = replace(binding, installation_id=InstallationId(UUID(int=999)))
    elif wrong == "authority":
        binding = replace(binding, identity=replace(IDENTITY, authority=IdentityAuthority("other")))
    elif wrong == "subject":
        binding = replace(binding, identity=replace(IDENTITY, subject=IdentitySubject("bob")))
    elif wrong == "version":
        binding = replace(binding, version=HumanCredentialVersion(2))
    elif wrong == "actor_link":
        async with database.session() as session, session.begin():
            bob = await MockAccessScenarios.seed_linked_human(
                session, replace(IDENTITY, subject=IdentitySubject("bob"))
            )
            await session.execute(
                update(HumanIdentityLinkRow)
                .where(
                    HumanIdentityLinkRow.authority == IDENTITY.authority.value,
                    HumanIdentityLinkRow.subject == IDENTITY.subject.value,
                )
                .values(principal_id=bob.id.value, organization_id=bob.organization_id.value)
            )
    else:
        async with database.session() as session, session.begin():
            await session.execute(delete(HumanCredentialVersionRow))
    if wrong in {"authority", "subject"}:
        async with database.session() as session, session.begin():
            await MockAccessScenarios.seed_linked_human(session, binding.identity)
        await PostgresHumanCredentialStateInitializer(database).initialize(binding.identity)
    async with database.session() as session, session.begin():
        access = AccessContextDTO(seed.principal_id, binding)
        browser_access = AccessContextDTO(
            seed.principal_id, authentication_evidence=MockAuthenticationEvidence.browser()
        )
        if family == "action":
            reader = PostgresProjectActionFactsReader(session)
            facts = await reader.read_action_facts(
                access=access, action_id=seed.action, target=ProjectActionTargetDTO(seed.project_id)
            )
            with pytest.raises(HumanOAuthCredentialRejectedError):
                await ActionAuthorizationService(reader).require_authorization(
                    access=access,
                    request=ProjectActionAuthorizationRequestDTO(seed.project_id, seed.action),
                )
            cookie_facts = await reader.read_action_facts(
                access=browser_access,
                action_id=seed.action,
                target=ProjectActionTargetDTO(seed.project_id),
            )
            assert cookie_facts is not None
            assert cookie_facts.oauth_credential_facts is None
        else:
            grant_reader = PostgresProjectGrantChangeFactsReader(session)
            facts = await grant_reader.read_for_change(
                access=access,
                project_id=seed.project_id,
                recipient_principal_id=seed.principal_id,
                action_id=seed.action,
            )
            with pytest.raises(HumanOAuthCredentialRejectedError):
                await ProjectGrantAuthorizationService(grant_reader).require_authorization(
                    access=access,
                    request=ProjectUseOnlyGrantAuthorizationRequestDTO(
                        seed.project_id, seed.principal_id, seed.action
                    ),
                )
            cookie_grant_facts = await grant_reader.read_for_change(
                access=browser_access,
                project_id=seed.project_id,
                recipient_principal_id=seed.principal_id,
                action_id=seed.action,
            )
            assert cookie_grant_facts is not None
            assert cookie_grant_facts.oauth_credential_facts is None

        assert facts is not None
        assert facts.oauth_credential_facts is not None
        assert facts.oauth_credential_facts.binding_matches_actor is (
            wrong in {"version", "missing_state"}
        )
        if wrong == "version":
            assert facts.oauth_credential_facts.current_version == state.version
        else:
            assert facts.oauth_credential_facts.current_version is None
