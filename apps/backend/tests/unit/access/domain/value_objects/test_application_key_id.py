from typing import cast
from uuid import UUID

import pytest

from inframeld_backend.access.domain.value_objects.application_key_id import ApplicationKeyId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId


@pytest.mark.parametrize("invalid", ["not-parsed", None, PrincipalId(UUID(int=1))])
def test_application_key_id_requires_a_parsed_uuid(invalid: object) -> None:
    """A key lookup ID cannot accidentally contain text or a principal ID."""
    with pytest.raises(TypeError, match="UUID"):
        ApplicationKeyId(cast(UUID, invalid))


@pytest.mark.parametrize("value", [UUID(int=0), UUID("550e8400-e29b-11d4-a716-446655440000")])
def test_application_key_id_preserves_uuid_meaning(value: UUID) -> None:
    assert ApplicationKeyId(value).value == value
    assert ApplicationKeyId(value) == ApplicationKeyId(value)
    assert len({ApplicationKeyId(value), PrincipalId(value)}) == 2
