from dataclasses import replace
from uuid import UUID

from inframeld_backend.access.application.commands.assign_project_use_only_grant_command import (
    AssignProjectUseOnlyGrantCommand,
)
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
        AssignProjectUseOnlyGrantCommand(
            project_id=PROJECT_ID,
            recipient_principal_id=RECIPIENT_ID,
            action_id=ACTION_ID,
            expected_access_revision=7,
        )
    )
    retry = service.for_assign_use_only(
        AssignProjectUseOnlyGrantCommand(
            project_id=PROJECT_ID,
            recipient_principal_id=RECIPIENT_ID,
            action_id=ACTION_ID,
            expected_access_revision=7,
        )
    )

    assert first == retry
    assert len(first.value) == 32


def test_each_meaningful_grant_field_changes_the_fingerprint() -> None:
    """A reused key cannot silently change target, recipient, action, or revision."""
    service = _service()
    original = service.for_assign_use_only(
        AssignProjectUseOnlyGrantCommand(
            project_id=PROJECT_ID,
            recipient_principal_id=RECIPIENT_ID,
            action_id=ACTION_ID,
            expected_access_revision=7,
        )
    )

    assert original != service.for_assign_use_only(
        AssignProjectUseOnlyGrantCommand(
            project_id=ProjectId(UUID(int=3)),
            recipient_principal_id=RECIPIENT_ID,
            action_id=ACTION_ID,
            expected_access_revision=7,
        )
    )
    assert original != service.for_assign_use_only(
        AssignProjectUseOnlyGrantCommand(
            project_id=PROJECT_ID,
            recipient_principal_id=PrincipalId(UUID(int=4)),
            action_id=ACTION_ID,
            expected_access_revision=7,
        )
    )
    assert original != service.for_assign_use_only(
        AssignProjectUseOnlyGrantCommand(
            project_id=PROJECT_ID,
            recipient_principal_id=RECIPIENT_ID,
            action_id=ActionId("delete-access-groups"),
            expected_access_revision=7,
        )
    )
    assert original != service.for_assign_use_only(
        AssignProjectUseOnlyGrantCommand(
            project_id=PROJECT_ID,
            recipient_principal_id=RECIPIENT_ID,
            action_id=ACTION_ID,
            expected_access_revision=8,
        )
    )


def test_fingerprint_matches_the_pre_refactor_contract() -> None:
    """Retained reservations must recognize requests made before the refactor."""
    command = AssignProjectUseOnlyGrantCommand(
        project_id=PROJECT_ID,
        recipient_principal_id=RECIPIENT_ID,
        action_id=ACTION_ID,
        expected_access_revision=7,
    )
    assert _service().for_assign_use_only(command).value.hex() == (
        "318247e6c6ef37e22d5fefd65bb023dada7bac1fdc25003571ed739b7e34a10b"
    )


def test_full_mutations_have_stable_distinct_meaning_from_legacy_post() -> None:
    service = _service()
    setting = SetProjectActionGrantCommand(PROJECT_ID, RECIPIENT_ID, ACTION_ID, False, 7)
    removal = RemoveProjectActionGrantCommand(PROJECT_ID, RECIPIENT_ID, ACTION_ID, 7)
    legacy = AssignProjectUseOnlyGrantCommand(PROJECT_ID, RECIPIENT_ID, ACTION_ID, 7)
    assert service.for_set(setting) == service.for_set(replace(setting))
    assert service.for_remove(removal) == service.for_remove(replace(removal))
    assert (
        len(
            {
                service.for_set(setting),
                service.for_remove(removal),
                service.for_assign_use_only(legacy),
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
