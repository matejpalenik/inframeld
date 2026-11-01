from dataclasses import dataclass
from datetime import datetime

from inframeld_backend.shared.application.dtos.deletion_status_binding_dto import (
    DeletionStatusBindingDTO,
)
from inframeld_backend.shared.application.dtos.deletion_status_obligation_provenance_dto import (
    DeletionStatusObligationProvenanceDTO,
)
from inframeld_backend.shared.domain.enums.job_status import JobStatus


@dataclass(frozen=True, slots=True)
class DeletionStatusObservationDTO:
    """Report retained owner observations and database time, without creating their proof.

    An absent owner revision denotes binding-only history. Unknown confirmations
    remain None. Source-specific admission and cleanup writers are separate work.
    """

    binding: DeletionStatusBindingDTO
    observed_at: datetime
    owner_revision: int | None = None
    owner_observed_at: datetime | None = None
    job_status: JobStatus | None = None
    admission_confirmed: bool | None = None
    access_blocked: bool | None = None
    application_shutdown_complete: bool | None = None
    physical_cleanup_complete: bool | None = None
    unfinished_obligation: DeletionStatusObligationProvenanceDTO | None = None
    retention_started_at: datetime | None = None
    expires_at: datetime | None = None
