"""Exercise durable cleanup claims against PostgreSQL without pretending to revoke providers."""

import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Literal, override
from uuid import uuid4

import pytest
from sqlalchemy import event, func, select, update
from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError
from sqlalchemy.orm import Session
from tests.support.access_scenarios import MockAccessScenarios
from tests.support.recovery_notifications import notification_service

from inframeld_backend.access.application.dtos.human_oauth_cleanup_outcome_dto import (
    HumanOAuthCleanupOutcomeDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_admission_dto import (
    IdentityRecoveryAdmissionDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_cleanup_work_dto import (
    IdentityRecoveryCleanupWorkDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_event_dto import (
    IdentityRecoveryEventDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_settings_evidence_dto import (
    IdentityRecoverySettingsEvidenceDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.enums.identity_recovery_cleanup_step import (
    IdentityRecoveryCleanupStep,
)
from inframeld_backend.access.application.enums.identity_recovery_event_kind import (
    IdentityRecoveryEventKind,
)
from inframeld_backend.access.application.enums.identity_recovery_evidence_type import (
    IdentityRecoveryEvidenceType,
)
from inframeld_backend.access.application.enums.oauth_cleanup_category import OAuthCleanupCategory
from inframeld_backend.access.application.enums.oauth_cleanup_disposition import (
    OAuthCleanupDisposition,
)
from inframeld_backend.access.application.protocols.human_oauth_credential_revoker import (
    HumanOAuthCredentialRevoker,
)
from inframeld_backend.access.application.services.identity_recovery_cleanup_execution_service import (
    IdentityRecoveryCleanupExecutionService,
)
from inframeld_backend.access.application.services.identity_recovery_cleanup_reconciliation_service import (
    IdentityRecoveryCleanupReconciliationService,
)
from inframeld_backend.access.application.value_objects.identity_session_id import IdentitySessionId
from inframeld_backend.access.application.value_objects.identity_settings_flow_id import (
    IdentitySettingsFlowId,
)
from inframeld_backend.access.domain.enums.identity_recovery_cleanup_state import (
    IdentityRecoveryCleanupState as State,
)
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_recovery_flow_id import (
    IdentityRecoveryFlowId,
)
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.infrastructure.readers.postgres_identity_recovery_cleanup_facts_reader import (
    PostgresIdentityRecoveryCleanupFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_identity_recovery_cleanup_proof_reader import (
    PostgresIdentityRecoveryCleanupProofReader,
)
from inframeld_backend.access.infrastructure.resources.sqlalchemy_recovery_transaction_manager import (
    SqlAlchemyRecoveryTransactionManager,
)
from inframeld_backend.access.infrastructure.rows.human_credential_version_row import (
    HumanCredentialVersionRow,
)
from inframeld_backend.access.infrastructure.rows.identity_recovery_admission_row import (
    IdentityRecoveryAdmissionRow,
)
from inframeld_backend.access.infrastructure.rows.identity_recovery_cleanup_attempt_row import (
    IdentityRecoveryCleanupAttemptRow,
)
from inframeld_backend.access.infrastructure.rows.identity_recovery_cleanup_job_row import (
    IdentityRecoveryCleanupJobRow,
)
from inframeld_backend.access.infrastructure.rows.identity_recovery_cleanup_proof_row import (
    IdentityRecoveryCleanupProofRow,
)
from inframeld_backend.access.infrastructure.rows.identity_recovery_cleanup_run_row import (
    IdentityRecoveryCleanupRunRow,
)
from inframeld_backend.access.infrastructure.rows.identity_recovery_cleanup_step_row import (
    IdentityRecoveryCleanupStepRow,
)
from inframeld_backend.access.infrastructure.rows.identity_recovery_evidence_receipt_row import (
    IdentityRecoveryEvidenceReceiptRow,
)
from inframeld_backend.access.infrastructure.writers.postgres_identity_recovery_cleanup_proof_writer import (
    PostgresIdentityRecoveryCleanupProofWriter,
)
from inframeld_backend.access.infrastructure.writers.postgres_identity_recovery_cleanup_writer import (
    PostgresIdentityRecoveryCleanupWriter,
)
from inframeld_backend.bootstrap.recovery_completion_operation import RecoveryCompletionOperation
from inframeld_backend.shared.application.errors.application_errors import (
    ConflictError,
    DependencyUnavailableError,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.infrastructure.readers.postgres_installation_identity_reader import (
    PostgresInstallationIdentityReader,
)
from inframeld_backend.shared.infrastructure.resources.database import Database

pytestmark = pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
    reason="Requires PostgreSQL integration services",
)
AUTHORITY = IdentityAuthority("kratos:cleanup-test")


@pytest.mark.asyncio
async def test_no_trusted_password_receipt_means_no_eligible_cleanup(database: Database) -> None:
    installation = await PostgresInstallationIdentityReader(database).read()
    async with database.session() as session, session.begin():
        reader = PostgresIdentityRecoveryCleanupFactsReader(
            session, installation_id=installation, authority=AUTHORITY
        )
        assert await reader.next_candidate() is None


CONFIRMED = HumanOAuthCleanupOutcomeDTO(
    State.CONFIRMED, OAuthCleanupDisposition.NOT_NEEDED, OAuthCleanupCategory.ACKNOWLEDGED, 204
)
UNCERTAIN = HumanOAuthCleanupOutcomeDTO(
    State.UNCERTAIN, OAuthCleanupDisposition.RETRYABLE, OAuthCleanupCategory.PROVIDER_TIMEOUT
)
REJECTED = HumanOAuthCleanupOutcomeDTO(
    State.FAILED,
    OAuthCleanupDisposition.OPERATOR_REQUIRED,
    OAuthCleanupCategory.PROVIDER_REJECTION,
    403,
)


class MockCredentialRevoker(HumanOAuthCredentialRevoker):
    def __init__(self) -> None:
        self.calls: list[tuple[str, IdentitySubject]] = []
        self.cli = CONFIRMED
        self.logins = CONFIRMED

    @override
    async def revoke_cli_grants(
        self, subject: IdentitySubject, *, timeout_seconds: float
    ) -> HumanOAuthCleanupOutcomeDTO:
        self.calls.append(("cli", subject))
        return self.cli

    @override
    async def revoke_remembered_logins(
        self, subject: IdentitySubject, *, timeout_seconds: float
    ) -> HumanOAuthCleanupOutcomeDTO:
        self.calls.append(("logins", subject))
        return self.logins


async def _prepare(
    database: Database,
    *,
    event: IdentityRecoveryEventDTO | None = None,
    password_saved: bool = True,
) -> IdentityRecoveryAdmissionDTO:
    installation = await PostgresInstallationIdentityReader(database).read()
    event = event or IdentityRecoveryEventDTO(
        IdentityRecoveryFlowId(uuid4()),
        VerifiedHumanIdentityDTO(AUTHORITY, IdentitySubject(str(uuid4()))),
        IdentityRecoveryEventKind.RECOVERY,
    )
    async with database.session() as session:
        service = notification_service(session, installation, AUTHORITY)
        admitted = await service.admit(event)
        if password_saved:
            evidence = IdentityRecoverySettingsEvidenceDTO(
                event.identity,
                IdentitySettingsFlowId(uuid4()),
                IdentitySessionId(uuid4()),
                event.flow_id,
            )
            await service.associate_settings(evidence)
            await service.record_password_saved(evidence)
    return IdentityRecoveryAdmissionDTO(event, admitted.operation_id)


async def _execute(database: Database, revoker: HumanOAuthCredentialRevoker) -> bool:
    installation = await PostgresInstallationIdentityReader(database).read()
    async with database.session() as session:
        return await IdentityRecoveryCleanupExecutionService(
            SqlAlchemyRecoveryTransactionManager(session),
            PostgresIdentityRecoveryCleanupFactsReader(
                session, installation_id=installation, authority=AUTHORITY
            ),
            PostgresIdentityRecoveryCleanupWriter(
                session, installation_id=installation, authority=AUTHORITY
            ),
            revoker,
            worker_id=uuid4(),
        ).execute_once()


async def _reconcile(database: Database, *, limit: int = 25) -> int:
    installation = await PostgresInstallationIdentityReader(database).read()
    async with database.session() as session:
        return await IdentityRecoveryCleanupReconciliationService(
            SqlAlchemyRecoveryTransactionManager(session),
            PostgresIdentityRecoveryCleanupProofReader(
                session, installation_id=installation, authority=AUTHORITY
            ),
            PostgresIdentityRecoveryCleanupProofWriter(
                session, installation_id=installation, authority=AUTHORITY
            ),
            RecoveryCompletionOperation(
                database, installation_id=installation, authority=AUTHORITY
            ),
        ).reconcile_pending(limit=limit)


@pytest.mark.asyncio
async def test_both_confirmations_survive_new_instances_and_release_only_from_proof(
    database: Database,
) -> None:
    original = await _prepare(database)
    revoker = MockCredentialRevoker()
    assert await _execute(database, revoker)

    async with database.session() as session:
        row = await session.get(IdentityRecoveryAdmissionRow, original.operation_id.value)
        assert (
            row is not None and row.released_at is None and row.hydra_cleanup_state is State.PENDING
        )
        assert (
            await session.scalar(
                select(func.count()).select_from(IdentityRecoveryCleanupAttemptRow)
            )
            == 1
        )
        assert (
            await session.scalar(select(func.count()).select_from(IdentityRecoveryCleanupProofRow))
            == 1
        )
    assert await _reconcile(database) == 1
    assert not await _execute(database, revoker)
    assert await _reconcile(database) == 0
    assert revoker.calls == [
        ("cli", original.event.identity.subject),
        ("logins", original.event.identity.subject),
    ]
    async with database.session() as session:
        row = await session.get(IdentityRecoveryAdmissionRow, original.operation_id.value)
        assert (
            row is not None
            and row.released_at is not None
            and row.hydra_cleanup_state is State.CONFIRMED
        )
        assert await session.scalar(select(HumanCredentialVersionRow.version)) == 2
        run = (await session.scalars(select(IdentityRecoveryCleanupRunRow))).one()
        assert run.consumed_attempts == 1 and run.terminal_reason == "cleanup_confirmed"


@pytest.mark.asyncio
async def test_restart_keeps_backoff_budget_and_skips_the_confirmed_step(
    database: Database,
) -> None:
    original = await _prepare(database)
    revoker = MockCredentialRevoker()
    revoker.cli = UNCERTAIN
    assert await _execute(database, revoker)
    async with database.session() as session:
        run = (await session.scalars(select(IdentityRecoveryCleanupRunRow))).one()
        first = (run.id, run.authorized_at, run.deadline, run.next_attempt_at)
        job = (await session.scalars(select(IdentityRecoveryCleanupJobRow))).one()
        login_confirmation = job.login_confirmation_attempt_id
        assert job.remembered_logins_state is State.CONFIRMED
        assert job.cli_grants_state is State.UNCERTAIN
    assert not await _execute(database, revoker)
    assert await _reconcile(database) == 0

    # Make only the saved wait due, without changing the run or its deadline.
    async with database.session() as session, session.begin():
        await session.execute(
            update(IdentityRecoveryCleanupRunRow).values(next_attempt_at=first[1])
        )
    revoker.cli = CONFIRMED
    assert await _execute(database, revoker)
    assert await _reconcile(database) == 1
    assert revoker.calls == [
        ("cli", original.event.identity.subject),
        ("logins", original.event.identity.subject),
        ("cli", original.event.identity.subject),
    ]
    async with database.session() as session:
        run = (await session.scalars(select(IdentityRecoveryCleanupRunRow))).one()
        job = (await session.scalars(select(IdentityRecoveryCleanupJobRow))).one()
        assert (run.id, run.authorized_at, run.deadline) == first[:3]
        assert run.consumed_attempts == 2
        assert job.login_confirmation_attempt_id == login_confirmation
        assert job.cli_confirmation_attempt_id != login_confirmation


@pytest.mark.asyncio
async def test_permanent_rejection_ends_run_and_duplicate_callback_cannot_restart_it(
    database: Database,
) -> None:
    original = await _prepare(database)
    revoker = MockCredentialRevoker()
    revoker.cli = REJECTED
    assert await _execute(database, revoker)
    async with database.session() as session:
        receipt = await session.scalar(
            select(IdentityRecoveryEvidenceReceiptRow).where(
                IdentityRecoveryEvidenceReceiptRow.operation_id == original.operation_id.value,
                IdentityRecoveryEvidenceReceiptRow.event_type
                == IdentityRecoveryEvidenceType.PASSWORD_SETTINGS_SAVED,
            )
        )
        assert receipt is not None and receipt.session_id is not None
        evidence = IdentityRecoverySettingsEvidenceDTO(
            original.event.identity,
            IdentitySettingsFlowId(receipt.native_flow_id),
            IdentitySessionId(receipt.session_id),
            None
            if receipt.source_recovery_flow_id is None
            else IdentityRecoveryFlowId(receipt.source_recovery_flow_id),
        )
    installation = await PostgresInstallationIdentityReader(database).read()
    async with database.session() as session:
        replay = await notification_service(session, installation, AUTHORITY).record_password_saved(
            evidence
        )
        assert replay is not None and replay.operation_id == original.operation_id
    assert not await _execute(database, revoker)
    assert await _reconcile(database) == 0
    assert revoker.calls == [("cli", original.event.identity.subject)]
    async with database.session() as session:
        run = (await session.scalars(select(IdentityRecoveryCleanupRunRow))).one()
        assert run.terminal_reason == "permanent_provider_rejection" and run.consumed_attempts == 1
        assert (
            await session.scalar(select(func.count()).select_from(IdentityRecoveryCleanupRunRow))
            == 1
        )
        row = await session.get(IdentityRecoveryAdmissionRow, original.operation_id.value)
        assert row is not None and row.released_at is None
        assert (
            await session.scalar(select(func.count()).select_from(IdentityRecoveryCleanupProofRow))
            == 0
        )


@pytest.mark.asyncio
async def test_newer_combined_proof_covers_only_explicit_older_links_without_inventing_jobs(
    database: Database,
) -> None:
    oldest = await _prepare(database, password_saved=False)
    middle_event = replace(oldest.event, flow_id=IdentityRecoveryFlowId(uuid4()))
    middle = await _prepare(database, event=middle_event)
    newest = await _prepare(
        database,
        event=replace(middle_event, flow_id=IdentityRecoveryFlowId(uuid4())),
        password_saved=False,
    )
    bob = await _prepare(database, password_saved=False)
    revoker = MockCredentialRevoker()
    assert await _execute(database, revoker)
    assert await _reconcile(database) == 2
    async with database.session() as session:
        for original in (oldest, middle):
            row = await session.get(IdentityRecoveryAdmissionRow, original.operation_id.value)
            assert row is not None and row.released_at is not None
        for original in (newest, bob):
            row = await session.get(IdentityRecoveryAdmissionRow, original.operation_id.value)
            assert row is not None and row.released_at is None
        assert (
            await session.scalar(select(func.count()).select_from(IdentityRecoveryCleanupJobRow))
            == 1
        )
        assert (
            await session.scalar(select(func.count()).select_from(IdentityRecoveryCleanupRunRow))
            == 1
        )
        covered = await session.get(IdentityRecoveryCleanupProofRow, oldest.operation_id.value)
        assert covered is not None and covered.source_operation_id == middle.operation_id.value
        assert (
            await session.scalar(
                select(HumanCredentialVersionRow.version).where(
                    HumanCredentialVersionRow.subject == oldest.event.identity.subject.value
                )
            )
            == 4
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [PrincipalStatus.SUSPENDED, PrincipalStatus.RETIRED])
async def test_finished_provider_work_does_not_restore_an_ineligible_account(
    database: Database, status: PrincipalStatus
) -> None:
    identity = VerifiedHumanIdentityDTO(AUTHORITY, IdentitySubject(str(uuid4())))
    async with database.session() as session, session.begin():
        await MockAccessScenarios.seed_linked_human(session, identity, status=status)
    original = await _prepare(
        database,
        event=IdentityRecoveryEventDTO(
            IdentityRecoveryFlowId(uuid4()), identity, IdentityRecoveryEventKind.RECOVERY
        ),
    )
    revoker = MockCredentialRevoker()
    assert await _execute(database, revoker)
    assert await _reconcile(database) == 1
    assert await _reconcile(database) == 0
    assert not await _execute(database, revoker)
    assert len(revoker.calls) == 2
    async with database.session() as session:
        row = await session.get(IdentityRecoveryAdmissionRow, original.operation_id.value)
        proof = await session.get(IdentityRecoveryCleanupProofRow, original.operation_id.value)
        assert (
            row is not None
            and row.hydra_cleanup_state is State.CONFIRMED
            and row.released_at is None
        )
        assert proof is not None and proof.release_status == "ineligible"


@pytest.mark.asyncio
async def test_expired_attempt_is_consumed_and_stale_owner_cannot_checkpoint(
    database: Database,
) -> None:
    from inframeld_backend.access.application.dtos.identity_recovery_cleanup_claim_dto import (
        IdentityRecoveryCleanupClaimDTO,
    )

    original = await _prepare(database)
    installation = await PostgresInstallationIdentityReader(database).read()
    now = datetime.now(UTC)
    async with database.session() as session, session.begin():
        reader = PostgresIdentityRecoveryCleanupFactsReader(
            session, installation_id=installation, authority=AUTHORITY
        )
        work = await reader.lock_work(original.operation_id)
        assert work is not None
        claim = IdentityRecoveryCleanupClaimDTO(
            original.operation_id,
            work.run.id,
            uuid4(),
            uuid4(),
            uuid4(),
            now + timedelta(seconds=60),
        )
        writer = PostgresIdentityRecoveryCleanupWriter(
            session, installation_id=installation, authority=AUTHORITY
        )
        await writer.claim(work, claim, at=now)
        await writer.admit_step(claim, IdentityRecoveryCleanupStep.CLI_GRANTS, at=now)
    revoker = MockCredentialRevoker()
    assert not await _execute(database, revoker)
    assert revoker.calls == []

    async with database.session() as session, session.begin():
        await session.execute(
            update(IdentityRecoveryCleanupAttemptRow).values(
                claimed_at=now - timedelta(seconds=120), lease_expires_at=now - timedelta(seconds=1)
            )
        )
        await session.execute(
            update(IdentityRecoveryCleanupJobRow).values(
                lease_expires_at=now - timedelta(seconds=1)
            )
        )
    assert await _execute(database, revoker)
    assert revoker.calls == []
    async with database.session() as session:
        attempt = await session.get(IdentityRecoveryCleanupAttemptRow, claim.attempt_id)
        assert attempt is not None and attempt.ended_at is not None
        step = await session.get(
            IdentityRecoveryCleanupStepRow,
            (claim.attempt_id, IdentityRecoveryCleanupStep.CLI_GRANTS),
        )
        assert step is not None and step.state is State.UNCERTAIN
        run = (await session.scalars(select(IdentityRecoveryCleanupRunRow))).one()
        assert run.consumed_attempts == 1 and run.next_attempt_at > now
    async with database.session() as session, session.begin():
        reader = PostgresIdentityRecoveryCleanupFactsReader(
            session, installation_id=installation, authority=AUTHORITY
        )
        await reader.lock_work(original.operation_id)
        with pytest.raises(ConflictError):
            await PostgresIdentityRecoveryCleanupWriter(
                session, installation_id=installation, authority=AUTHORITY
            ).checkpoint(
                claim, IdentityRecoveryCleanupStep.CLI_GRANTS, CONFIRMED, at=datetime.now(UTC)
            )
    assert await _reconcile(database) == 0


@pytest.mark.asyncio
async def test_exhausted_budget_never_admits_another_call(database: Database) -> None:
    original = await _prepare(database)
    async with database.session() as session, session.begin():
        await session.execute(update(IdentityRecoveryCleanupRunRow).values(consumed_attempts=12))
    revoker = MockCredentialRevoker()
    assert await _execute(database, revoker)
    assert revoker.calls == []
    async with database.session() as session:
        run = (await session.scalars(select(IdentityRecoveryCleanupRunRow))).one()
        assert run.terminal_reason == "attempt_budget_exhausted"
        assert (
            await session.scalar(
                select(func.count()).select_from(IdentityRecoveryCleanupAttemptRow)
            )
            == 0
        )
        row = await session.get(IdentityRecoveryAdmissionRow, original.operation_id.value)
        assert row is not None and row.released_at is None


@pytest.mark.asyncio
async def test_one_original_per_page_eventually_applies_all_newer_proof(database: Database) -> None:
    oldest = await _prepare(database, password_saved=False)
    newer = await _prepare(
        database, event=replace(oldest.event, flow_id=IdentityRecoveryFlowId(uuid4()))
    )
    revoker = MockCredentialRevoker()
    assert await _execute(database, revoker)
    assert await _reconcile(database, limit=1) == 1
    assert await _reconcile(database, limit=1) == 1
    assert await _reconcile(database, limit=1) == 0
    async with database.session() as session:
        proof = await session.get(IdentityRecoveryCleanupProofRow, oldest.operation_id.value)
        assert proof is not None and proof.source_operation_id == newer.operation_id.value
        assert proof.checked_at is not None


@pytest.mark.asyncio
async def test_newer_proof_ends_an_older_partial_run_without_overwriting_its_confirmation(
    database: Database,
) -> None:
    oldest = await _prepare(database)
    revoker = MockCredentialRevoker()
    revoker.cli = UNCERTAIN
    assert await _execute(database, revoker)
    async with database.session() as session:
        job = await session.get(IdentityRecoveryCleanupJobRow, oldest.operation_id.value)
        assert job is not None
        login_confirmation = job.login_confirmation_attempt_id
    newer = await _prepare(
        database, event=replace(oldest.event, flow_id=IdentityRecoveryFlowId(uuid4()))
    )
    revoker.cli = CONFIRMED
    assert await _execute(database, revoker)
    assert await _reconcile(database) == 2
    async with database.session() as session:
        job = await session.get(IdentityRecoveryCleanupJobRow, oldest.operation_id.value)
        assert job is not None and job.login_confirmation_attempt_id == login_confirmation
        old_run = (
            await session.scalars(
                select(IdentityRecoveryCleanupRunRow).where(
                    IdentityRecoveryCleanupRunRow.operation_id == oldest.operation_id.value
                )
            )
        ).one()
        assert (
            old_run.terminal_reason == "satisfied_by_newer_recovery"
            and old_run.consumed_attempts == 1
        )
        proof = await session.get(IdentityRecoveryCleanupProofRow, oldest.operation_id.value)
        assert proof is not None and proof.source_operation_id == newer.operation_id.value
    calls = tuple(revoker.calls)
    assert not await _execute(database, revoker)
    assert tuple(revoker.calls) == calls


@pytest.mark.asyncio
async def test_overlapping_workers_do_not_hold_identity_locks_during_provider_wait(
    database: Database,
) -> None:
    import asyncio

    class BlockedRevoker(MockCredentialRevoker):
        def __init__(self) -> None:
            super().__init__()
            self.started = asyncio.Event()

        @override
        async def revoke_cli_grants(
            self, subject: IdentitySubject, *, timeout_seconds: float
        ) -> HumanOAuthCleanupOutcomeDTO:
            self.started.set()
            await asyncio.Event().wait()
            return CONFIRMED

    await _prepare(database)
    revoker = BlockedRevoker()
    first = asyncio.create_task(_execute(database, revoker))
    try:
        async with asyncio.timeout(5):
            await revoker.started.wait()
            assert not await _execute(database, MockCredentialRevoker())
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        async with database.session() as session:
            run = (await session.scalars(select(IdentityRecoveryCleanupRunRow))).one()
            job = (await session.scalars(select(IdentityRecoveryCleanupJobRow))).one()
            assert run.consumed_attempts == 1 and run.ended_at is None
            assert job.ownership_token is not None and job.cli_grants_state is State.PENDING
    finally:
        first.cancel()
        await asyncio.gather(first, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    [
        OperationalError("checkpoint", None, ConnectionError("Unavailable.")),
        InterfaceError("checkpoint", None, ConnectionError("Unavailable.")),
        SqlAlchemyTimeoutError("Pool unavailable."),
    ],
    ids=["connection", "interface", "pool"],
)
async def test_failed_checkpoint_rolls_back_success_without_refunding_the_claim(
    database: Database,
    failure: Exception,
) -> None:
    from inframeld_backend.access.application.dtos.identity_recovery_cleanup_claim_dto import (
        IdentityRecoveryCleanupClaimDTO,
    )

    class FailingCheckpointWriter(PostgresIdentityRecoveryCleanupWriter):
        @override
        async def checkpoint(
            self,
            claim: IdentityRecoveryCleanupClaimDTO,
            step: IdentityRecoveryCleanupStep,
            outcome: HumanOAuthCleanupOutcomeDTO,
            *,
            at: datetime,
        ) -> None:
            await super().checkpoint(claim, step, outcome, at=at)
            raise failure

    await _prepare(database)
    installation = await PostgresInstallationIdentityReader(database).read()
    revoker = MockCredentialRevoker()
    async with database.session() as session:
        service = IdentityRecoveryCleanupExecutionService(
            SqlAlchemyRecoveryTransactionManager(session),
            PostgresIdentityRecoveryCleanupFactsReader(
                session, installation_id=installation, authority=AUTHORITY
            ),
            FailingCheckpointWriter(session, installation_id=installation, authority=AUTHORITY),
            revoker,
            worker_id=uuid4(),
        )
        with pytest.raises(DependencyUnavailableError):
            await service.execute_once()
    async with database.session() as session:
        run = (await session.scalars(select(IdentityRecoveryCleanupRunRow))).one()
        job = (await session.scalars(select(IdentityRecoveryCleanupJobRow))).one()
        step = (await session.scalars(select(IdentityRecoveryCleanupStepRow))).one()
        assert run.consumed_attempts == 1
        assert run.ended_at is None and run.terminal_reason is None
        assert job.active_attempt_id is not None
        assert job.cli_grants_state is State.PENDING and job.cli_confirmation_attempt_id is None
        assert step.checkpointed_at is None and step.state is None
        assert (
            await session.scalar(select(func.count()).select_from(IdentityRecoveryCleanupProofRow))
            == 0
        )


async def _expire_execution_lease(database: Database, operation_id: OperationId) -> None:
    now = datetime.now(UTC)
    async with database.session() as session, session.begin():
        await session.execute(
            update(IdentityRecoveryCleanupAttemptRow)
            .where(
                IdentityRecoveryCleanupAttemptRow.operation_id == operation_id.value,
                IdentityRecoveryCleanupAttemptRow.ended_at.is_(None),
            )
            .values(
                claimed_at=now - timedelta(seconds=120),
                lease_expires_at=now - timedelta(seconds=1),
            )
        )
        await session.execute(
            update(IdentityRecoveryCleanupJobRow)
            .where(IdentityRecoveryCleanupJobRow.operation_id == operation_id.value)
            .values(lease_expires_at=now - timedelta(seconds=1))
        )


@pytest.mark.asyncio
async def test_temporary_read_failure_after_confirmations_keeps_proof_work_recoverable(
    database: Database,
) -> None:
    class InterruptedFinalRead(PostgresIdentityRecoveryCleanupFactsReader):
        interrupted = False

        @override
        async def lock_work(
            self, operation_id: OperationId
        ) -> IdentityRecoveryCleanupWorkDTO | None:
            work = await super().lock_work(operation_id)
            if (
                not self.interrupted
                and work is not None
                and work.cli_grants_state is work.remembered_logins_state is State.CONFIRMED
            ):
                self.interrupted = True
                raise OperationalError("proof read", None, ConnectionError("Unavailable."))
            return work

    original = await _prepare(database)
    installation = await PostgresInstallationIdentityReader(database).read()
    revoker = MockCredentialRevoker()
    async with database.session() as session:
        service = IdentityRecoveryCleanupExecutionService(
            SqlAlchemyRecoveryTransactionManager(session),
            InterruptedFinalRead(session, installation_id=installation, authority=AUTHORITY),
            PostgresIdentityRecoveryCleanupWriter(
                session, installation_id=installation, authority=AUTHORITY
            ),
            revoker,
            worker_id=uuid4(),
        )
        with pytest.raises(DependencyUnavailableError):
            await service.execute_once()

    async with database.session() as session:
        run = (await session.scalars(select(IdentityRecoveryCleanupRunRow))).one()
        assert run.consumed_attempts == 1 and run.ended_at is None
        assert (
            await session.get(IdentityRecoveryCleanupProofRow, original.operation_id.value) is None
        )
        original_budget = (run.id, run.authorized_at, run.deadline, run.next_attempt_at)

    assert not await _execute(database, revoker)
    await _expire_execution_lease(database, original.operation_id)
    assert await _execute(database, revoker)
    assert await _reconcile(database) == 1
    assert len(revoker.calls) == 2

    async with database.session() as session:
        run = (await session.scalars(select(IdentityRecoveryCleanupRunRow))).one()
        assert (run.id, run.authorized_at, run.deadline, run.next_attempt_at) == original_budget
        assert run.consumed_attempts == 1 and run.terminal_reason == "cleanup_confirmed"
        admission = await session.get(IdentityRecoveryAdmissionRow, original.operation_id.value)
        assert admission is not None and admission.released_at is not None


async def _interrupt_proof_commit(
    database: Database,
    revoker: MockCredentialRevoker,
    when: Literal["before_commit", "after_commit"],
) -> None:
    installation = await PostgresInstallationIdentityReader(database).read()
    async with database.session() as session:

        def interrupt(_session: Session) -> None:
            raise OperationalError("commit acknowledgement", None, ConnectionError("Unavailable."))

        class InterruptedProofWriter(PostgresIdentityRecoveryCleanupWriter):
            @override
            async def save_complete_proof(
                self, work: IdentityRecoveryCleanupWorkDTO, *, at: datetime
            ) -> None:
                await super().save_complete_proof(work, at=at)
                event.listen(session.sync_session, when, interrupt, once=True)

        await IdentityRecoveryCleanupExecutionService(
            SqlAlchemyRecoveryTransactionManager(session),
            PostgresIdentityRecoveryCleanupFactsReader(
                session, installation_id=installation, authority=AUTHORITY
            ),
            InterruptedProofWriter(session, installation_id=installation, authority=AUTHORITY),
            revoker,
            worker_id=uuid4(),
        ).execute_once()


@pytest.mark.asyncio
async def test_failed_proof_commit_keeps_confirmations_and_original_budget(
    database: Database,
) -> None:
    original = await _prepare(database)
    revoker = MockCredentialRevoker()
    with pytest.raises(DependencyUnavailableError):
        await _interrupt_proof_commit(database, revoker, "before_commit")

    async with database.session() as session:
        assert (
            await session.get(IdentityRecoveryCleanupProofRow, original.operation_id.value) is None
        )
        run = (await session.scalars(select(IdentityRecoveryCleanupRunRow))).one()
        assert run.ended_at is None and run.consumed_attempts == 1
        original_budget = (run.id, run.authorized_at, run.deadline, run.next_attempt_at)

    await _expire_execution_lease(database, original.operation_id)
    assert await _execute(database, revoker)
    assert await _reconcile(database) == 1
    assert len(revoker.calls) == 2

    async with database.session() as session:
        run = (await session.scalars(select(IdentityRecoveryCleanupRunRow))).one()
        assert (run.id, run.authorized_at, run.deadline, run.next_attempt_at) == original_budget
        assert run.consumed_attempts == 1 and run.terminal_reason == "cleanup_confirmed"


@pytest.mark.asyncio
async def test_lost_proof_commit_acknowledgement_reloads_the_committed_result(
    database: Database,
) -> None:
    original = await _prepare(database)
    revoker = MockCredentialRevoker()
    with pytest.raises(DependencyUnavailableError):
        await _interrupt_proof_commit(database, revoker, "after_commit")

    async with database.session() as session:
        proof = await session.get(IdentityRecoveryCleanupProofRow, original.operation_id.value)
        run = (await session.scalars(select(IdentityRecoveryCleanupRunRow))).one()
        assert proof is not None and proof.checked_at is None
        assert run.consumed_attempts == 1 and run.terminal_reason == "cleanup_confirmed"
        original_budget = (run.id, run.authorized_at, run.deadline, run.next_attempt_at)

    assert not await _execute(database, revoker)
    assert await _reconcile(database) == 1
    assert len(revoker.calls) == 2

    async with database.session() as session:
        run = (await session.scalars(select(IdentityRecoveryCleanupRunRow))).one()
        assert (run.id, run.authorized_at, run.deadline, run.next_attempt_at) == original_budget
        admission = await session.get(IdentityRecoveryAdmissionRow, original.operation_id.value)
        assert admission is not None and admission.released_at is not None


@pytest.mark.asyncio
async def test_completed_proof_waits_for_intact_version_state_without_repeating_cleanup(
    database: Database,
) -> None:
    from sqlalchemy import delete

    original = await _prepare(database)
    revoker = MockCredentialRevoker()
    assert await _execute(database, revoker)
    async with database.session() as session, session.begin():
        await session.execute(delete(HumanCredentialVersionRow))
    assert await _reconcile(database) == 0
    assert not await _execute(database, revoker)
    assert len(revoker.calls) == 2
    async with database.session() as session:
        row = await session.get(IdentityRecoveryAdmissionRow, original.operation_id.value)
        proof = await session.get(IdentityRecoveryCleanupProofRow, original.operation_id.value)
        assert row is not None and row.released_at is None
        assert proof is not None and proof.checked_at is None
        assert (
            await session.scalar(select(func.count()).select_from(HumanCredentialVersionRow)) == 0
        )


@pytest.mark.asyncio
async def test_newer_proof_rechecks_an_older_confirmed_block_without_replacing_its_provenance(
    database: Database,
) -> None:
    from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
    from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow

    identity = VerifiedHumanIdentityDTO(AUTHORITY, IdentitySubject(str(uuid4())))
    async with database.session() as session, session.begin():
        alice = await MockAccessScenarios.seed_linked_human(
            session, identity, status=PrincipalStatus.SUSPENDED
        )
    oldest = await _prepare(
        database,
        event=IdentityRecoveryEventDTO(
            IdentityRecoveryFlowId(uuid4()), identity, IdentityRecoveryEventKind.RECOVERY
        ),
    )
    revoker = MockCredentialRevoker()
    assert await _execute(database, revoker)
    assert await _reconcile(database) == 1

    # Arrange a separate authorized restoration. It does not itself release recovery.
    async with database.session() as session, session.begin():
        await session.scalar(
            select(OrganizationRow.id)
            .where(OrganizationRow.id == alice.organization_id.value)
            .with_for_update()
        )
        await session.execute(
            update(PrincipalRow)
            .where(PrincipalRow.id == alice.id.value)
            .values(status=PrincipalStatus.ACTIVE)
        )
    newer = await _prepare(
        database, event=replace(oldest.event, flow_id=IdentityRecoveryFlowId(uuid4()))
    )
    assert await _execute(database, revoker)
    assert await _reconcile(database) == 2
    async with database.session() as session:
        row = await session.get(IdentityRecoveryAdmissionRow, oldest.operation_id.value)
        proof = await session.get(IdentityRecoveryCleanupProofRow, oldest.operation_id.value)
        assert row is not None and row.released_at is not None
        assert proof is not None and proof.source_operation_id == oldest.operation_id.value
        assert proof.source_operation_id != newer.operation_id.value
        assert len(revoker.calls) == 4
