import asyncio
from dataclasses import replace
from typing import override

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.access_group_metadata_dto import (
    AccessGroupMetadataDTO,
)
from inframeld_backend.access.application.dtos.access_group_principals_page_dto import (
    AccessGroupPrincipalsPageDTO,
)
from inframeld_backend.access.application.dtos.access_group_read_facts_dto import (
    AccessGroupReadFactsDTO,
)
from inframeld_backend.access.application.protocols.access_group_read_facts_reader import (
    AccessGroupReadFactsReader,
)
from inframeld_backend.access.application.protocols.access_group_reader import AccessGroupReader
from inframeld_backend.access.application.queries.list_access_group_principals_query import (
    ListAccessGroupPrincipalsQuery,
)
from inframeld_backend.access.application.services.action_authorization_service import (
    ActionAuthorizationService,
)
from inframeld_backend.access.application.value_objects.access_group_principals_cursor import (
    AccessGroupPrincipalsCursor,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    DependencyUnavailableError,
    InvalidInputError,
    ResourceNotFoundError,
)
from inframeld_backend.shared.application.protocols.transaction_manager import TransactionManager
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName


class AccessGroupReadService(AccessGroupReader):
    def __init__(
        self, transaction_manager: TransactionManager, facts_reader: AccessGroupReadFactsReader
    ) -> None:
        self._transaction_manager = transaction_manager
        self._facts_reader = facts_reader

    @override
    async def inspect(
        self,
        *,
        access: AccessContextDTO,
        project_id: ProjectId,
        selector: AccessGroupId | ResourceName,
    ) -> AccessGroupMetadataDTO:
        try:
            async with asyncio.timeout(5), self._transaction_manager.begin():
                facts = await self._facts_reader.read(
                    access=access, project_id=project_id, selector=selector
                )
                self._require_visible(access, project_id, selector, facts)
                assert facts is not None
                return facts.group
        except TimeoutError:
            raise DependencyUnavailableError() from None

    @override
    async def list_principals(
        self, *, access: AccessContextDTO, query: ListAccessGroupPrincipalsQuery
    ) -> AccessGroupPrincipalsPageDTO:
        try:
            async with asyncio.timeout(5), self._transaction_manager.begin():
                facts = await self._facts_reader.read(
                    access=access, project_id=query.project_id, selector=query.group_id
                )
                self._require_visible(access, query.project_id, query.group_id, facts)
                assert facts is not None
                if not facts.is_manager or facts.action.principal.kind is not PrincipalKind.HUMAN:
                    raise AccessDeniedError()
                cursor = None
                if query.cursor is not None:
                    try:
                        cursor = AccessGroupPrincipalsCursor.from_token(query.cursor)
                    except ValueError:
                        raise InvalidInputError() from None
                    if (
                        cursor.installation_id,
                        cursor.organization_id,
                        cursor.project_id,
                        cursor.group_id,
                        cursor.collection,
                    ) != (
                        facts.installation_id,
                        facts.group.organization_id,
                        query.project_id,
                        query.group_id,
                        query.collection,
                    ):
                        raise InvalidInputError(
                            "The cursor belongs to another group or collection."
                        )
                rows = await self._facts_reader.principals(
                    facts=facts,
                    collection=query.collection,
                    after=cursor.after if cursor is not None else None,
                    limit=query.limit,
                )
                items = rows[: query.limit]
                next_cursor = (
                    AccessGroupPrincipalsCursor(
                        facts.installation_id,
                        facts.group.organization_id,
                        query.project_id,
                        query.group_id,
                        query.collection,
                        items[-1].principal_id,
                    ).to_token()
                    if len(rows) > query.limit
                    else None
                )
                return AccessGroupPrincipalsPageDTO(
                    query.project_id,
                    query.group_id,
                    facts.group.access_revision,
                    items,
                    next_cursor,
                )
        except TimeoutError:
            raise DependencyUnavailableError() from None

    @staticmethod
    def _require_visible(
        access: AccessContextDTO,
        project_id: ProjectId,
        selector: AccessGroupId | ResourceName,
        facts: AccessGroupReadFactsDTO | None,
    ) -> None:
        if facts is None:
            raise ResourceNotFoundError()
        group = facts.group
        if (
            group.project_id != project_id
            or facts.action.principal.id != access.actor_principal_id
            or facts.action.principal.organization_id != group.organization_id
            or (isinstance(selector, AccessGroupId) and group.group_id != selector)
            or (isinstance(selector, ResourceName) and group.name != selector)
        ):
            raise RuntimeError("Group metadata changed the requested actor or scope.")
        ActionAuthorizationService.require_authorization_from_facts(
            access=access, facts=replace(facts.action, has_exact_action_grant=True)
        )
        if not (facts.is_member or facts.is_manager or facts.has_group_action):
            raise ResourceNotFoundError()
