from abc import abstractmethod
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from inframeld_backend.access.domain.authorization import (
    ActionAuthorizationFacts,
    may_perform_action,
)
from inframeld_backend.shared.application.errors import AccessDeniedError, ResourceNotFoundError


@dataclass(frozen=True, slots=True)
class AccessContext:
    actor_principal_id: UUID


@dataclass(frozen=True, slots=True)
class ActionTarget:
    project_id: UUID
    target_kind: str
    target_id: UUID


@dataclass(frozen=True, slots=True)
class CurrentActionFacts:
    authorization: ActionAuthorizationFacts
    target_is_visible: bool


class ActionFactsReader(Protocol):
    @abstractmethod
    async def read_action_facts(
        self, *, access: AccessContext, action: str, target: ActionTarget
    ) -> CurrentActionFacts: ...


class AccessAuthorizer:
    def __init__(self, facts_reader: ActionFactsReader) -> None:
        self._facts_reader = facts_reader

    async def require_action(
        self, *, access: AccessContext, action: str, target: ActionTarget
    ) -> None:
        """Require a visible target and current authority for the requested action."""
        facts = await self._facts_reader.read_action_facts(
            access=access, action=action, target=target
        )

        if not facts.target_is_visible:
            raise ResourceNotFoundError()

        if not may_perform_action(facts.authorization):
            raise AccessDeniedError()
