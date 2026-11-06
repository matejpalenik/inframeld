"""Keep removal distinct from an explicit use-only assignment."""

import pytest

from inframeld_backend.access.domain.value_objects.action_grant_state import ActionGrantState


@pytest.mark.parametrize("before", [None, False, True])
@pytest.mark.parametrize("level", [False, True])
def test_setting_preserves_the_requested_level_without_mutating_original_state(
    before: bool | None, level: bool
) -> None:
    original = ActionGrantState(can_grant=before)

    changed = original.set_level(can_grant=level)

    assert changed.can_grant is level
    assert original.can_grant is before
    assert (changed != original) is (before is not level)


@pytest.mark.parametrize("before", [None, False, True])
def test_removing_an_assignment_leaves_absence_without_changing_original_state(
    before: bool | None,
) -> None:
    original = ActionGrantState(can_grant=before)

    removed = original.remove()

    assert removed.can_grant is None
    assert original.can_grant is before
    assert (removed != original) is (before is not None)
