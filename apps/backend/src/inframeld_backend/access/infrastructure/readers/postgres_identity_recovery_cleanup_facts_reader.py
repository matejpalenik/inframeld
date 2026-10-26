from typing import override

from sqlalchemy import Nullable, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.human_oauth_cleanup_outcome_dto import (
    HumanOAuthCleanupOutcomeDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_admission_dto import (
    IdentityRecoveryAdmissionDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_cleanup_claim_dto import (
    IdentityRecoveryCleanupClaimDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_cleanup_run_dto import (
    IdentityRecoveryCleanupRunDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_cleanup_step_dto import (
    IdentityRecoveryCleanupStepDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_cleanup_work_dto import (
    IdentityRecoveryCleanupWorkDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_event_dto import (
    IdentityRecoveryEventDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.enums.identity_recovery_evidence_type import (
    IdentityRecoveryEvidenceType,
)
from inframeld_backend.access.application.protocols.identity_recovery_cleanup_facts_reader import (
    IdentityRecoveryCleanupFactsReader,
)
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_recovery_flow_id import (
    IdentityRecoveryFlowId,
)
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.infrastructure.resources.postgres_identity_coordinator import (
    PostgresIdentityCoordinator,
)
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
from inframeld_backend.access.infrastructure.rows.identity_recovery_cleanup_step_row import (
    IdentityRecoveryCleanupStepRow,
)
from inframeld_backend.access.infrastructure.rows.identity_recovery_evidence_receipt_row import (
    IdentityRecoveryEvidenceReceiptRow,
)
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.infrastructure.rows.installation_identity_row import (
    InstallationIdentityRow,
)


class PostgresIdentityRecoveryCleanupFactsReader(IdentityRecoveryCleanupFactsReader):
    def __init__(
        self,
        session: AsyncSession,
        *,
        installation_id: InstallationId,
        authority: IdentityAuthority,
    ) -> None:
        self._session = session
        self._installation_id = installation_id
        self._authority = authority

    async def _require_scope(self) -> None:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Cleanup observations require an active transaction.")
        installed = await self._session.scalar(
            select(InstallationIdentityRow.installation_id)
            .where(InstallationIdentityRow.singleton_key == 1)
            .execution_options(autoflush=False)
        )
        if installed != self._installation_id.value:
            raise DependencyUnavailableError("The installation identity is not available.")

    @override
    async def next_candidate(self) -> OperationId | None:
        await self._require_scope()
        result = await self._session.scalar(
            select(IdentityRecoveryCleanupJobRow.operation_id)
            .join(
                IdentityRecoveryCleanupRunRow,
                IdentityRecoveryCleanupRunRow.operation_id
                == IdentityRecoveryCleanupJobRow.operation_id,
            )
            .where(
                IdentityRecoveryCleanupJobRow.installation_id == self._installation_id.value,
                IdentityRecoveryCleanupJobRow.authority == self._authority.value,
                IdentityRecoveryCleanupRunRow.ended_at.is_(None),
                IdentityRecoveryCleanupRunRow.next_attempt_at <= func.now(),
                or_(
                    IdentityRecoveryCleanupJobRow.lease_expires_at.is_(None),
                    IdentityRecoveryCleanupJobRow.lease_expires_at <= func.now(),
                ),
            )
            .order_by(
                IdentityRecoveryCleanupRunRow.next_attempt_at,
                IdentityRecoveryCleanupJobRow.operation_id,
            )
            .limit(1)
            .execution_options(autoflush=False)
        )
        return None if result is None else OperationId(result)

    @override
    async def lock_work(self, operation_id: OperationId) -> IdentityRecoveryCleanupWorkDTO | None:
        await self._require_scope()
        subject = await self._session.scalar(
            select(IdentityRecoveryCleanupJobRow.subject)
            .where(
                IdentityRecoveryCleanupJobRow.operation_id == operation_id.value,
                IdentityRecoveryCleanupJobRow.installation_id == self._installation_id.value,
                IdentityRecoveryCleanupJobRow.authority == self._authority.value,
            )
            .execution_options(autoflush=False)
        )
        if subject is None:
            return None

        identity = VerifiedHumanIdentityDTO(self._authority, IdentitySubject(subject))
        await PostgresIdentityCoordinator(self._session).acquire(
            installation_id=self._installation_id, identity=identity
        )
        await self._require_scope()

        statement = (
            select(
                IdentityRecoveryCleanupJobRow,
                IdentityRecoveryCleanupRunRow,
                IdentityRecoveryAdmissionRow,
                IdentityRecoveryEvidenceReceiptRow,
                Nullable(HumanCredentialVersionRow),
            )
            .select_from(IdentityRecoveryCleanupJobRow)
            .join(
                IdentityRecoveryCleanupRunRow,
                IdentityRecoveryCleanupRunRow.operation_id
                == IdentityRecoveryCleanupJobRow.operation_id,
            )
            .join(
                IdentityRecoveryAdmissionRow,
                IdentityRecoveryAdmissionRow.operation_id
                == IdentityRecoveryCleanupJobRow.operation_id,
            )
            .join(
                IdentityRecoveryEvidenceReceiptRow,
                IdentityRecoveryEvidenceReceiptRow.id
                == IdentityRecoveryCleanupJobRow.evidence_receipt_id,
            )
            .outerjoin(
                HumanCredentialVersionRow,
                and_(
                    HumanCredentialVersionRow.installation_id
                    == IdentityRecoveryCleanupJobRow.installation_id,
                    HumanCredentialVersionRow.authority == IdentityRecoveryCleanupJobRow.authority,
                    HumanCredentialVersionRow.subject == IdentityRecoveryCleanupJobRow.subject,
                ),
            )
            .where(
                IdentityRecoveryCleanupJobRow.operation_id == operation_id.value,
                IdentityRecoveryCleanupJobRow.installation_id == self._installation_id.value,
                IdentityRecoveryCleanupJobRow.authority == self._authority.value,
                IdentityRecoveryCleanupRunRow.ended_at.is_(None),
            )
            .with_for_update(
                of=(IdentityRecoveryCleanupJobRow, IdentityRecoveryCleanupRunRow), skip_locked=True
            )
            .execution_options(populate_existing=True, autoflush=False)
        )
        result = (await self._session.execute(statement)).one_or_none()
        if result is None:
            return None

        job, run, admission, receipt, version = result
        binding = (self._installation_id.value, self._authority.value, subject)
        if (job.installation_id, job.authority, job.subject) != binding or (
            admission.installation_id,
            admission.authority,
            admission.subject,
        ) != binding:
            raise RuntimeError("Cleanup records changed their original identity binding.")

        claim = None
        if job.active_attempt_id is not None:
            if job.worker_id is None or job.ownership_token is None or job.lease_expires_at is None:
                raise RuntimeError("The cleanup ownership record is incomplete.")
            claim = IdentityRecoveryCleanupClaimDTO(
                operation_id,
                run.id,
                job.active_attempt_id,
                job.worker_id,
                job.ownership_token,
                job.lease_expires_at,
            )

        steps = ()
        if claim is not None:
            stored_steps = await self._session.scalars(
                select(IdentityRecoveryCleanupStepRow)
                .where(IdentityRecoveryCleanupStepRow.attempt_id == claim.attempt_id)
                .execution_options(populate_existing=True)
            )
            steps = tuple(self._step(row) for row in stored_steps)

        return IdentityRecoveryCleanupWorkDTO(
            self._installation_id,
            IdentityRecoveryAdmissionDTO(
                IdentityRecoveryEventDTO(
                    IdentityRecoveryFlowId(admission.flow_id), identity, admission.event_kind
                ),
                operation_id,
            ),
            receipt.id,
            receipt.event_type is IdentityRecoveryEvidenceType.PASSWORD_SETTINGS_SAVED
            and (receipt.installation_id, receipt.authority, receipt.subject, receipt.operation_id)
            == (*binding, operation_id.value),
            None if version is None else HumanCredentialVersion(version.version),
            admission.kratos_cleanup_state,
            admission.released_at,
            job.cli_grants_state,
            job.remembered_logins_state,
            job.cli_confirmation_attempt_id,
            job.login_confirmation_attempt_id,
            IdentityRecoveryCleanupRunDTO(
                run.id,
                run.authorized_at,
                run.deadline,
                run.next_attempt_at,
                run.max_attempts,
                run.consumed_attempts,
                run.ended_at,
                run.terminal_reason,
            ),
            claim,
            steps,
        )

    @staticmethod
    def _step(row: IdentityRecoveryCleanupStepRow) -> IdentityRecoveryCleanupStepDTO:
        outcome = None
        if row.state is not None:
            if row.disposition is None or row.category is None or row.checkpointed_at is None:
                raise RuntimeError("The cleanup checkpoint is incomplete.")
            outcome = HumanOAuthCleanupOutcomeDTO(
                row.state, row.disposition, row.category, row.http_status, row.retry_after_seconds
            )
        return IdentityRecoveryCleanupStepDTO(row.step, row.dispatched_at, outcome)
