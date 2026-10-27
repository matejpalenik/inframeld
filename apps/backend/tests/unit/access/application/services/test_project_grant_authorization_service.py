from dataclasses import replace
from typing import override
from uuid import UUID

import pytest
from tests.support.authentication_evidence import MockAuthenticationEvidence

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.human_oauth_credential_facts_dto import (
    HumanOAuthCredentialFactsDTO,
)
from inframeld_backend.access.application.dtos.project_grant_authorization_dto import (
    ProjectGrantAuthorizationDTO,
)
from inframeld_backend.access.application.dtos.project_grant_change_facts_dto import (
    ProjectGrantChangeFactsDTO,
)
from inframeld_backend.access.application.dtos.project_use_only_grant_authorization_request_dto import (
    ProjectUseOnlyGrantAuthorizationRequestDTO,
)
from inframeld_backend.access.application.protocols.project_grant_change_facts_reader import (
    ProjectGrantChangeFactsReader,
)
from inframeld_backend.access.application.services.project_grant_authorization_service import (
    ProjectGrantAuthorizationService,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ResourceNotFoundError,
)

ORGANIZATION_ID = OrganizationId(UUID(int=1))
PROJECT_ID = ProjectId(UUID(int=2))
ACTION_ID = ActionId("create-access-groups")

ACTOR = Principal(
    id=PrincipalId(UUID(int=3)),
    organization_id=ORGANIZATION_ID,
    kind=PrincipalKind.HUMAN,
    status=PrincipalStatus.ACTIVE,
)
RECIPIENT = Principal(
    id=PrincipalId(UUID(int=4)),
    organization_id=ORGANIZATION_ID,
    kind=PrincipalKind.HUMAN,
    status=PrincipalStatus.ACTIVE,
)
ACCESS = AccessContextDTO(
    actor_principal_id=ACTOR.id, authentication_evidence=MockAuthenticationEvidence.browser()
)


FACTS = ProjectGrantChangeFactsDTO(
    actor=ACTOR,
    has_pending_recovery=False,
    oauth_credential_facts=None,
    recipient=RECIPIENT,
    project_status=ProjectStatus.ACTIVE,
    project_access_revision=7,
    actor_is_project_member=True,
    recipient_is_project_member=True,
    actor_can_grant_action=True,
)


class MockProjectGrantChangeFactsReader(ProjectGrantChangeFactsReader):
    """Supply current facts and record the requested actor, target and action."""

    def __init__(self, facts: ProjectGrantChangeFactsDTO | None) -> None:
        self._facts = facts
        self.last_request: tuple[AccessContextDTO, ProjectId, PrincipalId, ActionId] | None = None

    @override
    async def read_for_change(
        self,
        *,
        access: AccessContextDTO,
        project_id: ProjectId,
        recipient_principal_id: PrincipalId,
        action_id: ActionId,
    ) -> ProjectGrantChangeFactsDTO | None:
        self.last_request = (
            access,
            project_id,
            recipient_principal_id,
            action_id,
        )
        return self._facts


@pytest.mark.asyncio
async def test_returns_current_scope_and_revision() -> None:
    """An eligible grantor receives the scope and revision read for this assignment."""
    reader = MockProjectGrantChangeFactsReader(FACTS)
    service = ProjectGrantAuthorizationService(reader)

    result = await service.require_authorization(
        access=ACCESS,
        request=ProjectUseOnlyGrantAuthorizationRequestDTO(
            project_id=PROJECT_ID, recipient_principal_id=RECIPIENT.id, action_id=ACTION_ID
        ),
    )

    assert result == ProjectGrantAuthorizationDTO(
        organization_id=ORGANIZATION_ID,
        project_id=PROJECT_ID,
        project_access_revision=7,
    )
    assert reader.last_request == (
        ACCESS,
        PROJECT_ID,
        RECIPIENT.id,
        ACTION_ID,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("facts", "expected_error"),
    [
        pytest.param(
            None,
            ResourceNotFoundError,
            id="missing-project",
        ),
        pytest.param(
            replace(
                FACTS,
                actor=replace(ACTOR, status=PrincipalStatus.SUSPENDED),
            ),
            ResourceNotFoundError,
            id="suspended-actor",
        ),
        pytest.param(
            replace(
                FACTS,
                actor=replace(ACTOR, status=PrincipalStatus.RETIRED),
            ),
            ResourceNotFoundError,
            id="retired-actor",
        ),
        pytest.param(
            replace(FACTS, project_status=ProjectStatus.DELETING),
            ResourceNotFoundError,
            id="unavailable-project",
        ),
        pytest.param(
            replace(FACTS, actor_is_project_member=False),
            ResourceNotFoundError,
            id="actor-is-not-member",
        ),
        pytest.param(
            replace(
                FACTS,
                actor_is_project_member=False,
                has_pending_recovery=True,
            ),
            ResourceNotFoundError,
            id="recovery-does-not-disclose-hidden-project",
        ),
        pytest.param(
            replace(FACTS, actor_can_grant_action=False),
            AccessDeniedError,
            id="use-only-authority",
        ),
        pytest.param(
            replace(
                FACTS,
                has_pending_recovery=True,
            ),
            AccessDeniedError,
            id="actor-has-pending-recovery",
        ),
        pytest.param(
            replace(
                FACTS,
                actor=replace(ACTOR, kind=PrincipalKind.APPLICATION),
            ),
            AccessDeniedError,
            id="application-cannot-delegate",
        ),
        pytest.param(
            replace(FACTS, recipient=None, recipient_is_project_member=False),
            ResourceNotFoundError,
            id="grantor-may-learn-recipient-is-missing",
        ),
        pytest.param(
            replace(
                FACTS,
                recipient=None,
                recipient_is_project_member=False,
                actor_can_grant_action=False,
            ),
            AccessDeniedError,
            id="nongrantor-cannot-learn-recipient-is-missing",
        ),
        pytest.param(
            replace(
                FACTS,
                recipient=None,
                recipient_is_project_member=False,
                has_pending_recovery=True,
            ),
            AccessDeniedError,
            id="recovery-denial-precedes-missing-recipient",
        ),
        pytest.param(
            replace(
                FACTS,
                recipient=replace(RECIPIENT, status=PrincipalStatus.SUSPENDED),
            ),
            AccessDeniedError,
            id="suspended-recipient",
        ),
        pytest.param(
            replace(
                FACTS,
                recipient=replace(RECIPIENT, status=PrincipalStatus.RETIRED),
            ),
            AccessDeniedError,
            id="retired-recipient",
        ),
        pytest.param(
            replace(
                FACTS,
                recipient=replace(RECIPIENT, kind=PrincipalKind.APPLICATION),
            ),
            AccessDeniedError,
            id="unsupported-recipient-kind",
        ),
        pytest.param(
            replace(
                FACTS,
                recipient=replace(
                    RECIPIENT,
                    organization_id=OrganizationId(UUID(int=5)),
                ),
            ),
            AccessDeniedError,
            id="recipient-from-another-organization",
        ),
        pytest.param(
            replace(FACTS, recipient_is_project_member=False),
            AccessDeniedError,
            id="recipient-is-not-member",
        ),
    ],
)
async def test_rejects_assignment_with_the_required_error(
    facts: ProjectGrantChangeFactsDTO | None,
    expected_error: type[Exception],
) -> None:
    """Preserve project privacy and check the grantor before recipient details."""
    service = ProjectGrantAuthorizationService(MockProjectGrantChangeFactsReader(facts))
    access = (
        replace(ACCESS, authentication_evidence=MockAuthenticationEvidence.application_key())
        if facts is not None and facts.actor.kind is PrincipalKind.APPLICATION
        else ACCESS
    )

    with pytest.raises(expected_error):
        await service.require_authorization(
            access=access,
            request=ProjectUseOnlyGrantAuthorizationRequestDTO(
                project_id=PROJECT_ID, recipient_principal_id=RECIPIENT.id, action_id=ACTION_ID
            ),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("visible", [False, True])
@pytest.mark.parametrize("binding_matches_actor, version", [(False, 1), (True, 2), (True, None)])
async def test_stale_credentials_are_rejected_before_authority_can_be_reused(
    visible: bool, binding_matches_actor: bool, version: int | None
) -> None:
    from inframeld_backend.access.application.errors.human_oauth_credential_rejected_error import (
        HumanOAuthCredentialRejectedError,
    )

    stale = replace(
        FACTS,
        actor_is_project_member=visible,
        oauth_credential_facts=HumanOAuthCredentialFactsDTO(
            binding_matches_actor=binding_matches_actor,
            current_version=HumanCredentialVersion(version) if version is not None else None,
        ),
    )
    with pytest.raises(HumanOAuthCredentialRejectedError):
        await ProjectGrantAuthorizationService(
            MockProjectGrantChangeFactsReader(stale)
        ).require_authorization(
            access=replace(
                ACCESS, authentication_evidence=MockAuthenticationEvidence.human_oauth()
            ),
            request=ProjectUseOnlyGrantAuthorizationRequestDTO(
                project_id=PROJECT_ID, recipient_principal_id=RECIPIENT.id, action_id=ACTION_ID
            ),
        )
