from dataclasses import replace
from uuid import uuid4

from inframeld_backend.access.application.commands.update_project_metadata_command import (
    UpdateProjectMetadataCommand,
)
from inframeld_backend.access.application.services.project_metadata_fingerprint_service import (
    ProjectMetadataFingerprintService,
)
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.request_fingerprint_key import (
    RequestFingerprintKey,
)
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName
from inframeld_backend.shared.domain.value_objects.submitted_display_name import (
    SubmittedDisplayName,
)


def test_exact_request_meaning_distinguishes_omitted_labels_and_review_revision() -> None:
    service = ProjectMetadataFingerprintService(
        RequestFingerprintService(RequestFingerprintKey(b"K" * 32))
    )
    command = UpdateProjectMetadataCommand(ProjectId(uuid4()), 0, ResourceName("support"))
    original = service.for_update(command)
    assert original != service.for_update(replace(command, expected_metadata_revision=1))
    assert original != service.for_update(
        replace(command, display_name=SubmittedDisplayName("Support"))
    )
    assert service.for_update(
        replace(command, display_name=SubmittedDisplayName("é"))
    ) != service.for_update(replace(command, display_name=SubmittedDisplayName("e\u0301")))
