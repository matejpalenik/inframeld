from typing import cast
from uuid import UUID

import pytest

from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
from inframeld_backend.access.domain.value_objects.upload_audience import UploadAudience

A = AccessGroupId(UUID(int=1))
B = AccessGroupId(UUID(int=2))


def test_audience_is_a_canonical_set() -> None:
    assert UploadAudience((B, A)).group_ids == (A, B)
    assert UploadAudience((B, A)) == UploadAudience((A, B))


@pytest.mark.parametrize("groups", [(), (A, A)])
def test_empty_and_duplicate_groups_reject(groups: tuple[AccessGroupId, ...]) -> None:
    with pytest.raises(ValueError):
        UploadAudience(groups)


def test_audience_rejects_an_untyped_group() -> None:
    with pytest.raises(TypeError):
        UploadAudience((cast(AccessGroupId, UUID(int=1)),))
