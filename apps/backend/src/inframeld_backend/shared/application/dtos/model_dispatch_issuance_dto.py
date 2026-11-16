from dataclasses import dataclass

from inframeld_backend.shared.application.value_objects.job_fence import JobFence
from inframeld_backend.shared.application.value_objects.job_id import JobId
from inframeld_backend.shared.application.value_objects.model_call_id import ModelCallId
from inframeld_backend.shared.application.value_objects.model_connection_id import ModelConnectionId


@dataclass(frozen=True, slots=True)
class ModelDispatchIssuanceDTO:
    """Retain the issuing fence and actual revisions without carrying authority or credentials."""

    call_id: ModelCallId
    job_id: JobId
    attempt_number: int
    fence: JobFence
    connection_id: ModelConnectionId
    access_revision: int
    credential_revision: int
    adapter_revision: str
