from dataclasses import replace
from typing import override
from uuid import UUID

import pytest
from tests.support.mock_project_metadata import (
    ACCESS,
    PROJECT_ID,
    MockTransactions,
)
from tests.unit.access.application.services.test_model_connection_creation_service import (
    COMMAND,
    FACTS,
)

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.model_connection_dto import ModelConnectionDTO
from inframeld_backend.access.application.dtos.project_action_facts_dto import ProjectActionFactsDTO
from inframeld_backend.access.application.protocols.model_connection_read_repository import (
    ModelConnectionReadRepository,
)
from inframeld_backend.access.application.services.model_connection_read_service import (
    ModelConnectionReadService,
)
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.errors.application_errors import (
    InvalidInputError,
    ResourceNotFoundError,
)
from inframeld_backend.shared.application.value_objects.model_connection_id import ModelConnectionId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId

FIRST = ModelConnectionDTO(
    PROJECT_ID,
    ModelConnectionId(UUID(int=1)),
    COMMAND.name,
    COMMAND.display_name.value,
    COMMAND.access,
    0,
    False,
    0,
)
SECOND = replace(FIRST, connection_id=ModelConnectionId(UUID(int=2)))
INSTALLED = InstallationId(UUID(int=3))


class MockReadRepository(ModelConnectionReadRepository):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.facts = replace(FACTS.action, has_exact_action_grant=False)
        self.items: tuple[ModelConnectionDTO, ...] = (FIRST, SECOND)

    @override
    async def lock_scope(
        self, access: AccessContextDTO, project_id: ProjectId
    ) -> tuple[InstallationId, ProjectActionFactsDTO]:
        self.events.append("current eligibility")
        return INSTALLED, self.facts

    @override
    async def get_visible(
        self, facts: ProjectActionFactsDTO, project_id: ProjectId, connection_id: ModelConnectionId
    ) -> ModelConnectionDTO | None:
        self.events.append("exact connection grant")
        return next((item for item in self.items if item.connection_id == connection_id), None)

    @override
    async def list_visible(
        self,
        facts: ProjectActionFactsDTO,
        project_id: ProjectId,
        after: ModelConnectionId | None,
        limit: int,
    ) -> tuple[ModelConnectionDTO, ...]:
        self.events.append("list exact connection grants")
        return tuple(
            item for item in self.items if after is None or item.connection_id.value > after.value
        )[:limit]


@pytest.mark.asyncio
async def test_page_reauthorizes_and_rejects_a_cursor_from_another_project() -> None:
    events: list[str] = []
    repository = MockReadRepository(events)
    reader = ModelConnectionReadService(MockTransactions(events), repository)
    first = await reader.list_connections(ACCESS, PROJECT_ID, 1, None)
    assert first.items == (FIRST,)
    assert first.next_cursor is not None
    second = await reader.list_connections(ACCESS, PROJECT_ID, 1, first.next_cursor)
    assert second.items == (SECOND,)
    assert second.next_cursor is None
    with pytest.raises(InvalidInputError):
        await reader.list_connections(ACCESS, ProjectId(UUID(int=99)), 1, first.next_cursor)
    assert events.count("current eligibility") >= 2


@pytest.mark.asyncio
async def test_usage_requires_the_exact_connection_grant_and_refuses_connection_list_cursor() -> (
    None
):
    events: list[str] = []
    repository = MockReadRepository(events)
    reader = ModelConnectionReadService(MockTransactions(events), repository)
    await reader.list_usage(ACCESS, PROJECT_ID, FIRST.connection_id, 25, None)
    assert events == ["begin", "current eligibility", "exact connection grant", "commit"]
    page = await reader.list_connections(ACCESS, PROJECT_ID, 1, None)
    with pytest.raises(InvalidInputError):
        await reader.list_usage(ACCESS, PROJECT_ID, FIRST.connection_id, 25, page.next_cursor)

    repository.items = (SECOND,)
    with pytest.raises(ResourceNotFoundError):
        await reader.list_usage(ACCESS, PROJECT_ID, FIRST.connection_id, 25, None)
    repository.facts = replace(repository.facts, is_project_member=False)
    with pytest.raises(ResourceNotFoundError):
        await reader.get(ACCESS, PROJECT_ID, SECOND.connection_id)
    assert events[-3:] == ["begin", "current eligibility", "rollback"]
