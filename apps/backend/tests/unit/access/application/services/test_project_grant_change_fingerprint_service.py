from dataclasses import replace
from uuid import UUID

from inframeld_backend.access.application.commands.remove_project_action_grant_command import (
    RemoveProjectActionGrantCommand,
)
from inframeld_backend.access.application.commands.set_project_action_grant_command import (
    SetProjectActionGrantCommand,
)
from inframeld_backend.access.application.services.project_grant_change_fingerprint_service import (
    ProjectGrantChangeFingerprintService,
)
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
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


def _historical_post_fingerprint() -> RequestFingerprint:
    """Reconstitute saved request identity without retaining a live POST command."""
    return RequestFingerprintService(RequestFingerprintKey(b"K" * 32)).fingerprint(
        purpose="access.project-grant.assign-use-only:v1",
        canonical_request=b'{"actionId":"create-access-groups","expectedAccessRevision":7,"projectId":"00000000-0000-0000-0000-000000000001","recipientPrincipalId":"00000000-0000-0000-0000-000000000002"}',
    )


def test_historical_post_fingerprint_keeps_the_original_saved_identity() -> None:
    assert (
        _historical_post_fingerprint().value.hex()
        == "318247e6c6ef37e22d5fefd65bb023dada7bac1fdc25003571ed739b7e34a10b"
    )


def test_full_mutations_have_stable_distinct_meaning_from_legacy_post() -> None:
    service = _service()
    setting = SetProjectActionGrantCommand(PROJECT_ID, RECIPIENT_ID, ACTION_ID, False, 7)
    removal = RemoveProjectActionGrantCommand(PROJECT_ID, RECIPIENT_ID, ACTION_ID, 7)
    legacy = _historical_post_fingerprint()
    assert service.for_set(setting) == service.for_set(replace(setting))
    assert service.for_remove(removal) == service.for_remove(replace(removal))
    assert (
        len(
            {
                service.for_set(setting),
                service.for_remove(removal),
                legacy,
            }
        )
        == 3
    )


def test_set_fingerprint_binds_recipient_scope_action_level_and_review() -> None:
    service = _service()
    command = SetProjectActionGrantCommand(PROJECT_ID, RECIPIENT_ID, ACTION_ID, False, 7)
    original = service.for_set(command)
    for changed in (
        replace(command, project_id=ProjectId(UUID(int=8))),
        replace(command, recipient_principal_id=PrincipalId(UUID(int=8))),
        replace(command, action_id=ActionId("inspect-budget")),
        replace(command, can_grant=True),
        replace(command, expected_access_revision=8),
    ):
        assert service.for_set(changed) != original


def test_remove_fingerprint_binds_recipient_scope_action_and_review() -> None:
    service = _service()
    command = RemoveProjectActionGrantCommand(PROJECT_ID, RECIPIENT_ID, ACTION_ID, 7)
    original = service.for_remove(command)
    for changed in (
        replace(command, project_id=ProjectId(UUID(int=8))),
        replace(command, recipient_principal_id=PrincipalId(UUID(int=8))),
        replace(command, action_id=ActionId("inspect-budget")),
        replace(command, expected_access_revision=8),
    ):
        assert service.for_remove(changed) != original
