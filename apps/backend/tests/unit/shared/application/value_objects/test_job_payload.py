import pytest

from inframeld_backend.shared.application.value_objects.job_payload import JobPayload


def test_payload_preserves_original_bytes_without_disclosing_them() -> None:
    payload = JobPayload("test.progress", 1, b"private-fixed-input")

    assert payload.data == b"private-fixed-input"
    assert "private-fixed-input" not in repr(payload)


@pytest.mark.parametrize(
    "kind, version, data",
    [
        ("", 1, b"x"),
        ("../file", 1, b"x"),
        ("x", 0, b"x"),
        ("x", True, b"x"),
        ("x", 1, b"x" * 65537),
    ],
    ids=["empty-kind", "path-kind", "zero-version", "boolean-version", "oversized"],
)
def test_invalid_or_unbounded_payload_is_rejected(kind: str, version: int, data: bytes) -> None:
    with pytest.raises((TypeError, ValueError)):
        JobPayload(kind, version, data)
