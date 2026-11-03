from pathlib import Path

import pytest
from pydantic import ValidationError

from inframeld_backend.shared.infrastructure.settings.artifact_storage_settings import (
    ArtifactStorageSettings,
)


def settings(tmp_path: Path, **changes: object) -> ArtifactStorageSettings:
    data: dict[str, object] = {
        "endpoint_url": "https://storage.test",
        "bucket": "private-artifacts",
        "access_key_id": "private-key",
        "secret_access_key": "private-secret",
    }
    data.update(changes)
    return ArtifactStorageSettings.model_validate(data)


def test_credentials_are_not_disclosed_in_configuration_repr(tmp_path: Path) -> None:
    configured = settings(tmp_path)
    assert "private-key" not in repr(configured)
    assert "private-secret" not in repr(configured)


@pytest.mark.parametrize(
    "changes",
    [
        {"endpoint_url": "https://user:private-secret@storage.test"},
        {"endpoint_url": "file:///tmp/objects"},
        {"endpoint_url": "https://storage.test/?token=private-secret"},
        {"bucket": "../public"},
        {"region": ""},
        {"connect_timeout_seconds": 0},
        {"read_timeout_seconds": float("inf")},
        {"operation_timeout_seconds": float("nan")},
        {"operation_timeout_seconds": 31},
        {"max_object_bytes": 256 * 1024 * 1024 + 1},
        {"max_object_bytes": 0},
        {"list_page_size": 1001},
    ],
)
def test_rejects_unsafe_or_unbounded_configuration(
    tmp_path: Path, changes: dict[str, object]
) -> None:
    with pytest.raises(ValidationError) as failure:
        settings(tmp_path, **changes)
    assert "private-secret" not in str(failure.value)
