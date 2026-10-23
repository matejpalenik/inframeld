"""Verify recovery admission against current authorization and grant transactions."""

import asyncio
import os
from dataclasses import dataclass
from typing import override
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import ARRAY, Integer, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from tests.support.access_scenarios import MockAccessScenarios, ProjectAuthorizationSeedDTO
from tests.support.project_grant_changes import create_project_grant_change_service

from inframeld_backend.access.application.commands.assign_project_use_only_grant_command import (
    AssignProjectUseOnlyGrantCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.identity_recovery_event_dto import (
    IdentityRecoveryEventDTO,
)
from inframeld_backend.access.application.dtos.project_action_authorization_request_dto import (
    ProjectActionAuthorizationRequestDTO,
)
from inframeld_backend.access.application.dtos.project_action_target_dto import (
    ProjectActionTargetDTO,
)
from inframeld_backend.access.application.dtos.project_grant_authorization_dto import (
    ProjectGrantAuthorizationDTO,
)
from inframeld_backend.access.application.dtos.project_use_only_grant_assigned_audit_event_dto import (
    ProjectUseOnlyGrantAssignedAuditEventDTO,
)
from inframeld_backend.access.application.dtos.project_use_only_grant_authorization_request_dto import (
    ProjectUseOnlyGrantAuthorizationRequestDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.enums.identity_recovery_event_kind import (
    IdentityRecoveryEventKind,
)
from inframeld_backend.access.application.protocols.audit_event_writer import AuditEventWriter
from inframeld_backend.access.application.protocols.project_grant_authorizer import (
    ProjectGrantAuthorizer,
)
from inframeld_backend.access.application.services.action_authorization_service import (
    ActionAuthorizationService,
)
from inframeld_backend.access.application.services.identity_recovery_admission_service import (
    IdentityRecoveryAdmissionService,
)
from inframeld_backend.access.application.services.project_grant_authorization_service import (
    ProjectGrantAuthorizationService,
)
from inframeld_backend.access.domain.enums.identity_recovery_cleanup_state import (
    IdentityRecoveryCleanupState,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_recovery_flow_id import (
    IdentityRecoveryFlowId,
)
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.infrastructure.readers.postgres_principal_recovery_block_reader import (
    PostgresPrincipalRecoveryBlockReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_project_action_facts_reader import (
    PostgresProjectActionFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_project_grant_change_facts_reader import (
    PostgresProjectGrantChangeFactsReader,
)
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.access.infrastructure.rows.human_identity_link_row import (
    HumanIdentityLinkRow,
)
from inframeld_backend.access.infrastructure.rows.identity_recovery_admission_row import (
    IdentityRecoveryAdmissionRow,
)
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.project_membership_row import ProjectMembershipRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.access.infrastructure.writers.postgres_audit_event_writer import (
    PostgresAuditEventWriter,
)
from inframeld_backend.access.infrastructure.writers.postgres_identity_recovery_admission_writer import (
    PostgresIdentityRecoveryAdmissionWriter,
)
from inframeld_backend.shared.application.dtos.accepted_async_operation_dto import (
    AcceptedAsyncOperationDTO,
)
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.dtos.new_operation_reservation_dto import (
    NewOperationReservationDTO,
)
from inframeld_backend.shared.application.dtos.operation_admission_context_dto import (
    OperationAdmissionContextDTO,
)
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ConflictError,
    DependencyUnavailableError,
)
from inframeld_backend.shared.application.protocols.operation_idempotency import (
    OperationIdempotency,
)
from inframeld_backend.shared.application.services.idempotency_service import IdempotencyService
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.infrastructure.readers.postgres_installation_identity_reader import (
    PostgresInstallationIdentityReader,
)
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)
from inframeld_backend.shared.infrastructure.rows.installation_identity_row import (
    InstallationIdentityRow,
)
from inframeld_backend.shared.infrastructure.writers.postgres_operation_reservation_writer import (
    PostgresOperationReservationWriter,
)

pytestmark = pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
    reason="Requires PostgreSQL integration services",
)

ACTION = ActionId("create-access-groups")
KEY = IdempotencyKey("grant-during-recovery")


@dataclass(frozen=True, slots=True)
class RecoveryAuthorizationScenarioDTO:
    seed: ProjectAuthorizationSeedDTO
    identity: VerifiedHumanIdentityDTO
    installation_id: InstallationId
    recipient_id: PrincipalId


@dataclass(frozen=True, slots=True)
class GrantEffectsDTO:
    grants: int
    audit_events: int
    reservations: int
    revision: int


@pytest_asyncio.fixture
async def scenario(database: Database) -> RecoveryAuthorizationScenarioDTO:
    identity = VerifiedHumanIdentityDTO(
        IdentityAuthority("kratos:test"),
        IdentitySubject(str(uuid4())),
    )
    installation_id = await PostgresInstallationIdentityReader(database).read()
    recipient_id = PrincipalId(uuid4())

    async with database.session() as session, session.begin():
        seed = await MockAccessScenarios.seed_project_authorization(
            session,
            is_project_member=True,
            has_action_grant=False,
        )
        session.add(
            PrincipalRow(
                id=recipient_id.value,
                organization_id=seed.organization_id.value,
                kind=PrincipalKind.HUMAN,
                status=PrincipalStatus.ACTIVE,
                display_name="Bob",
            )
        )
        await session.flush()

        session.add_all(
            [
                HumanIdentityLinkRow(
                    authority=identity.authority.value,
                    subject=identity.subject.value,
                    organization_id=seed.organization_id.value,
                    principal_id=seed.principal_id.value,
                    principal_kind=PrincipalKind.HUMAN,
                ),
                ProjectMembershipRow(
                    project_id=seed.project_id.value,
                    principal_id=recipient_id.value,
                    organization_id=seed.organization_id.value,
                    principal_kind=PrincipalKind.HUMAN,
                ),
                ProjectActionGrantRow(
                    project_id=seed.project_id.value,
                    recipient_principal_id=seed.principal_id.value,
                    recipient_kind=PrincipalKind.HUMAN,
                    action=ACTION.value,
                    can_grant=True,
                ),
            ]
        )

    return RecoveryAuthorizationScenarioDTO(
        seed,
        identity,
        installation_id,
        recipient_id,
    )


async def _admit(
    session: AsyncSession,
    scenario: RecoveryAuthorizationScenarioDTO,
) -> OperationId:
    return await IdentityRecoveryAdmissionService(
        PostgresIdentityRecoveryAdmissionWriter(
            session,
            installation_id=scenario.installation_id,
            authority=scenario.identity.authority,
        )
    ).admit(
        IdentityRecoveryEventDTO(
            flow_id=IdentityRecoveryFlowId(uuid4()),
            identity=scenario.identity,
            event_kind=IdentityRecoveryEventKind.RECOVERY,
        )
    )


async def _assign(
    session: AsyncSession,
    scenario: RecoveryAuthorizationScenarioDTO,
    *,
    key: IdempotencyKey = KEY,
    expected_revision: int = 0,
    authorizer: ProjectGrantAuthorizer | None = None,
    audit_events: AuditEventWriter | None = None,
    idempotency: OperationIdempotency | None = None,
) -> CompletedSynchronousOperationDTO:
    return await create_project_grant_change_service(
        session, authorizer=authorizer, audit_events=audit_events, idempotency=idempotency
    ).assign_use_only(
        access=AccessContextDTO(scenario.seed.principal_id),
        context=OperationAdmissionContextDTO(
            method="POST", requested_route="/v1/projects/{project_id}/grants", key=key
        ),
        command=AssignProjectUseOnlyGrantCommand(
            project_id=scenario.seed.project_id,
            recipient_principal_id=scenario.recipient_id,
            action_id=ACTION,
            expected_access_revision=expected_revision,
        ),
    )


async def _effects(
    database: Database,
    scenario: RecoveryAuthorizationScenarioDTO,
) -> GrantEffectsDTO:
    async with database.session() as session:
        grants = (
            await session.execute(
                select(func.count())
                .select_from(ProjectActionGrantRow)
                .where(
                    ProjectActionGrantRow.project_id == scenario.seed.project_id.value,
                    ProjectActionGrantRow.recipient_principal_id == scenario.recipient_id.value,
                    ProjectActionGrantRow.action == ACTION.value,
                )
            )
        ).scalar_one()

        audit_events = (
            await session.execute(
                select(func.count())
                .select_from(AccessAuditEventRow)
                .where(
                    AccessAuditEventRow.project_id == scenario.seed.project_id.value,
                    AccessAuditEventRow.actor_principal_id == scenario.seed.principal_id.value,
                )
            )
        ).scalar_one()

        reservations = (
            await session.execute(
                select(func.count())
                .select_from(IdempotencyReservationRow)
                .where(
                    IdempotencyReservationRow.project_id == scenario.seed.project_id.value,
                    IdempotencyReservationRow.principal_id == scenario.seed.principal_id.value,
                )
            )
        ).scalar_one()

        revision = (
            await session.execute(
                select(ProjectRow.access_revision).where(
                    ProjectRow.id == scenario.seed.project_id.value
                )
            )
        ).scalar_one()

    return GrantEffectsDTO(grants, audit_events, reservations, revision)


async def _backend_pid(session: AsyncSession) -> int:
    return (await session.execute(select(func.pg_backend_pid().cast(Integer)))).scalar_one()


async def _wait_until_database_blocks(database: Database, pid: int) -> None:
    """Observe a PostgreSQL lock wait before allowing the other transaction to commit."""
    async with asyncio.timeout(2):
        while True:
            async with database.session() as observer:
                blockers = await observer.scalar(
                    select(func.pg_blocking_pids(pid).cast(ARRAY(Integer)))
                )

            if blockers:
                return

            await asyncio.sleep(0.01)


class MockControlledProjectGrantAuthorizer(ProjectGrantAuthorizer):
    """Observe or pause real authorization after the service has begun its transaction."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        pid_ready: asyncio.Future[int] | None = None,
        authorized: asyncio.Event | None = None,
        release: asyncio.Event | None = None,
    ) -> None:
        self._session = session
        self._delegate = ProjectGrantAuthorizationService(
            PostgresProjectGrantChangeFactsReader(session)
        )
        self._pid_ready = pid_ready
        self._authorized = authorized
        self._release = release

    @override
    async def require_authorization(
        self, *, access: AccessContextDTO, request: ProjectUseOnlyGrantAuthorizationRequestDTO
    ) -> ProjectGrantAuthorizationDTO:
        if self._pid_ready is not None:
            self._pid_ready.set_result(await _backend_pid(self._session))
        result = await self._delegate.require_authorization(access=access, request=request)
        if self._authorized is not None:
            self._authorized.set()
        if self._release is not None:
            await self._release.wait()
        return result


class MockControlledAuditEventWriter(AuditEventWriter):
    """Inject a failure or cancellation after real audit SQL has been flushed."""

    def __init__(self, session: AsyncSession, *, fail: bool = False, pause: bool = False) -> None:
        self._delegate = PostgresAuditEventWriter(session)
        self._fail = fail
        self._pause = pause
        self.appended = asyncio.Event()
        self.release = asyncio.Event()

    @override
    async def append(self, event: ProjectUseOnlyGrantAssignedAuditEventDTO) -> None:
        await self._delegate.append(event)
        self.appended.set()
        if self._fail:
            raise RuntimeError("injected audit failure")
        if self._pause:
            await self.release.wait()


class MockFailingCompletion(IdempotencyService):
    @override
    async def record_completed_result(
        self, operation: NewOperationReservationDTO, *, replay_kind: OperationReplayKind
    ) -> CompletedSynchronousOperationDTO | AcceptedAsyncOperationDTO:
        await super().record_completed_result(operation, replay_kind=replay_kind)
        raise RuntimeError("injected completion failure")


@pytest.mark.asyncio
async def test_existing_context_rechecks_recovery_inside_authorization(
    database: Database,
    scenario: RecoveryAuthorizationScenarioDTO,
) -> None:
    """A context created before recovery must not preserve old action eligibility."""
    access = AccessContextDTO(scenario.seed.principal_id)

    async with database.session() as session, session.begin():
        authorizer = ActionAuthorizationService(PostgresProjectActionFactsReader(session))
        target = ProjectActionTargetDTO(scenario.seed.project_id)

        authorization = await authorizer.require_authorization(
            access=access,
            request=ProjectActionAuthorizationRequestDTO(
                project_id=target.project_id, action_id=ACTION
            ),
        )
        assert authorization.organization_id == scenario.seed.organization_id
        assert authorization.project_id == scenario.seed.project_id

        async with database.session() as recovery_session, recovery_session.begin():
            await _admit(recovery_session, scenario)

        with pytest.raises(AccessDeniedError):
            await authorizer.require_authorization(
                access=access,
                request=ProjectActionAuthorizationRequestDTO(
                    project_id=target.project_id, action_id=ACTION
                ),
            )


@pytest.mark.asyncio
async def test_recovery_denies_new_grants_and_saved_replays(
    database: Database,
    scenario: RecoveryAuthorizationScenarioDTO,
) -> None:
    """A saved success cannot bypass recovery or create another grant effect."""
    async with database.session() as session:
        await _assign(session, scenario)

    before = await _effects(database, scenario)
    assert before == GrantEffectsDTO(1, 1, 1, 1)

    async with database.session() as session, session.begin():
        await _admit(session, scenario)

    for key in (KEY, IdempotencyKey("another-grant-request")):
        with pytest.raises(AccessDeniedError):
            async with database.session() as session:
                await _assign(session, scenario, key=key)

    assert await _effects(database, scenario) == before


@pytest.mark.asyncio
async def test_recovery_committing_first_denies_the_waiting_grant(
    database: Database,
    scenario: RecoveryAuthorizationScenarioDTO,
) -> None:
    """A grant waiting behind recovery must read the newly committed block."""
    pid_ready: asyncio.Future[int] = asyncio.get_running_loop().create_future()

    async def try_grant() -> bool:
        try:
            async with database.session() as session:
                await _assign(
                    session,
                    scenario,
                    authorizer=MockControlledProjectGrantAuthorizer(session, pid_ready=pid_ready),
                )
        except AccessDeniedError:
            return False

        return True

    async with asyncio.timeout(10), asyncio.TaskGroup() as tasks:
        async with database.session() as session, session.begin():
            await _admit(session, scenario)
            grant = tasks.create_task(try_grant())
            await _wait_until_database_blocks(database, await pid_ready)

        assert await grant is False

    assert await _effects(database, scenario) == GrantEffectsDTO(0, 0, 0, 0)


@pytest.mark.asyncio
async def test_grant_committing_first_finishes_before_recovery_admission(
    database: Database,
    scenario: RecoveryAuthorizationScenarioDTO,
) -> None:
    """Recovery waits for an earlier grant transaction rather than overtaking it."""
    pid_ready: asyncio.Future[int] = asyncio.get_running_loop().create_future()

    async def recover() -> OperationId:
        async with database.session() as session, session.begin():
            pid_ready.set_result(await _backend_pid(session))
            return await _admit(session, scenario)

    authorized = asyncio.Event()
    release = asyncio.Event()

    async def grant() -> CompletedSynchronousOperationDTO:
        async with database.session() as session:
            return await _assign(
                session,
                scenario,
                authorizer=MockControlledProjectGrantAuthorizer(
                    session, authorized=authorized, release=release
                ),
            )

    async with asyncio.timeout(10), asyncio.TaskGroup() as tasks:
        granting = tasks.create_task(grant())
        await authorized.wait()
        recovery = tasks.create_task(recover())
        try:
            await _wait_until_database_blocks(database, await pid_ready)
        finally:
            release.set()
        await granting
        await recovery

    assert await _effects(database, scenario) == GrantEffectsDTO(1, 1, 1, 1)

    with pytest.raises(AccessDeniedError):
        async with database.session() as session:
            await _assign(
                session,
                scenario,
                key=IdempotencyKey("after-recovery"),
            )

    assert await _effects(database, scenario) == GrantEffectsDTO(1, 1, 1, 1)


@pytest.mark.asyncio
async def test_both_confirmed_states_still_need_explicit_release(
    database: Database,
    scenario: RecoveryAuthorizationScenarioDTO,
) -> None:
    """Provider confirmations alone must not release the product-access block."""
    async with database.session() as session, session.begin():
        operation_id = await _admit(session, scenario)

    async with database.session() as session, session.begin():
        await session.execute(
            update(IdentityRecoveryAdmissionRow)
            .where(IdentityRecoveryAdmissionRow.operation_id == operation_id.value)
            .values(
                kratos_cleanup_state=IdentityRecoveryCleanupState.CONFIRMED,
                hydra_cleanup_state=IdentityRecoveryCleanupState.CONFIRMED,
            )
        )

    async with database.session() as session:
        assert await PostgresPrincipalRecoveryBlockReader(session).is_blocked(
            scenario.seed.principal_id
        )

    # Arrange released history without claiming that real provider cleanup ran.
    async with database.session() as session, session.begin():
        await session.execute(
            update(IdentityRecoveryAdmissionRow)
            .where(IdentityRecoveryAdmissionRow.operation_id == operation_id.value)
            .values(released_at=func.now())
        )

    async with database.session() as session:
        assert not await PostgresPrincipalRecoveryBlockReader(session).is_blocked(
            scenario.seed.principal_id
        )


@pytest.mark.asyncio
async def test_recovery_lock_wait_times_out_without_admitting_an_operation(
    database: Database,
    scenario: RecoveryAuthorizationScenarioDTO,
) -> None:
    """A stalled recovery admission must leave no cleanup obligation after rollback."""
    async with asyncio.timeout(10):
        async with database.session() as holder, holder.begin():
            await holder.execute(
                select(OrganizationRow.id)
                .where(OrganizationRow.id == scenario.seed.organization_id.value)
                .with_for_update(read=True)
            )

            with pytest.raises(DependencyUnavailableError):
                async with database.session() as session, session.begin():
                    await _admit(session, scenario)

    async with database.session() as session:
        count = (
            await session.execute(select(func.count()).select_from(IdentityRecoveryAdmissionRow))
        ).scalar_one()

    assert count == 0
    assert await _effects(database, scenario) == GrantEffectsDTO(0, 0, 0, 0)


@pytest.mark.asyncio
async def test_grant_lock_wait_times_out_without_saving_partial_effects(
    database: Database,
    scenario: RecoveryAuthorizationScenarioDTO,
) -> None:
    """A stalled grant must leave no reservation, audit event or Access change."""
    async with asyncio.timeout(10):
        async with database.session() as holder, holder.begin():
            await _admit(holder, scenario)

            with pytest.raises(DependencyUnavailableError):
                async with database.session() as session:
                    await _assign(session, scenario)

    assert await _effects(database, scenario) == GrantEffectsDTO(0, 0, 0, 0)


@pytest.mark.asyncio
async def test_recovery_before_local_admission_blocks_the_later_linked_principal(
    database: Database,
) -> None:
    """A later local account must inherit its provider identity's pending block."""
    identity = VerifiedHumanIdentityDTO(
        IdentityAuthority("kratos:test"),
        IdentitySubject(str(uuid4())),
    )
    installation_id = await PostgresInstallationIdentityReader(database).read()

    async with database.session() as session, session.begin():
        await IdentityRecoveryAdmissionService(
            PostgresIdentityRecoveryAdmissionWriter(
                session,
                installation_id=installation_id,
                authority=identity.authority,
            )
        ).admit(
            IdentityRecoveryEventDTO(
                flow_id=IdentityRecoveryFlowId(uuid4()),
                identity=identity,
                event_kind=IdentityRecoveryEventKind.RECOVERY,
            )
        )

    async with database.session() as session:
        count = (await session.execute(select(func.count()).select_from(PrincipalRow))).scalar_one()

    assert count == 0

    async with database.session() as session, session.begin():
        principal = await MockAccessScenarios.seed_linked_human(session, identity)

    async with database.session() as session:
        assert await PostgresPrincipalRecoveryBlockReader(session).is_blocked(principal.id)


@pytest.mark.asyncio
async def test_missing_installation_metadata_cannot_allow_authorization(
    database: Database,
    scenario: RecoveryAuthorizationScenarioDTO,
) -> None:
    """Missing installation metadata must not be mistaken for an absent block."""
    async with database.session() as session, session.begin():
        await session.execute(delete(InstallationIdentityRow))

    with pytest.raises(DependencyUnavailableError):
        async with database.session() as session:
            await ActionAuthorizationService(
                PostgresProjectActionFactsReader(session)
            ).require_authorization(
                access=AccessContextDTO(scenario.seed.principal_id),
                request=ProjectActionAuthorizationRequestDTO(
                    project_id=scenario.seed.project_id, action_id=ACTION
                ),
            )


@pytest.mark.asyncio
async def test_one_humans_recovery_does_not_block_an_unrelated_application(
    database: Database,
    scenario: RecoveryAuthorizationScenarioDTO,
) -> None:
    """Recovery must follow the affected identity rather than block every principal."""
    async with database.session() as session, session.begin():
        await _admit(session, scenario)

    async with database.session() as session, session.begin():
        application = await MockAccessScenarios.seed_project_authorization(
            session,
            is_project_member=True,
            has_action_grant=True,
            principal_kind=PrincipalKind.APPLICATION,
        )

    async with database.session() as session:
        authorization = await ActionAuthorizationService(
            PostgresProjectActionFactsReader(session)
        ).require_authorization(
            access=AccessContextDTO(application.principal_id),
            request=ProjectActionAuthorizationRequestDTO(
                project_id=application.project_id, action_id=application.action
            ),
        )

    assert authorization.organization_id == application.organization_id
    assert authorization.project_id == application.project_id


@pytest.mark.asyncio
async def test_audit_failure_rolls_back_all_grant_effects(
    database: Database, scenario: RecoveryAuthorizationScenarioDTO
) -> None:
    """An audit failure must undo the already written grant, revision and reservation."""
    async with database.session() as session:
        with pytest.raises(RuntimeError, match="injected audit failure"):
            await _assign(
                session, scenario, audit_events=MockControlledAuditEventWriter(session, fail=True)
            )
    assert await _effects(database, scenario) == GrantEffectsDTO(0, 0, 0, 0)


@pytest.mark.asyncio
async def test_completion_failure_rolls_back_all_grant_effects(
    database: Database, scenario: RecoveryAuthorizationScenarioDTO
) -> None:
    """Even a flushed replay marker cannot survive a failed operation."""
    async with database.session() as session:
        with pytest.raises(RuntimeError, match="injected completion failure"):
            await _assign(
                session,
                scenario,
                idempotency=MockFailingCompletion(PostgresOperationReservationWriter(session)),
            )
    assert await _effects(database, scenario) == GrantEffectsDTO(0, 0, 0, 0)


@pytest.mark.asyncio
async def test_cancellation_before_commit_rolls_back_all_grant_effects(
    database: Database, scenario: RecoveryAuthorizationScenarioDTO
) -> None:
    """Cancel after real grant and audit writes, before the operation can commit."""
    async with database.session() as session:
        audit = MockControlledAuditEventWriter(session, pause=True)
        async with asyncio.timeout(5), asyncio.TaskGroup() as tasks:
            assignment = tasks.create_task(_assign(session, scenario, audit_events=audit))
            await audit.appended.wait()
            assignment.cancel()
            with pytest.raises(asyncio.CancelledError):
                await assignment
    assert await _effects(database, scenario) == GrantEffectsDTO(0, 0, 0, 0)


@pytest.mark.asyncio
async def test_duplicate_assignment_rolls_back_its_new_reservation_and_revision(
    database: Database, scenario: RecoveryAuthorizationScenarioDTO
) -> None:
    async with database.session() as session:
        await _assign(session, scenario)
    before = await _effects(database, scenario)
    assert before == GrantEffectsDTO(1, 1, 1, 1)
    async with database.session() as session:
        with pytest.raises(ConflictError):
            await _assign(
                session, scenario, key=IdempotencyKey("duplicate-assignment"), expected_revision=1
            )
    assert await _effects(database, scenario) == before
