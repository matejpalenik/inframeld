from uuid import UUID

import pytest

from inframeld_backend.shared.application.value_objects.artifact_attempt_id import ArtifactAttemptId
from inframeld_backend.shared.application.value_objects.artifact_staging_reservation_id import (
    ArtifactStagingReservationId,
)


def test_server_identity_keeps_its_original_uuid() -> None:
    assert ArtifactStagingReservationId(UUID(int=1)).value == UUID(int=1)


@pytest.mark.parametrize(
    "value", [None, 1, "00000000-0000-0000-0000-000000000001", ArtifactAttemptId(UUID(int=1))]
)
def test_rejects_unparsed_or_other_kind_identity(value: object) -> None:
    with pytest.raises(TypeError):
        ArtifactStagingReservationId(value)  # type: ignore[arg-type]
