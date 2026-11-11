from dataclasses import replace

from tests.support.mock_project_upload_defaults import COMMAND, A, B

from inframeld_backend.access.application.services.project_upload_default_fingerprint_service import (
    ProjectUploadDefaultFingerprintService,
)
from inframeld_backend.access.domain.value_objects.upload_audience import UploadAudience
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.request_fingerprint_key import (
    RequestFingerprintKey,
)


def test_request_identity_uses_the_canonical_set_and_review() -> None:
    service = ProjectUploadDefaultFingerprintService(
        RequestFingerprintService(RequestFingerprintKey(b"f" * 32))
    )
    first = replace(COMMAND, audience=UploadAudience((A, B)))
    same = replace(COMMAND, audience=UploadAudience((B, A)))
    assert service.for_set(first) == service.for_set(same)
    assert service.for_set(first) != service.for_set(replace(first, expected_access_revision=8))
    assert service.for_set(first) != service.for_set(COMMAND)
