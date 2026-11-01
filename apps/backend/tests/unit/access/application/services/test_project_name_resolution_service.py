from dataclasses import replace

import pytest
from tests.support.mock_project_metadata import (
    ACCESS,
    PROJECT_ID,
    SCOPE,
    MockMetadataAuthorizer,
    MockMetadataRepository,
    MockMetadataScope,
    MockResourceBindings,
    MockTransactions,
)

from inframeld_backend.access.application.queries.resolve_project_name_query import (
    ResolveProjectNameQuery,
)
from inframeld_backend.access.application.services.project_name_resolution_service import (
    ProjectNameResolutionService,
)
from inframeld_backend.shared.application.dtos.resource_name_binding_dto import (
    ResourceNameBindingDTO,
)
from inframeld_backend.shared.application.enums.resource_name_kind import ResourceNameKind
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ResourceNotFoundError,
)
from inframeld_backend.shared.application.services.resource_name_resolution_service import (
    ResourceNameResolutionService,
)
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName


@pytest.mark.asyncio
async def test_real_project_service_consumes_checked_typed_binding_then_current_visibility() -> (
    None
):
    events: list[str] = []
    repository = MockMetadataRepository(events)
    repository.metadata.change(expected_revision=0, name=ResourceName("support"), display_name=None)
    authorizer = MockMetadataAuthorizer(events)
    binding = ResourceNameBindingDTO(
        ResourceNameKind.PROJECT, PROJECT_ID.value, SCOPE, ResourceName("support"), 1, False
    )
    bindings = MockResourceBindings((binding,))
    service = ProjectNameResolutionService(
        transactions=MockTransactions(events),
        facts=MockMetadataScope(),
        resolver=ResourceNameResolutionService(bindings),
        authorizer=authorizer,
        repository=repository,
    )
    result = await service.resolve(
        access=ACCESS, query=ResolveProjectNameQuery(ResourceName("support"))
    )
    assert result.project_id == PROJECT_ID
    assert events == ["begin", "authorize", "load", "commit"]
    events.clear()
    authorizer.error = AccessDeniedError()
    with pytest.raises(AccessDeniedError):
        await service.resolve(access=ACCESS, query=ResolveProjectNameQuery(ResourceName("support")))
    assert "load" not in events
    authorizer.error = None
    bindings.bindings = (replace(binding, retired=True),)
    with pytest.raises(ResourceNotFoundError):
        await service.resolve(access=ACCESS, query=ResolveProjectNameQuery(ResourceName("support")))


@pytest.mark.asyncio
async def test_retired_name_guidance_uses_latest_selector_only_after_current_authorization() -> (
    None
):
    from inframeld_backend.access.application.errors.retired_project_name_error import (
        RetiredProjectNameError,
    )

    events: list[str] = []
    repository = MockMetadataRepository(events)
    for revision, name in enumerate(["support", "legal", "research"]):
        repository.metadata.change(
            expected_revision=revision, name=ResourceName(name), display_name=None
        )
    authorizer = MockMetadataAuthorizer(events)
    binding = ResourceNameBindingDTO(
        ResourceNameKind.PROJECT,
        PROJECT_ID.value,
        SCOPE,
        ResourceName("support"),
        1,
        True,
    )
    service = ProjectNameResolutionService(
        transactions=MockTransactions(events),
        facts=MockMetadataScope(),
        resolver=ResourceNameResolutionService(MockResourceBindings((binding,))),
        authorizer=authorizer,
        repository=repository,
    )
    with pytest.raises(RetiredProjectNameError) as failure:
        await service.resolve(access=ACCESS, query=ResolveProjectNameQuery(ResourceName("support")))
    assert failure.value.project_id == PROJECT_ID
    assert failure.value.current_name == ResourceName("research")
    assert events == ["begin", "authorize", "load", "rollback"]
    events.clear()
    authorizer.error = AccessDeniedError()
    with pytest.raises(AccessDeniedError):
        await service.resolve(access=ACCESS, query=ResolveProjectNameQuery(ResourceName("support")))
    assert "load" not in events
