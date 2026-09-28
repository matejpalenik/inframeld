from uuid import UUID

from inframeld_backend.access.application.services.project_grant_change_fingerprint_service import (
    ProjectGrantChangeFingerprintService,
)
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.request_fingerprint_key import (
    RequestFingerprintKey,
)

PROJECT_ID = ProjectId(UUID(int=1))
RECIPIENT_ID = PrincipalId(UUID(int=2))
ACTION_ID = ActionId("create-access-groups")


def _service() -> ProjectGrantChangeFingerprintService:
    return ProjectGrantChangeFingerprintService(
        RequestFingerprintService(RequestFingerprintKey(b"K" * 32))
    )


def test_equivalent_grant_commands_have_the_same_fingerprint() -> None:
    """A retry with unchanged meaning can find its original operation."""
    service = _service()

    first = service.for_assign_use_only(
        project_id=PROJECT_ID,
        recipient_principal_id=RECIPIENT_ID,
        action_id=ACTION_ID,
        expected_access_revision=7,
    )
    retry = service.for_assign_use_only(
        project_id=PROJECT_ID,
        recipient_principal_id=RECIPIENT_ID,
        action_id=ACTION_ID,
        expected_access_revision=7,
    )

    assert first == retry
    assert len(first) == 32


def test_each_meaningful_grant_field_changes_the_fingerprint() -> None:
    """A reused key cannot silently change target, recipient, action, or revision."""
    service = _service()
    original = service.for_assign_use_only(
        project_id=PROJECT_ID,
        recipient_principal_id=RECIPIENT_ID,
        action_id=ACTION_ID,
        expected_access_revision=7,
    )

    assert original != service.for_assign_use_only(
        project_id=ProjectId(UUID(int=3)),
        recipient_principal_id=RECIPIENT_ID,
        action_id=ACTION_ID,
        expected_access_revision=7,
    )
    assert original != service.for_assign_use_only(
        project_id=PROJECT_ID,
        recipient_principal_id=PrincipalId(UUID(int=4)),
        action_id=ACTION_ID,
        expected_access_revision=7,
    )
    assert original != service.for_assign_use_only(
        project_id=PROJECT_ID,
        recipient_principal_id=RECIPIENT_ID,
        action_id=ActionId("delete-access-groups"),
        expected_access_revision=7,
    )
    assert original != service.for_assign_use_only(
        project_id=PROJECT_ID,
        recipient_principal_id=RECIPIENT_ID,
        action_id=ACTION_ID,
        expected_access_revision=8,
    )
