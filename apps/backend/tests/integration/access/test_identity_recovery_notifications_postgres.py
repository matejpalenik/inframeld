"""Persist native evidence without provider calls or recovery release."""

import os
from dataclasses import replace
from datetime import timedelta
from uuid import UUID

import pytest
from sqlalchemy import func, select
from tests.support.recovery_notifications import notification_service

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
from inframeld_backend.access.infrastructure.rows.human_credential_version_row import (
    HumanCredentialVersionRow,
)
from inframeld_backend.access.infrastructure.rows.identity_recovery_admission_row import (
    IdentityRecoveryAdmissionRow,
)
from inframeld_backend.access.infrastructure.rows.identity_recovery_cleanup_job_row import (
    IdentityRecoveryCleanupJobRow,
)
from inframeld_backend.access.infrastructure.rows.identity_recovery_cleanup_run_row import (
    IdentityRecoveryCleanupRunRow,
)
from inframeld_backend.access.infrastructure.rows.identity_recovery_evidence_receipt_row import (
    IdentityRecoveryEvidenceReceiptRow,
)
from inframeld_backend.access.infrastructure.rows.identity_recovery_proof_link_row import (
    IdentityRecoveryProofLinkRow,
)
from inframeld_backend.shared.application.errors.application_errors import ConflictError
from inframeld_backend.shared.infrastructure.readers.postgres_installation_identity_reader import (
    PostgresInstallationIdentityReader,
)
from inframeld_backend.shared.infrastructure.resources.database import Database

pytestmark = pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
    reason="Requires PostgreSQL integration services",
)
AUTHORITY = IdentityAuthority("https://identity.example.test")
EVENT = IdentityRecoveryEventDTO(
    IdentityRecoveryFlowId(UUID(int=2)),
    VerifiedHumanIdentityDTO(AUTHORITY, IdentitySubject(str(UUID(int=3)))),
    IdentityRecoveryEventKind.RECOVERY,
)
EVIDENCE = IdentityRecoverySettingsEvidenceDTO(
    EVENT.identity,
    IdentitySettingsFlowId(UUID(int=4)),
    IdentitySessionId(UUID(int=5)),
    EVENT.flow_id,
)


@pytest.mark.asyncio
async def test_native_receipts_replay_original_operation_and_preserve_one_budget(
    database: Database,
) -> None:
    installation = await PostgresInstallationIdentityReader(database).read()
    async with database.session() as session:
        first = await notification_service(session, installation, AUTHORITY).admit(EVENT)
    for _ in range(2):
        async with database.session() as session:
            service = notification_service(session, installation, AUTHORITY)
            assert await service.admit(EVENT) == first
            result = await service.associate_settings(EVIDENCE)
            assert result is not None and result.operation_id == first.operation_id
    for _ in range(2):
        async with database.session() as session:
            result = await notification_service(
                session, installation, AUTHORITY
            ).record_password_saved(EVIDENCE)
            assert result is not None and result.operation_id == first.operation_id
    async with database.session() as session:
        assert (
            await session.scalar(
                select(func.count()).select_from(IdentityRecoveryEvidenceReceiptRow)
            )
            == 3
        )
        assert (
            await session.scalar(select(func.count()).select_from(IdentityRecoveryCleanupJobRow))
            == 1
        )
        run = (await session.scalars(select(IdentityRecoveryCleanupRunRow))).one()
        job = (await session.scalars(select(IdentityRecoveryCleanupJobRow))).one()
        admission = await session.get(IdentityRecoveryAdmissionRow, first.operation_id.value)
        assert admission is not None
        assert (
            admission.kratos_cleanup_state,
            admission.hydra_cleanup_state,
            admission.released_at,
        ) == (State.CONFIRMED, State.PENDING, None)
        assert (job.cli_grants_state, job.remembered_logins_state) == ("pending", "pending")
        assert run.authorized_at == job.eligible_at == run.next_attempt_at
        assert run.deadline - run.authorized_at == timedelta(hours=1)
        assert (run.max_attempts, run.consumed_attempts, run.ended_at) == (12, 0, None)
        assert await session.scalar(select(HumanCredentialVersionRow.version)) == 2


@pytest.mark.asyncio
async def test_ordinary_settings_do_not_initialize_identity_or_recovery(database: Database) -> None:
    installation = await PostgresInstallationIdentityReader(database).read()
    ordinary = replace(EVIDENCE, source_recovery_flow_id=None)
    async with database.session() as session:
        service = notification_service(session, installation, AUTHORITY)
        assert await service.associate_settings(ordinary) is None
        assert await service.record_password_saved(ordinary) is None
    async with database.session() as session:
        assert (
            await session.scalar(select(func.count()).select_from(IdentityRecoveryAdmissionRow))
            == 0
        )
        assert (
            await session.scalar(select(func.count()).select_from(HumanCredentialVersionRow)) == 0
        )
        assert (
            await session.scalar(
                select(func.count()).select_from(IdentityRecoveryEvidenceReceiptRow)
            )
            == 0
        )


@pytest.mark.asyncio
async def test_restart_inherits_session_but_wrong_binding_cannot_move_it(
    database: Database,
) -> None:
    installation = await PostgresInstallationIdentityReader(database).read()
    async with database.session() as session:
        service = notification_service(session, installation, AUTHORITY)
        first = await service.admit(EVENT)
        await service.associate_settings(EVIDENCE)
        restarted = replace(
            EVIDENCE,
            settings_flow_id=IdentitySettingsFlowId(UUID(int=7)),
            source_recovery_flow_id=None,
        )
        result = await service.associate_settings(restarted)
        assert result is not None and result.operation_id == first.operation_id
        assert await service.record_password_saved(restarted) is not None
    for invalid in [
        replace(EVIDENCE, session_id=IdentitySessionId(UUID(int=8))),
        replace(
            EVIDENCE, identity=replace(EVENT.identity, subject=IdentitySubject(str(UUID(int=9))))
        ),
        replace(EVIDENCE, source_recovery_flow_id=IdentityRecoveryFlowId(UUID(int=10))),
    ]:
        async with database.session() as session:
            with pytest.raises(ConflictError):
                await notification_service(session, installation, AUTHORITY).associate_settings(
                    invalid
                )


@pytest.mark.asyncio
async def test_password_evidence_cannot_create_missing_settings_association(
    database: Database,
) -> None:
    installation = await PostgresInstallationIdentityReader(database).read()
    async with database.session() as session:
        service = notification_service(session, installation, AUTHORITY)
        await service.admit(EVENT)
        with pytest.raises(ConflictError):
            await service.record_password_saved(EVIDENCE)
    async with database.session() as session:
        assert (
            await session.scalar(select(func.count()).select_from(IdentityRecoveryCleanupJobRow))
            == 0
        )
        assert (
            await session.scalar(select(IdentityRecoveryAdmissionRow.kratos_cleanup_state))
            is State.PENDING
        )


@pytest.mark.asyncio
async def test_new_admission_captures_only_prior_same_identity_obligations(
    database: Database,
) -> None:
    installation = await PostgresInstallationIdentityReader(database).read()
    newer = replace(EVENT, flow_id=IdentityRecoveryFlowId(UUID(int=20)))
    latest = replace(EVENT, flow_id=IdentityRecoveryFlowId(UUID(int=21)))
    bob = replace(
        EVENT,
        flow_id=IdentityRecoveryFlowId(UUID(int=22)),
        identity=replace(EVENT.identity, subject=IdentitySubject(str(UUID(int=23)))),
    )
    async with database.session() as session:
        service = notification_service(session, installation, AUTHORITY)
        old = await service.admit(EVENT)
        await service.admit(bob)
        new = await service.admit(newer)
        last = await service.admit(latest)
        assert await service.admit(newer) == new
    async with database.session() as session:
        links = set(
            (
                await session.execute(
                    select(
                        IdentityRecoveryProofLinkRow.covering_operation_id,
                        IdentityRecoveryProofLinkRow.covered_operation_id,
                    )
                )
            ).tuples()
        )
        assert links == {
            (new.operation_id.value, old.operation_id.value),
            (last.operation_id.value, old.operation_id.value),
            (last.operation_id.value, new.operation_id.value),
        }
        assert (
            await session.scalar(
                select(HumanCredentialVersionRow.version).where(
                    HumanCredentialVersionRow.subject == EVENT.identity.subject.value
                )
            )
            == 4
        )


@pytest.mark.asyncio
async def test_failed_commit_rolls_back_admission_receipt_and_version(database: Database) -> None:
    from sqlalchemy import event

    installation = await PostgresInstallationIdentityReader(database).read()

    def fail_commit(_session: object) -> None:
        raise RuntimeError("Injected commit failure.")

    async with database.session() as session:
        event.listen(session.sync_session, "before_commit", fail_commit)
        with pytest.raises(RuntimeError, match="Injected commit"):
            await notification_service(session, installation, AUTHORITY).admit(EVENT)
        event.remove(session.sync_session, "before_commit", fail_commit)
    async with database.session() as session:
        assert (
            await session.scalar(select(func.count()).select_from(IdentityRecoveryAdmissionRow))
            == 0
        )
        assert (
            await session.scalar(
                select(func.count()).select_from(IdentityRecoveryEvidenceReceiptRow)
            )
            == 0
        )
        assert (
            await session.scalar(select(func.count()).select_from(HumanCredentialVersionRow)) == 0
        )


@pytest.mark.asyncio
async def test_concurrent_password_receipts_preserve_single_original_budget(
    database: Database,
) -> None:
    import asyncio

    installation = await PostgresInstallationIdentityReader(database).read()
    async with database.session() as session:
        service = notification_service(session, installation, AUTHORITY)
        admission = await service.admit(EVENT)
        await service.associate_settings(EVIDENCE)

    async def complete() -> object:
        async with database.session() as session:
            return await notification_service(
                session, installation, AUTHORITY
            ).record_password_saved(EVIDENCE)

    async with asyncio.timeout(10):
        first, second = await asyncio.gather(complete(), complete())
    assert first == second
    async with database.session() as session:
        assert (
            await session.scalar(select(func.count()).select_from(IdentityRecoveryCleanupRunRow))
            == 1
        )
        assert (
            await session.scalar(select(IdentityRecoveryCleanupJobRow.operation_id))
            == admission.operation_id.value
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("released", [False, True])
async def test_already_confirmed_or_released_recovery_creates_no_cleanup_work(
    database: Database,
    released: bool,
) -> None:
    from sqlalchemy import update

    installation = await PostgresInstallationIdentityReader(database).read()
    async with database.session() as session:
        service = notification_service(session, installation, AUTHORITY)
        result = await service.admit(EVENT)
        await service.associate_settings(EVIDENCE)
    async with database.session() as session, session.begin():
        await session.execute(
            update(IdentityRecoveryAdmissionRow).values(
                kratos_cleanup_state=State.CONFIRMED,
                hydra_cleanup_state=State.CONFIRMED,
                released_at=func.now() if released else None,
            )
        )
    async with database.session() as session:
        recorded = await notification_service(
            session, installation, AUTHORITY
        ).record_password_saved(EVIDENCE)
        assert recorded is not None and recorded.operation_id == result.operation_id
    async with database.session() as session:
        assert (
            await session.scalar(select(func.count()).select_from(IdentityRecoveryCleanupJobRow))
            == 0
        )
        assert (
            await session.scalar(select(func.count()).select_from(IdentityRecoveryCleanupRunRow))
            == 0
        )


@pytest.mark.asyncio
async def test_cancellation_after_handoff_writes_rolls_back_all_password_progress(
    database: Database,
) -> None:
    import asyncio
    from collections.abc import AsyncGenerator
    from contextlib import asynccontextmanager
    from typing import override

    from inframeld_backend.access.application.services.identity_recovery_admission_service import (
        IdentityRecoveryAdmissionService,
    )
    from inframeld_backend.access.application.services.identity_recovery_notification_service import (
        IdentityRecoveryNotificationService,
    )
    from inframeld_backend.access.infrastructure.readers.postgres_identity_recovery_association_facts_reader import (
        PostgresIdentityRecoveryAssociationFactsReader,
    )
    from inframeld_backend.access.infrastructure.repositories.postgres_identity_recovery_repository import (
        PostgresIdentityRecoveryRepository,
    )
    from inframeld_backend.access.infrastructure.writers.postgres_identity_recovery_admission_writer import (
        PostgresIdentityRecoveryAdmissionWriter,
    )
    from inframeld_backend.access.infrastructure.writers.postgres_identity_recovery_evidence_writer import (
        PostgresIdentityRecoveryEvidenceWriter,
    )
    from inframeld_backend.shared.application.protocols.transaction_manager import (
        TransactionManager,
    )
    from inframeld_backend.shared.infrastructure.resources.sqlalchemy_transaction_manager import (
        SqlAlchemyTransactionManager,
    )

    installation = await PostgresInstallationIdentityReader(database).read()
    async with database.session() as session:
        service = notification_service(session, installation, AUTHORITY)
        await service.admit(EVENT)
        await service.associate_settings(EVIDENCE)
    written = asyncio.Event()

    class PausedCommit(TransactionManager):
        @override
        @asynccontextmanager
        async def begin(self) -> AsyncGenerator[None]:
            async with SqlAlchemyTransactionManager(session).begin():
                yield
                written.set()
                await asyncio.Event().wait()

    async with database.session() as session:
        service = IdentityRecoveryNotificationService(
            PausedCommit(),
            IdentityRecoveryAdmissionService(
                PostgresIdentityRecoveryAdmissionWriter(
                    session, installation_id=installation, authority=AUTHORITY
                )
            ),
            PostgresIdentityRecoveryEvidenceWriter(
                session, installation_id=installation, authority=AUTHORITY
            ),
            PostgresIdentityRecoveryRepository(session),
            installation_id=installation,
            facts=PostgresIdentityRecoveryAssociationFactsReader(
                session, installation_id=installation, authority=AUTHORITY
            ),
        )
        task = asyncio.create_task(service.record_password_saved(EVIDENCE))
        try:
            await asyncio.wait_for(written.wait(), 2)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
    async with database.session() as session:
        assert (
            await session.scalar(select(IdentityRecoveryAdmissionRow.kratos_cleanup_state))
            is State.PENDING
        )
        assert (
            await session.scalar(
                select(func.count()).select_from(IdentityRecoveryEvidenceReceiptRow)
            )
            == 2
        )
        assert (
            await session.scalar(select(func.count()).select_from(IdentityRecoveryCleanupJobRow))
            == 0
        )
        assert (
            await session.scalar(select(func.count()).select_from(IdentityRecoveryCleanupRunRow))
            == 0
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["suspended", "retired"])
async def test_ineligible_account_still_records_cleanup_without_releasing_access(
    database: Database, status: str
) -> None:
    from sqlalchemy import update
    from tests.support.access_scenarios import MockAccessScenarios

    from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
    from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow

    installation = await PostgresInstallationIdentityReader(database).read()
    async with database.session() as session, session.begin():
        principal = await MockAccessScenarios.seed_linked_human(session, EVENT.identity)
        await session.execute(
            update(PrincipalRow)
            .where(PrincipalRow.id == principal.id.value)
            .values(status=PrincipalStatus(status))
        )
    async with database.session() as session:
        service = notification_service(session, installation, AUTHORITY)
        result = await service.admit(EVENT)
        await service.associate_settings(EVIDENCE)
        assert await service.record_password_saved(EVIDENCE) is not None
    async with database.session() as session:
        row = await session.get(IdentityRecoveryAdmissionRow, result.operation_id.value)
        assert row is not None
        assert row.kratos_cleanup_state is State.CONFIRMED
        assert row.released_at is None
        assert (
            await session.scalar(select(func.count()).select_from(IdentityRecoveryCleanupJobRow))
            == 1
        )


@pytest.mark.asyncio
async def test_missing_original_version_refuses_settings_without_reinitialization(
    database: Database,
) -> None:
    from sqlalchemy import delete

    from inframeld_backend.shared.application.errors.application_errors import (
        DependencyUnavailableError,
    )

    installation = await PostgresInstallationIdentityReader(database).read()
    async with database.session() as session:
        await notification_service(session, installation, AUTHORITY).admit(EVENT)
    async with database.session() as session, session.begin():
        await session.execute(delete(HumanCredentialVersionRow))
    async with database.session() as session:
        with pytest.raises(DependencyUnavailableError):
            await notification_service(session, installation, AUTHORITY).associate_settings(
                EVIDENCE
            )
    async with database.session() as session:
        assert (
            await session.scalar(select(func.count()).select_from(HumanCredentialVersionRow)) == 0
        )
        assert (
            await session.scalar(
                select(func.count()).select_from(IdentityRecoveryEvidenceReceiptRow)
            )
            == 1
        )
        assert (
            await session.scalar(select(func.count()).select_from(IdentityRecoveryCleanupJobRow))
            == 0
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("wrong_scope", [False, True])
async def test_database_rejects_invalid_receipt_kind_or_identity_binding(
    database: Database, wrong_scope: bool
) -> None:
    from uuid import uuid4

    from sqlalchemy.exc import IntegrityError

    from inframeld_backend.access.application.enums.identity_recovery_evidence_type import (
        IdentityRecoveryEvidenceType,
    )

    installation = await PostgresInstallationIdentityReader(database).read()
    async with database.session() as session:
        result = await notification_service(session, installation, AUTHORITY).admit(EVENT)
    async with database.session() as session:
        with pytest.raises(IntegrityError):
            async with session.begin():
                session.add(
                    IdentityRecoveryEvidenceReceiptRow(
                        id=uuid4(),
                        installation_id=installation.value,
                        authority=AUTHORITY.value,
                        subject=str(UUID(int=99)) if wrong_scope else EVENT.identity.subject.value,
                        operation_id=result.operation_id.value,
                        event_type=IdentityRecoveryEvidenceType.RECOVERY_CODE_VERIFIED,
                        native_flow_id=uuid4(),
                        session_id=None,
                        source_recovery_flow_id=None,
                        event_kind=IdentityRecoveryEventKind.RECOVERY if wrong_scope else None,
                    )
                )
                await session.flush()
    async with database.session() as session:
        assert (
            await session.scalar(
                select(func.count()).select_from(IdentityRecoveryEvidenceReceiptRow)
            )
            == 1
        )


@pytest.mark.asyncio
async def test_database_prevents_parallel_active_cleanup_runs(database: Database) -> None:
    from uuid import uuid4

    from sqlalchemy.exc import IntegrityError

    installation = await PostgresInstallationIdentityReader(database).read()
    async with database.session() as session:
        service = notification_service(session, installation, AUTHORITY)
        await service.admit(EVENT)
        await service.associate_settings(EVIDENCE)
        await service.record_password_saved(EVIDENCE)
    async with database.session() as session:
        original = (await session.scalars(select(IdentityRecoveryCleanupRunRow))).one()
    async with database.session() as session:
        with pytest.raises(IntegrityError):
            async with session.begin():
                session.add(
                    IdentityRecoveryCleanupRunRow(
                        id=uuid4(),
                        operation_id=original.operation_id,
                        authorization_source=original.authorization_source,
                        authorized_at=original.authorized_at,
                        deadline=original.deadline,
                        next_attempt_at=original.next_attempt_at,
                    )
                )
                await session.flush()
    async with database.session() as session:
        assert (
            await session.scalar(select(func.count()).select_from(IdentityRecoveryCleanupRunRow))
            == 1
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("bound", [False, True])
async def test_association_facts_report_candidates_and_binding_mismatches(
    database: Database, bound: bool
) -> None:
    from inframeld_backend.access.application.services.identity_recovery_admission_service import (
        IdentityRecoveryAdmissionService,
    )
    from inframeld_backend.access.infrastructure.readers.postgres_identity_recovery_association_facts_reader import (
        PostgresIdentityRecoveryAssociationFactsReader,
    )
    from inframeld_backend.access.infrastructure.rows.identity_recovery_session_binding_row import (
        IdentityRecoverySessionBindingRow,
    )
    from inframeld_backend.access.infrastructure.rows.identity_recovery_settings_binding_row import (
        IdentityRecoverySettingsBindingRow,
    )
    from inframeld_backend.access.infrastructure.writers.postgres_identity_recovery_admission_writer import (
        PostgresIdentityRecoveryAdmissionWriter,
    )

    installation = await PostgresInstallationIdentityReader(database).read()
    async with database.session() as session, session.begin():
        operation = await IdentityRecoveryAdmissionService(
            PostgresIdentityRecoveryAdmissionWriter(
                session, installation_id=installation, authority=AUTHORITY
            )
        ).admit(EVENT)
        if bound:
            session.add(
                IdentityRecoverySessionBindingRow(
                    installation_id=installation.value,
                    authority=AUTHORITY.value,
                    subject=EVENT.identity.subject.value,
                    operation_id=operation.value,
                    session_id=EVIDENCE.session_id.value,
                )
            )
            session.add(
                IdentityRecoverySettingsBindingRow(
                    installation_id=installation.value,
                    authority=AUTHORITY.value,
                    subject=EVENT.identity.subject.value,
                    operation_id=operation.value,
                    settings_flow_id=EVIDENCE.settings_flow_id.value,
                    session_id=EVIDENCE.session_id.value,
                    source_recovery_flow_id=EVENT.flow_id.value,
                )
            )
    # Wrong incoming identity must not hide the stored bindings from the application.
    incoming = (
        replace(
            EVIDENCE, identity=replace(EVENT.identity, subject=IdentitySubject(str(UUID(int=999))))
        )
        if bound
        else EVIDENCE
    )
    async with database.session() as session, session.begin():
        facts = await PostgresIdentityRecoveryAssociationFactsReader(
            session, installation_id=installation, authority=AUTHORITY
        ).read(incoming)
    assert facts.source_admission is not None
    assert facts.source_admission.event == EVENT
    assert facts.source_admission.operation_id == operation
    if bound:
        assert facts.session_binding is not None and facts.settings_binding is not None
        assert facts.session_binding.identity == facts.settings_binding.identity == EVENT.identity
        assert facts.session_admission == facts.settings_admission == facts.source_admission
        assert facts.current_version is None
    else:
        assert facts.session_binding is None and facts.settings_binding is None
        assert facts.session_admission is None and facts.settings_admission is None
        assert facts.current_version is not None and facts.current_version.value == 2


@pytest.mark.asyncio
async def test_later_password_event_preserves_original_run_and_confirmed_progress(
    database: Database,
) -> None:
    from sqlalchemy import update

    installation = await PostgresInstallationIdentityReader(database).read()
    async with database.session() as session:
        service = notification_service(session, installation, AUTHORITY)
        await service.admit(EVENT)
        await service.associate_settings(EVIDENCE)
        await service.record_password_saved(EVIDENCE)
    async with database.session() as session, session.begin():
        run = (await session.scalars(select(IdentityRecoveryCleanupRunRow))).one()
        job = (await session.scalars(select(IdentityRecoveryCleanupJobRow))).one()
        original = (
            run.id,
            run.authorized_at,
            run.deadline,
            run.next_attempt_at,
            job.evidence_receipt_id,
        )
        await session.execute(update(IdentityRecoveryCleanupRunRow).values(consumed_attempts=3))
        await session.execute(
            update(IdentityRecoveryCleanupJobRow).values(cli_grants_state="confirmed")
        )
    restarted = replace(
        EVIDENCE,
        settings_flow_id=IdentitySettingsFlowId(UUID(int=50)),
        source_recovery_flow_id=None,
    )
    async with database.session() as session:
        service = notification_service(session, installation, AUTHORITY)
        await service.associate_settings(restarted)
        await service.record_password_saved(restarted)
    async with database.session() as session:
        run = (await session.scalars(select(IdentityRecoveryCleanupRunRow))).one()
        job = (await session.scalars(select(IdentityRecoveryCleanupJobRow))).one()
        assert (
            run.id,
            run.authorized_at,
            run.deadline,
            run.next_attempt_at,
            job.evidence_receipt_id,
        ) == original
        assert run.consumed_attempts == 3 and run.max_attempts == 12
        assert (job.cli_grants_state, job.remembered_logins_state) == ("confirmed", "pending")
        password_receipts = (
            await session.scalars(
                select(IdentityRecoveryEvidenceReceiptRow).where(
                    IdentityRecoveryEvidenceReceiptRow.event_type == "password-settings-saved"
                )
            )
        ).all()
        assert len(password_receipts) == 2
        assert {row.native_flow_id for row in password_receipts} == {
            EVIDENCE.settings_flow_id.value,
            restarted.settings_flow_id.value,
        }
