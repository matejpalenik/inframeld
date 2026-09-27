"""Keep UUID identifiers distinct without restricting existing stored UUIDs."""

from dataclasses import FrozenInstanceError
from typing import cast
from uuid import UUID, uuid4

import pytest

from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId


@pytest.mark.parametrize("identifier_type", [PrincipalId, OrganizationId, ProjectId, AccessGroupId])
def test_identifier_requires_a_parsed_uuid(
    identifier_type: type[PrincipalId]
    | type[OrganizationId]
    | type[ProjectId]
    | type[AccessGroupId],
) -> None:
    """Reject raw external input even when it bypasses static checking."""
    with pytest.raises(TypeError, match="UUID"):
        identifier_type(cast(UUID, "not-parsed"))


def test_identifiers_are_immutable_and_distinguish_entity_kinds() -> None:
    """Keep equal UUIDs for different entity kinds distinct in sets and comparisons."""
    value = uuid4()
    principal_id = PrincipalId(value)
    assert principal_id == PrincipalId(value)
    assert len({principal_id, ProjectId(value), OrganizationId(value)}) == 3
    with pytest.raises(FrozenInstanceError):
        principal_id.__setattr__("value", uuid4())


@pytest.mark.parametrize("value", [UUID(int=0), UUID("550e8400-e29b-11d4-a716-446655440000")])
def test_identifiers_preserve_existing_uuid_values(value: UUID) -> None:
    """Accept zero and non-v4 UUIDs without adding an unrequested identity restriction."""
    assert PrincipalId(value).value == value
    assert OrganizationId(value).value == value
    assert ProjectId(value).value == value
    assert AccessGroupId(value).value == value
