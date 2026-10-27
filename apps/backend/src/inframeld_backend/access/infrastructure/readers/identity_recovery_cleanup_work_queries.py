from sqlalchemy import Nullable, Select, and_, select

from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
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
from inframeld_backend.access.infrastructure.rows.identity_recovery_evidence_receipt_row import (
    IdentityRecoveryEvidenceReceiptRow,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


class IdentityRecoveryCleanupWorkQueries:
    """Build the shared original-job projection without executing database work."""

    @staticmethod
    def statement(
        *,
        installation_id: InstallationId,
        identity: VerifiedHumanIdentityDTO,
        operation_id: OperationId,
        include_ended: bool = False,
        skip_locked: bool = True,
    ) -> Select[
        tuple[
            IdentityRecoveryCleanupJobRow,
            IdentityRecoveryCleanupRunRow,
            IdentityRecoveryAdmissionRow,
            IdentityRecoveryEvidenceReceiptRow,
            HumanCredentialVersionRow | None,
        ]
    ]:
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
                IdentityRecoveryCleanupJobRow.installation_id == installation_id.value,
                IdentityRecoveryCleanupJobRow.authority == identity.authority.value,
            )
            .execution_options(populate_existing=True, autoflush=False)
        )
        if not include_ended:
            statement = statement.where(IdentityRecoveryCleanupRunRow.ended_at.is_(None))
        return (
            statement.order_by(
                IdentityRecoveryCleanupRunRow.ended_at.is_(None).desc(),
                IdentityRecoveryCleanupRunRow.authorized_at.desc(),
                IdentityRecoveryCleanupRunRow.id.desc(),
            )
            .limit(1)
            .with_for_update(
                of=(IdentityRecoveryCleanupJobRow, IdentityRecoveryCleanupRunRow),
                skip_locked=skip_locked,
            )
        )
