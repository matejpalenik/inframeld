import asyncio
import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import override
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update
from tests.support.recovery_notifications import notification_service

from inframeld_backend.access.application.commands.resume_identity_recovery_cleanup_command import (
    ResumeIdentityRecoveryCleanupCommand,
)
from inframeld_backend.access.application.dtos.human_oauth_cleanup_outcome_dto import (
    HumanOAuthCleanupOutcomeDTO,
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
from inframeld_backend.access.application.enums.identity_recovery_event_kind import (
    IdentityRecoveryEventKind,
)
from inframeld_backend.access.application.enums.oauth_cleanup_category import OAuthCleanupCategory
from inframeld_backend.access.application.enums.oauth_cleanup_disposition import (
    OAuthCleanupDisposition,
)
from inframeld_backend.access.application.enums.recovery_maintenance_error_code import (
    RecoveryMaintenanceErrorCode as Code,
)
from inframeld_backend.access.application.errors.recovery_maintenance_error import (
    RecoveryMaintenanceError,
)
from inframeld_backend.access.application.protocols.human_oauth_credential_revoker import (
    HumanOAuthCredentialRevoker,
)
from inframeld_backend.access.application.services.identity_recovery_cleanup_execution_service import (
    IdentityRecoveryCleanupExecutionService,
)
from inframeld_backend.access.application.services.identity_recovery_cleanup_resume_service import (
    IdentityRecoveryCleanupResumeService,
)
from inframeld_backend.access.application.value_objects.identity_session_id import IdentitySessionId
from inframeld_backend.access.application.value_objects.identity_settings_flow_id import (
    IdentitySettingsFlowId,
)
from inframeld_backend.access.domain.enums.identity_recovery_cleanup_state import (
    IdentityRecoveryCleanupState as State,
)
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_recovery_flow_id import (
    IdentityRecoveryFlowId,
)
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.infrastructure.readers.postgres_identity_recovery_cleanup_facts_reader import (
    PostgresIdentityRecoveryCleanupFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_identity_recovery_cleanup_resume_facts_reader import (
    PostgresIdentityRecoveryCleanupResumeFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_identity_recovery_completion_facts_reader import (
    PostgresIdentityRecoveryCompletionFactsReader,
)
from inframeld_backend.access.infrastructure.resources.sqlalchemy_recovery_transaction_manager import (
    SqlAlchemyRecoveryTransactionManager,
)
from inframeld_backend.access.infrastructure.rows.host_maintenance_receipt_row import (
    HostMaintenanceReceiptRow,
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
from inframeld_backend.access.infrastructure.rows.identity_recovery_cleanup_run_row import (
    IdentityRecoveryCleanupRunRow,
)
from inframeld_backend.access.infrastructure.writers.postgres_identity_recovery_cleanup_resume_writer import (
    PostgresIdentityRecoveryCleanupResumeWriter,
)
from inframeld_backend.access.infrastructure.writers.postgres_identity_recovery_cleanup_writer import (
    PostgresIdentityRecoveryCleanupWriter,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.infrastructure.readers.postgres_installation_identity_reader import (
    PostgresInstallationIdentityReader,
)
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.settings.database_settings import DatabaseSettings

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
        reason="Requires PostgreSQL integration services",
    ),
]
AUTHORITY = IdentityAuthority("kratos:maintenance-test")
CONFIRMED = HumanOAuthCleanupOutcomeDTO(
    State.CONFIRMED, OAuthCleanupDisposition.NOT_NEEDED, OAuthCleanupCategory.ACKNOWLEDGED, 204
)
REJECTED = HumanOAuthCleanupOutcomeDTO(
    State.FAILED,
    OAuthCleanupDisposition.OPERATOR_REQUIRED,
    OAuthCleanupCategory.PROVIDER_REJECTION,
    403,
)


class Revoker(HumanOAuthCredentialRevoker):
    def __init__(self) -> None:
        self.cli = REJECTED
        self.logins = CONFIRMED
        self.calls: list[str] = []

    @override
    async def revoke_cli_grants(
        self, subject: IdentitySubject, *, timeout_seconds: float
    ) -> HumanOAuthCleanupOutcomeDTO:
        self.calls.append("cli")
        return self.cli

    @override
    async def revoke_remembered_logins(
        self, subject: IdentitySubject, *, timeout_seconds: float
    ) -> HumanOAuthCleanupOutcomeDTO:
        self.calls.append("login")
        return self.logins


async def _prepare(
    database: Database,
    *,
    password_saved: bool = True,
    identity: VerifiedHumanIdentityDTO | None = None,
) -> ResumeIdentityRecoveryCleanupCommand:
    installed = await PostgresInstallationIdentityReader(database).read()
    event = IdentityRecoveryEventDTO(
        IdentityRecoveryFlowId(uuid4()),
        identity or VerifiedHumanIdentityDTO(AUTHORITY, IdentitySubject(str(uuid4()))),
        IdentityRecoveryEventKind.RECOVERY,
    )
    async with database.session() as session:
        service = notification_service(session, installed, AUTHORITY)
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
    return ResumeIdentityRecoveryCleanupCommand(
        installed,
        OperationId(str(uuid4())),
        admitted.operation_id,
        "Deployment operator",
        "Hydra configuration repaired",
    )


async def _execute(database: Database, revoker: Revoker) -> None:
    installed = await PostgresInstallationIdentityReader(database).read()
    async with database.session() as session:
        assert await IdentityRecoveryCleanupExecutionService(
            SqlAlchemyRecoveryTransactionManager(session),
            PostgresIdentityRecoveryCleanupFactsReader(
                session, installation_id=installed, authority=AUTHORITY
            ),
            PostgresIdentityRecoveryCleanupWriter(
                session, installation_id=installed, authority=AUTHORITY
            ),
            revoker,
            worker_id=uuid4(),
        ).execute_once()


async def _resume(
    command: ResumeIdentityRecoveryCleanupCommand, settings: DatabaseSettings
) -> dict[str, object]:
    fresh = Database(settings)
    try:
        await fresh.startup()
        async with fresh.session() as session:
            result = await IdentityRecoveryCleanupResumeService(
                SqlAlchemyRecoveryTransactionManager(session),
                PostgresIdentityRecoveryCleanupResumeFactsReader(session),
                PostgresIdentityRecoveryCompletionFactsReader(session),
                PostgresIdentityRecoveryCleanupResumeWriter(session),
            ).resume(command=command)
            from inframeld_backend.access.cli.mappers.recovery_maintenance_mapper import (
                RecoveryMaintenanceMapper,
            )

            return RecoveryMaintenanceMapper.result(result)
    finally:
        await fresh.shutdown()


async def test_new_run_receipt_replays_original_without_resetting_history(
    database: Database, temporary_postgres_settings: DatabaseSettings
) -> None:
    command = await _prepare(database)
    revoker = Revoker()
    await _execute(database, revoker)
    first = await _resume(command, temporary_postgres_settings)
    assert first["outcome"] == "cleanup-authorized"
    assert await _resume(command, temporary_postgres_settings) == first
    async with database.session() as session:
        runs = (
            await session.scalars(
                select(IdentityRecoveryCleanupRunRow).order_by(
                    IdentityRecoveryCleanupRunRow.authorized_at
                )
            )
        ).all()
        assert len(runs) == 2
        assert runs[0].terminal_reason == "permanent_provider_rejection"
        assert runs[0].consumed_attempts == 1
        assert runs[1].consumed_attempts == 0 and runs[1].max_attempts == 12
        assert runs[1].deadline == runs[1].authorized_at + timedelta(hours=1)
        assert runs[1].authorization_source.value == "host-operator"
        assert (
            await session.scalar(select(func.count()).select_from(HostMaintenanceReceiptRow)) == 1
        )
        assert await session.scalar(select(HumanCredentialVersionRow.version)) == 2
        assert (
            await session.scalar(
                select(func.count()).select_from(IdentityRecoveryCleanupAttemptRow)
            )
            == 1
        )

    with pytest.raises(RecoveryMaintenanceError) as error:
        await _resume(replace(command, reason="different meaning"), temporary_postgres_settings)
    assert error.value.code is Code.KEY_REUSED
    revoker.cli = CONFIRMED
    await _execute(database, revoker)
    assert revoker.calls == ["cli", "cli", "login"]
    assert await _resume(command, temporary_postgres_settings) == first


async def test_active_budget_rejects_new_request(
    database: Database, temporary_postgres_settings: DatabaseSettings
) -> None:
    command = await _prepare(database)
    with pytest.raises(RecoveryMaintenanceError) as error:
        await _resume(command, temporary_postgres_settings)
    assert error.value.code is Code.RUN_ACTIVE
    async with database.session() as session:
        assert (
            await session.scalar(select(func.count()).select_from(HostMaintenanceReceiptRow)) == 0
        )


@pytest.mark.parametrize("equivalent", [True, False])
async def test_concurrent_requests_share_one_new_budget(
    database: Database, temporary_postgres_settings: DatabaseSettings, equivalent: bool
) -> None:
    command = await _prepare(database)
    await _execute(database, Revoker())
    second = command if equivalent else replace(command, operation_id=OperationId(str(uuid4())))
    async with asyncio.timeout(10):
        results = await asyncio.gather(
            _resume(command, temporary_postgres_settings),
            _resume(second, temporary_postgres_settings),
            return_exceptions=True,
        )
    if equivalent:
        assert results[0] == results[1] and isinstance(results[0], dict)
    else:
        assert sum(isinstance(result, dict) for result in results) == 1
        failure = next(result for result in results if isinstance(result, RecoveryMaintenanceError))
        assert failure.code is Code.RUN_ACTIVE
    async with database.session() as session:
        assert (
            await session.scalar(select(func.count()).select_from(IdentityRecoveryCleanupRunRow))
            == 2
        )
        assert (
            await session.scalar(select(func.count()).select_from(HostMaintenanceReceiptRow)) == 1
        )


async def test_same_request_id_across_targets_cannot_authorize_two_runs(
    database: Database, temporary_postgres_settings: DatabaseSettings
) -> None:
    first, second = await _prepare(database), await _prepare(database)
    revoker = Revoker()
    await _execute(database, revoker)
    await _execute(database, revoker)
    second = replace(second, operation_id=first.operation_id)
    async with asyncio.timeout(10):
        results = await asyncio.gather(
            _resume(first, temporary_postgres_settings),
            _resume(second, temporary_postgres_settings),
            return_exceptions=True,
        )
    assert sum(isinstance(result, dict) for result in results) == 1
    failure = next(result for result in results if isinstance(result, RecoveryMaintenanceError))
    assert failure.code is Code.KEY_REUSED
    async with database.session() as session:
        assert (
            await session.scalar(select(func.count()).select_from(IdentityRecoveryCleanupRunRow))
            == 3
        )
        assert (
            await session.scalar(select(func.count()).select_from(HostMaintenanceReceiptRow)) == 1
        )


@pytest.mark.parametrize("missing", ["evidence", "version"])
async def test_missing_prerequisites_never_authorize(
    database: Database, temporary_postgres_settings: DatabaseSettings, missing: str
) -> None:
    command = await _prepare(database, password_saved=missing != "evidence")
    if missing == "version":
        from sqlalchemy import delete

        async with database.session() as session, session.begin():
            await session.execute(delete(HumanCredentialVersionRow))
    with pytest.raises(RecoveryMaintenanceError) as error:
        await _resume(command, temporary_postgres_settings)
    assert error.value.code is (
        Code.DEPENDENCY_UNAVAILABLE if missing == "version" else Code.EVIDENCE_MISSING
    )
    async with database.session() as session:
        assert (
            await session.scalar(select(func.count()).select_from(HostMaintenanceReceiptRow)) == 0
        )


async def test_fully_confirmed_cleanup_creates_no_run_and_replays_no_work(
    database: Database, temporary_postgres_settings: DatabaseSettings
) -> None:
    command = await _prepare(database)
    revoker = Revoker()
    revoker.cli = CONFIRMED
    await _execute(database, revoker)
    result = await _resume(command, temporary_postgres_settings)
    assert result["outcome"] == "cleanup-confirmed" and "runId" not in result
    async with database.session() as session:
        assert (
            await session.scalar(select(func.count()).select_from(IdentityRecoveryCleanupRunRow))
            == 1
        )
        assert await session.scalar(select(IdentityRecoveryAdmissionRow.released_at)) is None
    assert await _resume(command, temporary_postgres_settings) == result


async def test_receipt_and_run_roll_back_together_on_write_failure(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    command = await _prepare(database)
    await _execute(database, Revoker())
    original = PostgresIdentityRecoveryCleanupResumeWriter.authorize_run

    async def fail_after_insert(
        self: PostgresIdentityRecoveryCleanupResumeWriter, receipt: object
    ) -> None:
        from inframeld_backend.access.application.dtos.identity_recovery_maintenance_receipt_dto import (
            IdentityRecoveryMaintenanceReceiptDTO,
        )

        assert isinstance(receipt, IdentityRecoveryMaintenanceReceiptDTO)
        await original(self, receipt)
        raise RuntimeError("Simulated persistence failure")

    with monkeypatch.context() as patch:
        patch.setattr(
            PostgresIdentityRecoveryCleanupResumeWriter, "authorize_run", fail_after_insert
        )
        with pytest.raises(RuntimeError):
            await _resume(command, temporary_postgres_settings)
    async with database.session() as session:
        assert (
            await session.scalar(select(func.count()).select_from(HostMaintenanceReceiptRow)) == 0
        )
        assert (
            await session.scalar(select(func.count()).select_from(IdentityRecoveryCleanupRunRow))
            == 1
        )
    assert (await _resume(command, temporary_postgres_settings))["outcome"] == "cleanup-authorized"


@pytest.mark.parametrize("when", ["before_commit", "after_commit"])
async def test_commit_failure_or_lost_ack_reloads_durable_receipt(
    database: Database, temporary_postgres_settings: DatabaseSettings, when: str
) -> None:
    from sqlalchemy import event
    from sqlalchemy.exc import OperationalError
    from sqlalchemy.orm import Session

    from inframeld_backend.shared.application.errors.application_errors import (
        DependencyUnavailableError,
    )

    command = await _prepare(database)
    await _execute(database, Revoker())
    async with database.session() as session:

        def interrupt(_session: Session) -> None:
            raise OperationalError("commit acknowledgment", None, ConnectionError("secret"))

        event.listen(session.sync_session, when, interrupt, once=True)
        with pytest.raises(DependencyUnavailableError):
            await IdentityRecoveryCleanupResumeService(
                SqlAlchemyRecoveryTransactionManager(session),
                PostgresIdentityRecoveryCleanupResumeFactsReader(session),
                PostgresIdentityRecoveryCompletionFactsReader(session),
                PostgresIdentityRecoveryCleanupResumeWriter(session),
            ).resume(command=command)
    async with database.session() as session:
        count = await session.scalar(select(func.count()).select_from(HostMaintenanceReceiptRow))
        assert count == (1 if when == "after_commit" else 0)
    result = await _resume(command, temporary_postgres_settings)
    assert result["outcome"] == "cleanup-authorized"
    async with database.session() as session:
        assert (
            await session.scalar(select(func.count()).select_from(HostMaintenanceReceiptRow)) == 1
        )
        assert (
            await session.scalar(select(func.count()).select_from(IdentityRecoveryCleanupRunRow))
            == 2
        )


@pytest.mark.parametrize("consumed", [1, 12])
async def test_expired_lease_does_not_renew_budget_and_live_final_attempt_stays_active(
    database: Database, temporary_postgres_settings: DatabaseSettings, consumed: int
) -> None:
    from inframeld_backend.access.application.dtos.identity_recovery_cleanup_claim_dto import (
        IdentityRecoveryCleanupClaimDTO,
    )
    from inframeld_backend.access.application.enums.identity_recovery_cleanup_step import (
        IdentityRecoveryCleanupStep,
    )
    from inframeld_backend.shared.application.errors.application_errors import ConflictError

    command = await _prepare(database)
    now = datetime.now(UTC)
    async with database.session() as session, session.begin():
        run = (await session.scalars(select(IdentityRecoveryCleanupRunRow))).one()
        run.consumed_attempts = consumed
        claim = IdentityRecoveryCleanupClaimDTO(
            command.recovery_operation_id,
            run.id,
            uuid4(),
            uuid4(),
            uuid4(),
            now + timedelta(seconds=30),
        )
        session.add(
            IdentityRecoveryCleanupAttemptRow(
                id=claim.attempt_id,
                operation_id=command.recovery_operation_id.value,
                run_id=run.id,
                ordinal=consumed,
                worker_id=claim.worker_id,
                ownership_token=claim.token,
                claimed_at=now - timedelta(seconds=70),
                lease_expires_at=claim.lease_expires_at,
            )
        )
        await session.flush()
        job = await session.get(IdentityRecoveryCleanupJobRow, command.recovery_operation_id.value)
        assert job is not None
        job.active_attempt_id, job.worker_id, job.ownership_token, job.lease_expires_at = (
            claim.attempt_id,
            claim.worker_id,
            claim.token,
            claim.lease_expires_at,
        )
    with pytest.raises(RecoveryMaintenanceError) as error:
        await _resume(command, temporary_postgres_settings)
    assert error.value.code is Code.RUN_ACTIVE
    async with database.session() as session, session.begin():
        await session.execute(
            update(IdentityRecoveryCleanupJobRow).values(
                lease_expires_at=now - timedelta(seconds=1)
            )
        )
        await session.execute(
            update(IdentityRecoveryCleanupAttemptRow).values(
                lease_expires_at=now - timedelta(seconds=1)
            )
        )
    if consumed < 12:
        with pytest.raises(RecoveryMaintenanceError) as error:
            await _resume(command, temporary_postgres_settings)
        assert error.value.code is Code.RUN_ACTIVE
        return
    assert (await _resume(command, temporary_postgres_settings))["outcome"] == "cleanup-authorized"
    async with database.session() as session, session.begin():
        with pytest.raises(ConflictError):
            await PostgresIdentityRecoveryCleanupWriter(
                session, installation_id=command.expected_installation_id, authority=AUTHORITY
            ).checkpoint(
                claim, IdentityRecoveryCleanupStep.CLI_GRANTS, CONFIRMED, at=datetime.now(UTC)
            )
    async with database.session() as session:
        old = await session.get(IdentityRecoveryCleanupRunRow, claim.run_id)
        assert (
            old is not None
            and old.consumed_attempts == 12
            and old.terminal_reason == "attempt_budget_exhausted"
        )


async def test_expired_deadline_settles_original_without_resetting_its_budget(
    database: Database, temporary_postgres_settings: DatabaseSettings
) -> None:
    command = await _prepare(database)
    now = datetime.now(UTC)
    async with database.session() as session, session.begin():
        await session.execute(
            update(IdentityRecoveryCleanupRunRow).values(
                authorized_at=now - timedelta(hours=2),
                deadline=now - timedelta(hours=1),
                next_attempt_at=now - timedelta(hours=2),
            )
        )
    await _resume(command, temporary_postgres_settings)
    async with database.session() as session:
        runs = (
            await session.scalars(
                select(IdentityRecoveryCleanupRunRow).order_by(
                    IdentityRecoveryCleanupRunRow.authorized_at
                )
            )
        ).all()
        assert runs[0].deadline == now - timedelta(hours=1)
        assert runs[0].terminal_reason == "deadline_exhausted"
        assert runs[1].deadline > now


async def test_missing_proof_is_rebuilt_from_confirmations_without_new_provider_work(
    database: Database, temporary_postgres_settings: DatabaseSettings
) -> None:
    from sqlalchemy import delete

    from inframeld_backend.access.infrastructure.rows.identity_recovery_cleanup_proof_row import (
        IdentityRecoveryCleanupProofRow,
    )

    command = await _prepare(database)
    revoker = Revoker()
    revoker.cli = CONFIRMED
    await _execute(database, revoker)
    async with database.session() as session, session.begin():
        await session.execute(delete(IdentityRecoveryCleanupProofRow))
    result = await _resume(command, temporary_postgres_settings)
    assert result["outcome"] == "cleanup-confirmed"
    async with database.session() as session:
        proof = await session.get(
            IdentityRecoveryCleanupProofRow, command.recovery_operation_id.value
        )
        assert proof is not None and proof.checked_at is None
        assert (
            await session.scalar(select(func.count()).select_from(IdentityRecoveryCleanupRunRow))
            == 1
        )
    assert revoker.calls == ["cli", "login"]


async def test_covered_original_without_job_records_no_run_receipt(
    database: Database, temporary_postgres_settings: DatabaseSettings
) -> None:
    from inframeld_backend.access.infrastructure.readers.postgres_identity_recovery_cleanup_proof_reader import (
        PostgresIdentityRecoveryCleanupProofReader,
    )
    from inframeld_backend.access.infrastructure.writers.postgres_identity_recovery_cleanup_proof_writer import (
        PostgresIdentityRecoveryCleanupProofWriter,
    )

    older = await _prepare(database, password_saved=False)
    async with database.session() as session:
        row = await session.get(IdentityRecoveryAdmissionRow, older.recovery_operation_id.value)
        assert row is not None
        identity = VerifiedHumanIdentityDTO(AUTHORITY, IdentitySubject(row.subject))
    newer = await _prepare(database, identity=identity)
    revoker = Revoker()
    revoker.cli = CONFIRMED
    await _execute(database, revoker)
    async with database.session() as session, session.begin():
        coordinated = await PostgresIdentityRecoveryCompletionFactsReader(session).read(
            installation_id=older.expected_installation_id,
            authority=AUTHORITY,
            flow_id=IdentityRecoveryFlowId(row.flow_id),
        )
        proof = await PostgresIdentityRecoveryCleanupProofReader(
            session, installation_id=older.expected_installation_id, authority=AUTHORITY
        ).read_proof(newer.recovery_operation_id)
        assert proof is not None
        await PostgresIdentityRecoveryCleanupProofWriter(
            session, installation_id=older.expected_installation_id, authority=AUTHORITY
        ).apply_to_covered(proof, coordinated.admission, at=datetime.now(UTC))
    result = await _resume(older, temporary_postgres_settings)
    assert result["outcome"] == "cleanup-confirmed"
    async with database.session() as session:
        assert (
            await session.get(IdentityRecoveryCleanupJobRow, older.recovery_operation_id.value)
            is None
        )
        assert (
            await session.scalar(select(func.count()).select_from(IdentityRecoveryCleanupRunRow))
            == 1
        )


async def test_new_run_preserves_confirmed_step_and_its_attribution(
    database: Database, temporary_postgres_settings: DatabaseSettings
) -> None:
    command = await _prepare(database)
    revoker = Revoker()
    revoker.cli, revoker.logins = CONFIRMED, REJECTED
    await _execute(database, revoker)
    async with database.session() as session:
        job = await session.get(IdentityRecoveryCleanupJobRow, command.recovery_operation_id.value)
        assert job is not None and job.cli_confirmation_attempt_id is not None
        first_confirmation = job.cli_confirmation_attempt_id
    await _resume(command, temporary_postgres_settings)
    revoker.logins = CONFIRMED
    await _execute(database, revoker)
    assert revoker.calls == ["cli", "login", "login"]
    async with database.session() as session:
        job = await session.get(IdentityRecoveryCleanupJobRow, command.recovery_operation_id.value)
        assert job is not None and job.cli_confirmation_attempt_id == first_confirmation
        assert job.login_confirmation_attempt_id != first_confirmation


@pytest.mark.parametrize("status_value", ["suspended", "retired"])
async def test_host_continuation_does_not_restore_account_or_repeat_ineligible_checks(
    database: Database, temporary_postgres_settings: DatabaseSettings, status_value: str
) -> None:
    from tests.support.access_scenarios import MockAccessScenarios

    from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
    from inframeld_backend.access.infrastructure.rows.identity_recovery_cleanup_proof_row import (
        IdentityRecoveryCleanupProofRow,
    )
    from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
    from inframeld_backend.bootstrap.recovery_completion_operation import (
        RecoveryCompletionOperation,
    )

    identity = VerifiedHumanIdentityDTO(AUTHORITY, IdentitySubject(str(uuid4())))
    async with database.session() as session, session.begin():
        principal = await MockAccessScenarios.seed_linked_human(
            session, identity, status=PrincipalStatus(status_value)
        )
    command = await _prepare(database, identity=identity)
    revoker = Revoker()
    await _execute(database, revoker)
    await _resume(command, temporary_postgres_settings)
    revoker.cli = CONFIRMED
    await _execute(database, revoker)
    await RecoveryCompletionOperation(
        database, installation_id=command.expected_installation_id, authority=AUTHORITY
    ).reconcile_proof(operation_id=command.recovery_operation_id)
    async with database.session() as session:
        proof = await session.get(
            IdentityRecoveryCleanupProofRow, command.recovery_operation_id.value
        )
        assert (
            proof is not None
            and proof.release_status == "ineligible"
            and proof.checked_at is not None
        )
        original_check = proof.checked_at
    no_work = await _resume(
        replace(command, operation_id=OperationId(str(uuid4()))), temporary_postgres_settings
    )
    assert no_work["outcome"] == "cleanup-confirmed" and no_work["released"] is False
    async with database.session() as session:
        proof = await session.get(
            IdentityRecoveryCleanupProofRow, command.recovery_operation_id.value
        )
        account = await session.get(PrincipalRow, principal.id.value)
        admission = await session.get(
            IdentityRecoveryAdmissionRow, command.recovery_operation_id.value
        )
        assert proof is not None and proof.checked_at == original_check
        assert account is not None and account.status is PrincipalStatus(status_value)
        assert admission is not None and admission.released_at is None
        assert (
            await session.scalar(select(func.count()).select_from(IdentityRecoveryCleanupRunRow))
            == 2
        )
