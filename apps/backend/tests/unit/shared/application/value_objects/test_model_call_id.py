from uuid import UUID

import pytest

from inframeld_backend.shared.application.value_objects.model_call_id import ModelCallId


def test_preserves_original_call_identity() -> None:
    identity = UUID(int=7)

    assert ModelCallId(identity).value == identity


def test_rejects_a_string_in_place_of_a_call_uuid() -> None:
    with pytest.raises(TypeError):
        ModelCallId("not-a-uuid")  # pyright: ignore[reportArgumentType]
