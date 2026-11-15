from dataclasses import dataclass

from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.domain.value_objects.upload_audience import UploadAudience
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.request_id import RequestId


@dataclass(frozen=True, slots=True)
class UploadDocumentCommand:
    project_id: ProjectId
    audience: UploadAudience
    filename: str
    key: IdempotencyKey
    request_id: RequestId
