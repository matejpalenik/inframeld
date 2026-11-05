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
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
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
from inframeld_backend.access.infrastructure.rows.identity_recovery_cleanup_step_row import (
    IdentityRecoveryCleanupStepRow,
)
from inframeld_backend.access.infrastructure.rows.identity_recovery_evidence_receipt_row import (
    IdentityRecoveryEvidenceReceiptRow,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


class PostgresIdentityRecoveryCleanupWorkMapper:
    """Convert saved cleanup records without selecting a run or granting authority."""

    @staticmethod
    def from_rows(
        installation_id: InstallationId,
        job: IdentityRecoveryCleanupJobRow,
        run: IdentityRecoveryCleanupRunRow,
        admission: IdentityRecoveryAdmissionRow,
        receipt: IdentityRecoveryEvidenceReceiptRow,
        version: HumanCredentialVersionRow | None,
        steps: tuple[IdentityRecoveryCleanupStepDTO, ...],
    ) -> IdentityRecoveryCleanupWorkDTO:
        operation_id = OperationId(admission.operation_id)
        identity = VerifiedHumanIdentityDTO(
            IdentityAuthority(admission.authority), IdentitySubject(admission.subject)
        )
        binding = (installation_id.value, identity.authority.value, identity.subject.value)
        if (
            job.installation_id,
            job.authority,
            job.subject,
        ) != binding or admission.installation_id != installation_id.value:
            raise RuntimeError("Cleanup records changed their original identity binding.")

        claim = None
        if job.active_attempt_id is not None:
            if job.worker_id is None or job.ownership_token is None or job.lease_expires_at is None:
                raise RuntimeError("The cleanup ownership record is incomplete.")
            claim = IdentityRecoveryCleanupClaimDTO(
                operation_id=operation_id,
                run_id=run.id,
                attempt_id=job.active_attempt_id,
                worker_id=job.worker_id,
                token=job.ownership_token,
                lease_expires_at=job.lease_expires_at,
            )

        return IdentityRecoveryCleanupWorkDTO(
            installation_id=installation_id,
            admission=IdentityRecoveryAdmissionDTO(
                IdentityRecoveryEventDTO(
                    IdentityRecoveryFlowId(admission.flow_id), identity, admission.event_kind
                ),
                operation_id,
            ),
            evidence_receipt_id=receipt.id,
            has_original_password_receipt=receipt.event_type
            is IdentityRecoveryEvidenceType.PASSWORD_SETTINGS_SAVED
            and (receipt.installation_id, receipt.authority, receipt.subject, receipt.operation_id)
            == (*binding, operation_id.value),
            credential_version=None if version is None else HumanCredentialVersion(version.version),
            kratos_cleanup_state=admission.kratos_cleanup_state,
            released_at=admission.released_at,
            cli_grants_state=job.cli_grants_state,
            remembered_logins_state=job.remembered_logins_state,
            cli_confirmation_attempt_id=job.cli_confirmation_attempt_id,
            login_confirmation_attempt_id=job.login_confirmation_attempt_id,
            run=IdentityRecoveryCleanupRunDTO(
                id=run.id,
                authorized_at=run.authorized_at,
                deadline=run.deadline,
                next_attempt_at=run.next_attempt_at,
                max_attempts=run.max_attempts,
                consumed_attempts=run.consumed_attempts,
                ended_at=run.ended_at,
                terminal_reason=run.terminal_reason,
            ),
            claim=claim,
            steps=steps,
        )

    @staticmethod
    def step(row: IdentityRecoveryCleanupStepRow) -> IdentityRecoveryCleanupStepDTO:
        outcome = None
        if row.state is not None:
            if row.disposition is None or row.category is None or row.checkpointed_at is None:
                raise RuntimeError("The cleanup checkpoint is incomplete.")
            outcome = HumanOAuthCleanupOutcomeDTO(
                row.state, row.disposition, row.category, row.http_status, row.retry_after_seconds
            )
        return IdentityRecoveryCleanupStepDTO(row.step, row.dispatched_at, outcome)
