from dataclasses import replace
from typing import override
from uuid import uuid4

import pytest

from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.dtos.resource_name_binding_dto import (
    ResourceNameBindingDTO,
)
from inframeld_backend.shared.application.dtos.resource_name_scope_dto import ResourceNameScopeDTO
from inframeld_backend.shared.application.enums.resource_name_kind import ResourceNameKind
from inframeld_backend.shared.application.errors.application_errors import ResourceNotFoundError
from inframeld_backend.shared.application.protocols.resource_name_binding_reader import (
    ResourceNameBindingReader,
)
from inframeld_backend.shared.application.queries.resolve_resource_name_query import (
    ResolveResourceNameQuery,
)
from inframeld_backend.shared.application.services.resource_name_resolution_service import (
    ResourceNameResolutionService,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName


class MockBindings(ResourceNameBindingReader):
    def __init__(
        self, bindings: tuple[ResourceNameBindingDTO, ...], *, obey_kind: bool = True
    ) -> None:
        self.bindings = bindings
        self.obey_kind = obey_kind

    @override
    async def read(self, query: ResolveResourceNameQuery) -> tuple[ResourceNameBindingDTO, ...]:
        return tuple(b for b in self.bindings if not self.obey_kind or b.kind is query.kind)


def binding() -> ResourceNameBindingDTO:
    scope = ResourceNameScopeDTO(
        InstallationId(uuid4()), OrganizationId(uuid4()), ProjectId(uuid4())
    )
    return ResourceNameBindingDTO(
        kind=ResourceNameKind.PROCESSING_PROFILE,
        resource_id=uuid4(),
        scope=scope,
        name=ResourceName("support"),
        revision=1,
        retired=False,
    )


@pytest.mark.asyncio
async def test_same_spelling_collection_cannot_replace_profile_binding() -> None:
    profile = binding()
    collection = replace(profile, kind=ResourceNameKind.COLLECTION, resource_id=uuid4())
    service = ResourceNameResolutionService(MockBindings((collection, profile)))
    assert (
        await service.resolve(ResolveResourceNameQuery(profile.scope, profile.kind, profile.name))
        == profile
    )
    with pytest.raises(ResourceNotFoundError):
        await ResourceNameResolutionService(MockBindings((collection,))).resolve(
            ResolveResourceNameQuery(profile.scope, profile.kind, profile.name)
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mismatch", ["kind", "project", "organization", "installation", "name", "ambiguous"]
)
async def test_rejects_bad_adapter_scope_or_ambiguity(mismatch: str) -> None:
    wanted = binding()
    bad = wanted
    if mismatch == "kind":
        bad = replace(wanted, kind=ResourceNameKind.COLLECTION)
    elif mismatch == "project":
        bad = replace(wanted, scope=replace(wanted.scope, project_id=ProjectId(uuid4())))
    elif mismatch == "organization":
        bad = replace(wanted, scope=replace(wanted.scope, organization_id=OrganizationId(uuid4())))
    elif mismatch == "installation":
        bad = replace(wanted, scope=replace(wanted.scope, installation_id=InstallationId(uuid4())))
    elif mismatch == "name":
        bad = replace(wanted, name=ResourceName("other"))
    rows = (bad, bad) if mismatch == "ambiguous" else (bad,)
    with pytest.raises(ResourceNotFoundError):
        await ResourceNameResolutionService(MockBindings(rows, obey_kind=False)).resolve(
            ResolveResourceNameQuery(wanted.scope, wanted.kind, wanted.name)
        )
