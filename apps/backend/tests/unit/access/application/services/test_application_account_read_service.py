"""Protect account visibility and each fresh bounded key-metadata disclosure."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import override
from uuid import UUID

import pytest
from tests.support.mock_project_metadata import ACCESS, ORGANIZATION_ID, PROJECT_ID

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.application_account_metadata_dto import (
    ApplicationAccountMetadataDTO,
)
from inframeld_backend.access.application.dtos.application_account_read_facts_dto import (
    ApplicationAccountReadFactsDTO,
)
from inframeld_backend.access.application.dtos.application_key_metadata_dto import (
    ApplicationKeyMetadataDTO,
)
from inframeld_backend.access.application.dtos.application_keys_facts_dto import (
    ApplicationKeysFactsDTO,
)
from inframeld_backend.access.application.dtos.project_action_facts_dto import ProjectActionFactsDTO
from inframeld_backend.access.application.protocols.application_account_facts_reader import (
    ApplicationAccountFactsReader,
)
from inframeld_backend.access.application.queries.list_application_keys_query import (
    ListApplicationKeysQuery,
)
from inframeld_backend.access.application.services.application_account_read_service import (
    ApplicationAccountReadService,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.application_key_adapter import ApplicationKeyAdapter
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.value_objects.application_key_id import ApplicationKeyId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    InvalidInputError,
    ResourceNotFoundError,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName

APP = PrincipalId(UUID(int=8))
NOW = datetime(2030, 1, 1, tzinfo=UTC)
ACCOUNT = ApplicationAccountMetadataDTO(
    ORGANIZATION_ID,
    PROJECT_ID,
    APP,
    ResourceName("support-bot"),
    "SupportBot",
    PrincipalStatus.ACTIVE,
    NOW,
    8,
)
FACTS = ApplicationAccountReadFactsDTO(
    InstallationId(UUID(int=9)),
    ProjectActionFactsDTO(
        Principal(
            ACCESS.actor_principal_id, ORGANIZATION_ID, PrincipalKind.HUMAN, PrincipalStatus.ACTIVE
        ),
        False,
        None,
        ProjectStatus.ACTIVE,
        True,
        True,
    ),
    ACCOUNT,
    True,
)
KEYS = tuple(
    ApplicationKeyMetadataDTO(
        ApplicationKeyId(UUID(int=n)),
        APP,
        PROJECT_ID,
        (ApplicationKeyAdapter.HTTP,),
        NOW,
        NOW + timedelta(days=90),
        None,
    )
    for n in (10, 11, 12)
)


class MockAccountFacts(ApplicationAccountFactsReader):
    def __init__(self) -> None:
        self.facts: ApplicationAccountReadFactsDTO | None = FACTS
        self.keys = KEYS
        self.calls = 0
        self.filter_position = True

    @override
    async def read_account(
        self,
        *,
        access: AccessContextDTO,
        project_id: ProjectId,
        selector: PrincipalId | ResourceName,
    ) -> ApplicationAccountReadFactsDTO | None:
        self.calls += 1
        return self.facts

    @override
    async def read_keys(
        self,
        *,
        access: AccessContextDTO,
        project_id: ProjectId,
        application_principal_id: PrincipalId,
        key_id: ApplicationKeyId | None,
        after: ApplicationKeyId | None,
        limit: int,
    ) -> ApplicationKeysFactsDTO | None:
        self.calls += 1
        keys = self.keys
        if key_id is not None:
            keys = tuple(key for key in keys if key.key_id == key_id)
        if after is not None and self.filter_position:
            keys = tuple(key for key in keys if key.key_id.value.int > after.value.int)
        return (
            ApplicationKeysFactsDTO(self.facts, keys[: limit + 1])
            if self.facts is not None
            else None
        )


@pytest.fixture
def reader() -> tuple[ApplicationAccountReadService, MockAccountFacts]:
    facts = MockAccountFacts()
    return ApplicationAccountReadService(facts), facts


@pytest.mark.asyncio
async def test_id_and_exact_name_read_same_safe_metadata(
    reader: tuple[ApplicationAccountReadService, MockAccountFacts],
) -> None:
    service, facts = reader
    assert (
        await service.get_account(access=ACCESS, project_id=PROJECT_ID, principal_id=APP) == ACCOUNT
    )
    assert (
        await service.resolve_account(
            access=ACCESS, project_id=PROJECT_ID, name=ResourceName("support-bot")
        )
        == ACCOUNT
    )
    assert facts.calls == 2


@pytest.mark.asyncio
async def test_delete_alone_can_read_account_but_cannot_read_key_metadata(
    reader: tuple[ApplicationAccountReadService, MockAccountFacts],
) -> None:
    service, facts = reader
    facts.facts = replace(FACTS, can_read_keys=False)
    assert (
        await service.get_account(access=ACCESS, project_id=PROJECT_ID, principal_id=APP) == ACCOUNT
    )
    with pytest.raises(AccessDeniedError):
        await service.list_keys(access=ACCESS, query=ListApplicationKeysQuery(PROJECT_ID, APP))
    with pytest.raises(AccessDeniedError):
        await service.get_key(
            access=ACCESS,
            project_id=PROJECT_ID,
            application_principal_id=APP,
            key_id=KEYS[0].key_id,
        )


@pytest.mark.asyncio
async def test_keys_page_has_stable_uuid_continuation_and_current_authority(
    reader: tuple[ApplicationAccountReadService, MockAccountFacts],
) -> None:
    service, facts = reader
    first = await service.list_keys(
        access=ACCESS, query=ListApplicationKeysQuery(PROJECT_ID, APP, 2)
    )
    assert first.items == KEYS[:2] and first.next_cursor is not None
    second = await service.list_keys(
        access=ACCESS, query=ListApplicationKeysQuery(PROJECT_ID, APP, 2, first.next_cursor)
    )
    assert second.items == KEYS[2:] and second.next_cursor is None
    facts.facts = replace(FACTS, can_read_keys=False)
    with pytest.raises(AccessDeniedError):
        await service.list_keys(
            access=ACCESS, query=ListApplicationKeysQuery(PROJECT_ID, APP, 2, first.next_cursor)
        )
    assert facts.calls == 3


@pytest.mark.asyncio
async def test_get_key_selects_exact_id_and_missing_stays_not_found(
    reader: tuple[ApplicationAccountReadService, MockAccountFacts],
) -> None:
    service, _ = reader
    assert (
        await service.get_key(
            access=ACCESS,
            project_id=PROJECT_ID,
            application_principal_id=APP,
            key_id=KEYS[1].key_id,
        )
        == KEYS[1]
    )
    with pytest.raises(ResourceNotFoundError):
        await service.get_key(
            access=ACCESS,
            project_id=PROJECT_ID,
            application_principal_id=APP,
            key_id=ApplicationKeyId(UUID(int=90)),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["hidden", "membership", "recovery", "suspended"])
async def test_current_denial_never_returns_account_or_keys(
    reader: tuple[ApplicationAccountReadService, MockAccountFacts], change: str
) -> None:
    service, facts = reader
    action = FACTS.action
    if change == "hidden":
        action = replace(action, has_exact_action_grant=False)
    elif change == "membership":
        action = replace(action, is_project_member=False)
    elif change == "recovery":
        action = replace(action, has_pending_recovery=True)
    else:
        action = replace(
            action, principal=replace(action.principal, status=PrincipalStatus.SUSPENDED)
        )
    facts.facts = replace(FACTS, action=action)
    with pytest.raises((AccessDeniedError, ResourceNotFoundError)):
        await service.get_account(access=ACCESS, project_id=PROJECT_ID, principal_id=APP)
    with pytest.raises((AccessDeniedError, ResourceNotFoundError)):
        await service.list_keys(access=ACCESS, query=ListApplicationKeysQuery(PROJECT_ID, APP))


@pytest.mark.asyncio
async def test_cross_account_cursor_cannot_authorize_or_retarget_keys(
    reader: tuple[ApplicationAccountReadService, MockAccountFacts],
) -> None:
    service, facts = reader
    first = await service.list_keys(
        access=ACCESS, query=ListApplicationKeysQuery(PROJECT_ID, APP, 2)
    )
    other = PrincipalId(UUID(int=70))
    facts.facts = replace(FACTS, account=replace(ACCOUNT, principal_id=other))
    facts.keys = ()
    with pytest.raises(InvalidInputError):
        await service.list_keys(
            access=ACCESS, query=ListApplicationKeysQuery(PROJECT_ID, other, 2, first.next_cursor)
        )


@pytest.mark.asyncio
async def test_wrong_returned_account_and_key_scope_fail_closed(
    reader: tuple[ApplicationAccountReadService, MockAccountFacts],
) -> None:
    service, facts = reader
    with pytest.raises(RuntimeError):
        await service.get_account(
            access=ACCESS, project_id=ProjectId(UUID(int=99)), principal_id=APP
        )
    with pytest.raises(RuntimeError):
        await service.resolve_account(
            access=ACCESS, project_id=PROJECT_ID, name=ResourceName("wrong-name")
        )
    facts.keys = (replace(KEYS[0], application_principal_id=PrincipalId(UUID(int=77))),)
    with pytest.raises(RuntimeError):
        await service.list_keys(access=ACCESS, query=ListApplicationKeysQuery(PROJECT_ID, APP))
