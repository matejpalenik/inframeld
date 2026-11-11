"""Keep recovery invalidation durable without creating a local account."""

import asyncio
import os
from uuid import uuid4

import pytest
from sqlalchemy import Integer, String, column, func, select, table, update
from sqlalchemy.dialects.postgresql import ARRAY
from tests.support.access_scenarios import MockAccessScenarios

from inframeld_backend.access.application.dtos.browser_session_authentication_dto import (
    BrowserSessionAuthenticationDTO,
)
from inframeld_backend.access.application.dtos.human_authentication_state_dto import (
    HumanAuthenticationStateDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_event_dto import (
    IdentityRecoveryEventDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.enums.human_identity_link_state import (
    HumanIdentityLinkState,
)
from inframeld_backend.access.application.enums.identity_recovery_event_kind import (
    IdentityRecoveryEventKind,
)
from inframeld_backend.access.application.errors.human_oauth_credential_rejected_error import (
    HumanOAuthCredentialRejectedError,
)
from inframeld_backend.access.application.services.principal_access_evaluation_service import (
    PrincipalAccessEvaluationService,
)
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_recovery_flow_id import (
    IdentityRecoveryFlowId,
)
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.infrastructure.readers.human_credential_state_queries import (
    HumanCredentialStateQueries,
)
from inframeld_backend.access.infrastructure.readers.postgres_human_credential_state_reader import (
    PostgresHumanCredentialStateReader,
)
from inframeld_backend.access.infrastructure.resources.postgres_identity_coordinator import (
    PostgresIdentityCoordinator,
)
from inframeld_backend.access.infrastructure.rows.human_credential_version_row import (
    HumanCredentialVersionRow,
)
from inframeld_backend.access.infrastructure.rows.human_identity_link_row import (
    HumanIdentityLinkRow,
)
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.writers.postgres_human_credential_state_initializer import (
    PostgresHumanCredentialStateInitializer,
)
from inframeld_backend.access.infrastructure.writers.postgres_identity_recovery_admission_writer import (
    PostgresIdentityRecoveryAdmissionWriter,
)
from inframeld_backend.shared.application.errors.application_errors import (
    AuthenticationRequiredError,
    DependencyUnavailableError,
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
@pytest.mark.parametrize("credential_family", ["browser", "oauth"])
async def test_facts_recheck_a_binding_after_its_recovery_block_is_released(
    database: Database, family: str, credential_family: str
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
        (
            BrowserSessionAuthenticationDTO(IDENTITY, initial.installation_id, initial.version)
            if credential_family == "browser"
            else HumanOAuthCredentialBindingDTO(IDENTITY, initial.installation_id, initial.version)
        ),
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
        expected = (
            AuthenticationRequiredError
            if credential_family == "browser"
            else HumanOAuthCredentialRejectedError
        )
        with pytest.raises(AuthenticationRequiredError) as rejection:
            PrincipalAccessEvaluationService.require_current_credential(
                access=access, principal_access=observed
            )
        assert type(rejection.value) is expected


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

    await _admit(database, IdentityRecoveryFlowId(uuid4()))
    async with database.session() as session, session.begin():
        await session.execute(delete(HumanCredentialVersionRow))
    with pytest.raises(DependencyUnavailableError):
        await PostgresHumanCredentialStateInitializer(database).initialize(IDENTITY)
    with pytest.raises(DependencyUnavailableError):
        await PostgresHumanCredentialStateInitializer(database).initialize_authentication_state(
            IDENTITY
        )
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

    from inframeld_backend.shared.infrastructure.rows.installation_identity_row import (
        InstallationIdentityRow,
    )

    async with database.session() as session, session.begin():
        await session.execute(delete(InstallationIdentityRow))
    with pytest.raises(DependencyUnavailableError):
        await PostgresHumanCredentialStateReader(database).read(IDENTITY)
    with pytest.raises(DependencyUnavailableError):
        await PostgresHumanCredentialStateInitializer(database).initialize(IDENTITY)

    with pytest.raises(DependencyUnavailableError):
        await PostgresHumanCredentialStateReader(database).read_authentication_state(IDENTITY)
    with pytest.raises(DependencyUnavailableError):
        await PostgresHumanCredentialStateInitializer(database).initialize_authentication_state(
            IDENTITY
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("family", ["action", "grant"])
@pytest.mark.parametrize(
    "wrong", ["installation", "authority", "subject", "actor_link", "version", "missing_state"]
)
@pytest.mark.parametrize("credential_family", ["browser", "oauth"])
async def test_actor_lookup_matches_every_binding_component(
    database: Database, wrong: str, family: str, credential_family: str
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
    from inframeld_backend.access.application.errors.human_oauth_credential_rejected_error import (
        HumanOAuthCredentialRejectedError,
    )
    from inframeld_backend.access.application.services.action_authorization_service import (
        ActionAuthorizationService,
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
    binding = (
        BrowserSessionAuthenticationDTO(IDENTITY, state.installation_id, state.version)
        if credential_family == "browser"
        else HumanOAuthCredentialBindingDTO(IDENTITY, state.installation_id, state.version)
    )
    expected = (
        AuthenticationRequiredError
        if credential_family == "browser"
        else HumanOAuthCredentialRejectedError
    )
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
        if family == "action":
            reader = PostgresProjectActionFactsReader(session)
            facts = await reader.read_action_facts(
                access=access, action_id=seed.action, target=ProjectActionTargetDTO(seed.project_id)
            )
            with pytest.raises(AuthenticationRequiredError) as rejection:
                await ActionAuthorizationService(reader).require_authorization(
                    access=access,
                    request=ProjectActionAuthorizationRequestDTO(seed.project_id, seed.action),
                )
            assert type(rejection.value) is expected
        else:
            grant_reader = PostgresProjectGrantChangeFactsReader(session)
            facts = await grant_reader.read_for_change(
                access=access,
                project_id=seed.project_id,
                recipient_principal_id=seed.principal_id,
                action_id=seed.action,
            )

        assert facts is not None
        assert facts.oauth_credential_facts is not None
        assert facts.oauth_credential_facts.binding_matches_actor is (
            wrong in {"version", "missing_state"}
        )
        if wrong == "version":
            assert facts.oauth_credential_facts.current_version == state.version
        else:
            assert facts.oauth_credential_facts.current_version is None

    if family == "grant":
        from tests.support.project_grant_changes import create_project_grant_change_service

        from inframeld_backend.access.application.commands.set_project_action_grant_command import (
            SetProjectActionGrantCommand,
        )
        from inframeld_backend.shared.application.dtos.idempotency_context_dto import (
            IdempotencyContextDTO,
        )
        from inframeld_backend.shared.application.enums.http_method import HttpMethod
        from inframeld_backend.shared.application.value_objects.idempotency_key import (
            IdempotencyKey,
        )

        grant_action = ActionId("create-access-groups")
        async with database.session() as session:
            with pytest.raises(AuthenticationRequiredError) as rejection:
                await create_project_grant_change_service(session).set_action_grant(
                    access=access,
                    command=SetProjectActionGrantCommand(
                        project_id=seed.project_id,
                        recipient_principal_id=seed.principal_id,
                        action_id=grant_action,
                        can_grant=False,
                        expected_access_revision=0,
                    ),
                    context=IdempotencyContextDTO(
                        method=HttpMethod.PUT,
                        requested_route=f"/v1/projects/{seed.project_id.value}/grants/{seed.principal_id.value}/{grant_action.value}",
                        key=IdempotencyKey("credential-binding-check"),
                    ),
                )
            assert type(rejection.value) is expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status", [PrincipalStatus.ACTIVE, PrincipalStatus.SUSPENDED, PrincipalStatus.RETIRED]
)
async def test_authentication_query_returns_exact_linked_state(
    database: Database, status: PrincipalStatus
) -> None:
    """Keep the raw credential prefix and the exact inactive linked human in one projection."""
    other = VerifiedHumanIdentityDTO(IDENTITY.authority, IdentitySubject("other-human"))
    async with database.session() as session, session.begin():
        await MockAccessScenarios.seed_linked_human(session, other)
        principal = await MockAccessScenarios.seed_linked_human(session, IDENTITY, status=status)
    state = await PostgresHumanCredentialStateInitializer(database).initialize(IDENTITY)
    assert state.version is not None
    async with database.session() as session:
        narrow = (
            (await session.execute(HumanCredentialStateQueries.for_identity(IDENTITY)))
            .tuples()
            .one()
        )
        assert narrow == (state.installation_id.value, state.version.value, False, False)
        rich = (
            (
                await session.execute(
                    HumanCredentialStateQueries.for_identity_with_principal(IDENTITY)
                )
            )
            .tuples()
            .one()
        )
        assert rich[:4] == narrow
        link, stored_principal = rich[4], rich[5]
        assert link is not None and stored_principal is not None
        assert (link.authority, link.subject) == (IDENTITY.authority.value, IDENTITY.subject.value)
        assert (link.principal_id, link.organization_id) == (
            principal.id.value,
            principal.organization_id.value,
        )
        assert stored_principal.id == principal.id.value
        assert stored_principal.organization_id == principal.organization_id.value
        assert stored_principal.kind == principal.kind
        assert stored_principal.status is status


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status", [PrincipalStatus.ACTIVE, PrincipalStatus.SUSPENDED, PrincipalStatus.RETIRED]
)
async def test_authentication_reader_returns_exact_linked_state(
    database: Database, status: PrincipalStatus
) -> None:
    """Return the same committed version and retired principal without borrowing another link."""
    other = VerifiedHumanIdentityDTO(IDENTITY.authority, IdentitySubject("other-human"))
    async with database.session() as session, session.begin():
        await MockAccessScenarios.seed_linked_human(session, other)
        principal = await MockAccessScenarios.seed_linked_human(session, IDENTITY, status=status)
    expected = await PostgresHumanCredentialStateInitializer(database).initialize(IDENTITY)
    assert expected.version is not None
    observed = await PostgresHumanCredentialStateReader(database).read_authentication_state(
        IDENTITY
    )
    assert observed.credential_state == expected
    assert observed.link_state is HumanIdentityLinkState.LINKED
    assert observed.linked_principal == principal


@pytest.mark.asyncio
async def test_authentication_initializer_preserves_genuine_unlinked_identity(
    database: Database,
) -> None:
    """Initialize only the credential generation, never a local admission or fabricated principal."""
    reader = PostgresHumanCredentialStateReader(database)
    absent = await reader.read(IDENTITY)
    assert absent.version is None and not absent.has_pending_recovery
    async with database.session() as session:
        principals_before = await session.scalar(select(func.count()).select_from(PrincipalRow))
        assert (
            await session.scalar(
                select(func.count())
                .select_from(HumanIdentityLinkRow)
                .where(
                    HumanIdentityLinkRow.authority == IDENTITY.authority.value,
                    HumanIdentityLinkRow.subject == IDENTITY.subject.value,
                )
            )
            == 0
        )
    observed = await PostgresHumanCredentialStateInitializer(
        database
    ).initialize_authentication_state(IDENTITY)
    assert observed.credential_state.installation_id == absent.installation_id
    assert observed.credential_state.identity == IDENTITY
    assert observed.credential_state.version is not None
    assert observed.credential_state.version.value == 1
    assert not observed.credential_state.has_pending_recovery
    assert observed.link_state is HumanIdentityLinkState.UNLINKED
    assert observed.linked_principal is None
    assert await reader.read(IDENTITY) == observed.credential_state
    async with database.session() as session:
        assert (
            await session.scalar(select(func.count()).select_from(PrincipalRow))
            == principals_before
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(HumanIdentityLinkRow)
                .where(
                    HumanIdentityLinkRow.authority == IDENTITY.authority.value,
                    HumanIdentityLinkRow.subject == IDENTITY.subject.value,
                )
            )
            == 0
        )


@pytest.mark.asyncio
async def test_rich_absent_identity_does_not_borrow_another_principal(database: Database) -> None:
    other = VerifiedHumanIdentityDTO(IDENTITY.authority, IdentitySubject("linked-other"))
    async with database.session() as session, session.begin():
        await MockAccessScenarios.seed_linked_human(session, other)
    await PostgresHumanCredentialStateInitializer(database).initialize(other)
    expected = await PostgresHumanCredentialStateReader(database).read(IDENTITY)
    assert expected.version is None
    observed = await PostgresHumanCredentialStateReader(database).read_authentication_state(
        IDENTITY
    )
    assert observed.credential_state == expected
    assert observed.link_state is HumanIdentityLinkState.UNLINKED
    assert observed.linked_principal is None


@pytest.mark.asyncio
async def test_rich_initialization_preserves_an_existing_generation_without_admission(
    database: Database,
) -> None:
    from sqlalchemy import update

    initializer = PostgresHumanCredentialStateInitializer(database)
    initial = await initializer.initialize(IDENTITY)
    async with database.session() as session, session.begin():
        await session.execute(
            update(HumanCredentialVersionRow)
            .where(
                HumanCredentialVersionRow.installation_id == initial.installation_id.value,
                HumanCredentialVersionRow.authority == IDENTITY.authority.value,
                HumanCredentialVersionRow.subject == IDENTITY.subject.value,
            )
            .values(version=7)
        )
    expected = await PostgresHumanCredentialStateReader(database).read(IDENTITY)
    assert expected.version == HumanCredentialVersion(7)
    observed = await initializer.initialize_authentication_state(IDENTITY)
    assert observed.credential_state == expected
    assert await initializer.initialize(IDENTITY) == expected
    assert observed.link_state is HumanIdentityLinkState.UNLINKED
    assert observed.linked_principal is None
    async with database.session() as session:
        assert await session.scalar(select(func.count()).select_from(PrincipalRow)) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [PrincipalStatus.SUSPENDED, PrincipalStatus.RETIRED])
async def test_narrow_initialization_observes_inactive_link_without_authorizing_it(
    database: Database, status: PrincipalStatus
) -> None:
    async with database.session() as session, session.begin():
        principal = await MockAccessScenarios.seed_linked_human(session, IDENTITY, status=status)
    initializer = PostgresHumanCredentialStateInitializer(database)
    await initializer.initialize(IDENTITY)
    await _admit(database, IdentityRecoveryFlowId(uuid4()))
    narrow = await initializer.initialize(IDENTITY)
    assert narrow.version == HumanCredentialVersion(2) and narrow.has_pending_recovery
    rich = await initializer.initialize_authentication_state(IDENTITY)
    assert rich.credential_state == narrow
    assert rich.link_state is HumanIdentityLinkState.LINKED
    assert rich.linked_principal == principal


@pytest.mark.asyncio
async def test_rich_initialization_observes_security_state_after_the_identity_turn(
    database: Database,
) -> None:
    """The initializer must observe a recovery committed while it waited, without restamping."""
    async with database.session() as session, session.begin():
        principal = await MockAccessScenarios.seed_linked_human(session, IDENTITY)
    initializer = PostgresHumanCredentialStateInitializer(database)
    initial = await initializer.initialize(IDENTITY)
    task: asyncio.Task[HumanAuthenticationStateDTO] | None = None
    work_error: BaseException | None = None
    async with database.session() as holder:
        try:
            await holder.begin()
            holder_pid = await holder.scalar(select(func.pg_backend_pid(type_=Integer)))
            assert holder_pid is not None
            await PostgresIdentityCoordinator(holder).acquire(
                installation_id=initial.installation_id, identity=IDENTITY
            )
            task = asyncio.create_task(initializer.initialize_authentication_state(IDENTITY))
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
                pytest.fail("Rich initialization bypassed its identity turn.")
            await PostgresIdentityRecoveryAdmissionWriter(
                holder, installation_id=initial.installation_id, authority=IDENTITY.authority
            ).reserve(
                IdentityRecoveryEventDTO(
                    IdentityRecoveryFlowId(uuid4()), IDENTITY, IdentityRecoveryEventKind.RECOVERY
                )
            )
            await holder.execute(
                update(PrincipalRow)
                .where(PrincipalRow.id == principal.id.value)
                .values(status=PrincipalStatus.SUSPENDED)
            )
            async with asyncio.timeout(3):
                await holder.commit()
                observed = await task
            assert observed.credential_state.version == HumanCredentialVersion(2)
            assert observed.credential_state.has_pending_recovery
            assert observed.link_state is HumanIdentityLinkState.LINKED
            assert observed.linked_principal is not None
            assert observed.linked_principal.id == principal.id
            assert observed.linked_principal.status is PrincipalStatus.SUSPENDED
        except BaseException as error:
            work_error = error
            raise
        finally:
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
                    "Rich initialization and owned cleanup failed",
                    ([work_error] if work_error is not None else []) + cleanup_errors,
                ) from None
