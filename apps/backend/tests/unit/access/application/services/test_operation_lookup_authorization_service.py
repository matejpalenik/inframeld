"""Require original exact authority using only current Access observations."""

from dataclasses import replace
from typing import override
from uuid import UUID

import pytest
from tests.support.authentication_evidence import MockAuthenticationEvidence

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.human_credential_facts_dto import (
    HumanCredentialFactsDTO,
)
from inframeld_backend.access.application.dtos.operation_lookup_facts_dto import (
    OperationLookupFactsDTO,
)
from inframeld_backend.access.application.errors.human_oauth_credential_rejected_error import (
    HumanOAuthCredentialRejectedError,
)
from inframeld_backend.access.application.protocols.operation_lookup_facts_reader import (
    OperationLookupFactsReader,
)
from inframeld_backend.access.application.services.operation_lookup_authorization_service import (
    OperationLookupAuthorizationService,
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
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.enums.operation_lookup_authority_family import (
    OperationLookupAuthorityFamily,
)
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    AuthenticationRequiredError,
    DependencyUnavailableError,
    ResourceNotFoundError,
)
from inframeld_backend.shared.application.queries.lookup_original_operation_query import (
    LookupOriginalOperationQuery,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.operation_lookup_authority import (
    OperationLookupAuthority,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId

ACTOR = Principal(
    PrincipalId(UUID(int=1)),
    OrganizationId(UUID(int=2)),
    PrincipalKind.HUMAN,
    PrincipalStatus.ACTIVE,
)
ACCESS = AccessContextDTO(ACTOR.id, MockAuthenticationEvidence.browser())
QUERY = LookupOriginalOperationQuery(
    InstallationId(UUID(int=3)),
    ACTOR.organization_id,
    ProjectId(UUID(int=4)),
    HttpMethod.POST,
    "/v1/projects/{project_id}/grants",
    IdempotencyKey("lost"),
    OperationLookupAuthority(
        OperationLookupAuthorityFamily.PROJECT_GRANT_READ, ActionId("create-access-groups")
    ),
)
FACTS = OperationLookupFactsDTO(
    installation_id=QUERY.installation_id,
    principal=ACTOR,
    project_status=ProjectStatus.ACTIVE,
    is_project_member=True,
    has_exact_action_grant=True,
    can_grant_action=True,
    has_pending_recovery=False,
    oauth_credential_facts=HumanCredentialFactsDTO(True, HumanCredentialVersion(1)),
)


class MockLookupFacts(OperationLookupFactsReader):
    def __init__(self, result: OperationLookupFactsDTO | None = FACTS) -> None:
        self.result = result
        self.failure: Exception | None = None

    @override
    async def read(
        self, *, access: AccessContextDTO, query: LookupOriginalOperationQuery
    ) -> OperationLookupFactsDTO | None:
        if self.failure is not None:
            raise self.failure
        return self.result


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "facts,error",
    [
        (None, ResourceNotFoundError),
        (replace(FACTS, can_grant_action=False), AccessDeniedError),
        (replace(FACTS, has_pending_recovery=True), AccessDeniedError),
        (replace(FACTS, is_project_member=False), ResourceNotFoundError),
        (replace(FACTS, project_status=ProjectStatus.DELETING), ResourceNotFoundError),
        (replace(FACTS, installation_id=InstallationId(UUID(int=99))), ResourceNotFoundError),
        (
            replace(FACTS, principal=replace(ACTOR, organization_id=OrganizationId(UUID(int=99)))),
            ResourceNotFoundError,
        ),
    ],
)
async def test_current_grant_read_rejections(
    facts: OperationLookupFactsDTO | None, error: type[Exception]
) -> None:
    with pytest.raises(error):
        await OperationLookupAuthorizationService(MockLookupFacts(facts)).require_authorization(
            access=ACCESS, request=QUERY
        )


@pytest.mark.asyncio
async def test_grant_read_does_not_need_a_recipient_or_expected_revision() -> None:
    result = await OperationLookupAuthorizationService(MockLookupFacts()).require_authorization(
        access=ACCESS, request=QUERY
    )
    assert result.organization_id == QUERY.organization_id
    assert result.project_id == QUERY.project_id


@pytest.mark.asyncio
async def test_generic_project_action_uses_its_exact_use_grant() -> None:
    query = replace(
        QUERY,
        requested_route="/v1/original-project-operation",
        expected_authority=OperationLookupAuthority(
            OperationLookupAuthorityFamily.PROJECT_ACTION_USE, ActionId("create-access-groups")
        ),
    )
    service = OperationLookupAuthorizationService(
        MockLookupFacts(replace(FACTS, can_grant_action=False))
    )
    assert (
        await service.require_authorization(access=ACCESS, request=query)
    ).project_id == query.project_id
    with pytest.raises(AccessDeniedError):
        await OperationLookupAuthorizationService(
            MockLookupFacts(replace(FACTS, has_exact_action_grant=False))
        ).require_authorization(access=ACCESS, request=query)


@pytest.mark.asyncio
async def test_organization_lookup_needs_exact_organization_action_without_project_membership() -> (
    None
):
    query = replace(
        QUERY,
        project_id=None,
        requested_route="/v1/original-organization-operation",
        expected_authority=OperationLookupAuthority(
            OperationLookupAuthorityFamily.ORGANIZATION_ACTION_USE, ActionId("create-projects")
        ),
    )
    facts = replace(FACTS, project_status=None, is_project_member=False, can_grant_action=False)
    result = await OperationLookupAuthorizationService(
        MockLookupFacts(facts)
    ).require_authorization(access=ACCESS, request=query)
    assert result.project_id is None
    with pytest.raises(AccessDeniedError):
        await OperationLookupAuthorizationService(
            MockLookupFacts(replace(facts, has_exact_action_grant=False))
        ).require_authorization(access=ACCESS, request=query)


@pytest.mark.asyncio
async def test_availability_failure_is_not_missing_scope() -> None:
    reader = MockLookupFacts()
    reader.failure = DependencyUnavailableError()
    with pytest.raises(DependencyUnavailableError):
        await OperationLookupAuthorizationService(reader).require_authorization(
            access=ACCESS, request=QUERY
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "family,action,target",
    [
        (OperationLookupAuthorityFamily.ORGANIZATION_GRANT_READ, "create-projects", "organization"),
        (OperationLookupAuthorityFamily.ACCESS_GROUP_GRANT_READ, "add-documents", "access-groups"),
        (
            OperationLookupAuthorityFamily.APPLICATION_ACCOUNT_GRANT_READ,
            "issue-application-keys",
            "application-accounts",
        ),
    ],
)
@pytest.mark.parametrize("can_grant", [True, False])
async def test_other_access_grant_lookup_requires_exact_current_delegation(
    family: OperationLookupAuthorityFamily, action: str, target: str, can_grant: bool
) -> None:
    organization = target == "organization"
    route = (
        f"/v1/organizations/{QUERY.organization_id.value}/grants/{UUID(int=8)}/{action}"
        if organization
        else f"/v1/projects/{UUID(int=4)}/{target}/{UUID(int=7)}/grants/{UUID(int=8)}/{action}"
    )
    query = replace(
        QUERY,
        project_id=None if organization else QUERY.project_id,
        method=HttpMethod.PUT,
        requested_route=route,
        expected_authority=OperationLookupAuthority(family=family, action_id=ActionId(action)),
    )
    facts = replace(
        FACTS,
        project_status=None if organization else ProjectStatus.ACTIVE,
        is_project_member=not organization,
        can_grant_action=can_grant,
    )
    service = OperationLookupAuthorizationService(MockLookupFacts(facts))
    if can_grant:
        result = await service.require_authorization(access=ACCESS, request=query)
        assert result.organization_id == query.organization_id
        assert result.project_id == query.project_id
    else:
        # Use-only and group management never substitute for this exact delegated grant.
        with pytest.raises(AccessDeniedError):
            await service.require_authorization(access=ACCESS, request=query)


@pytest.mark.asyncio
@pytest.mark.parametrize("oauth", [False, True])
async def test_browser_currentness_preserves_the_presented_credential_family(oauth: bool) -> None:
    """Reject stale evidence before disclosing data, recovering originals or changing authority."""
    evidence = (
        MockAuthenticationEvidence.human_oauth() if oauth else MockAuthenticationEvidence.browser()
    )
    stale = HumanCredentialFactsDTO(True, HumanCredentialVersion(2))
    expected = HumanOAuthCredentialRejectedError if oauth else AuthenticationRequiredError
    reader = MockLookupFacts(replace(FACTS, oauth_credential_facts=stale))
    with pytest.raises(AuthenticationRequiredError) as caught:
        await OperationLookupAuthorizationService(reader).require_authorization(
            access=replace(ACCESS, authentication_evidence=evidence), request=QUERY
        )
    assert type(caught.value) is expected
