import pytest

from inframeld_backend.shared.domain.value_objects.submitted_display_name import (
    SubmittedDisplayName,
)


@pytest.mark.parametrize(
    "value", ["", " ", " label", "label ", "a\nlabel", "a\x00label", "a\u2028label", "a" * 129]
)
def test_replacement_rejects_invalid_label_without_rewriting(value: str) -> None:
    with pytest.raises(ValueError):
        SubmittedDisplayName(value)


def test_codepoint_limit_preserves_non_bmp_and_combining_spelling() -> None:
    value = "😀" * 126 + "e\u0301"
    assert SubmittedDisplayName(value).value == value
