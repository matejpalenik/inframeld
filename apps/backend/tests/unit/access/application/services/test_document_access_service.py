from dataclasses import replace
from uuid import UUID

import pytest
from tests.support.application_key_scenarios import current_key_facts
from tests.support.authentication_evidence import MockAuthenticationEvidence
from tests.support.mock_document_access_facts_reader import MockDocumentAccessFactsReader
from tests.support.mock_project_metadata import ACCESS, ORGANIZATION_ID, PROJECT_ID

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.current_document_access_dto import (
    CurrentDocumentAccessDTO,
)
from inframeld_backend.access.application.dtos.document_access_facts_dto import (
    DocumentAccessFactsDTO,
)
from inframeld_backend.access.application.dtos.human_credential_facts_dto import (
    HumanCredentialFactsDTO,
)
from inframeld_backend.access.application.dtos.selected_document_source_dto import (
    SelectedDocumentSourceDTO,
)
from inframeld_backend.access.application.errors.application_key_credential_rejected_error import (
    ApplicationKeyCredentialRejectedError,
)
from inframeld_backend.access.application.errors.human_oauth_credential_rejected_error import (
    HumanOAuthCredentialRejectedError,
)
from inframeld_backend.access.application.services.document_access_service import (
    DocumentAccessService,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
from inframeld_backend.access.domain.value_objects.document_id import DocumentId
from inframeld_backend.access.domain.value_objects.document_source_id import DocumentSourceId
from inframeld_backend.access.domain.value_objects.document_version_id import DocumentVersionId
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    DependencyUnavailableError,
    ResourceNotFoundError,
)

D = DocumentId(UUID(int=10))
E = DocumentId(UUID(int=11))
S = DocumentSourceId(D, DocumentVersionId(UUID(int=12)))
V2 = DocumentSourceId(D, DocumentVersionId(UUID(int=13)))
T = DocumentSourceId(E, DocumentVersionId(UUID(int=14)))
G = AccessGroupId(UUID(int=20))
H = AccessGroupId(UUID(int=21))
BAD = AccessGroupId(UUID(int=22))
PRINCIPAL = Principal(
    ACCESS.actor_principal_id, ORGANIZATION_ID, PrincipalKind.HUMAN, PrincipalStatus.ACTIVE
)
FACTS = DocumentAccessFactsDTO(
    PRINCIPAL,
    ORGANIZATION_ID,
    PROJECT_ID,
    ProjectStatus.ACTIVE,
    True,
    False,
    HumanCredentialFactsDTO(True, HumanCredentialVersion(1)),
    frozenset((G, H)),
    frozenset((G,)),
)
DOC = CurrentDocumentAccessDTO(D, PROJECT_ID, frozenset((G, H)), True)
SELECTED = (
    SelectedDocumentSourceDTO(S, True),
    SelectedDocumentSourceDTO(V2, True),
    SelectedDocumentSourceDTO(T, True),
)
DOCS = (DOC, CurrentDocumentAccessDTO(E, PROJECT_ID, frozenset((H,)), True))


@pytest.mark.asyncio
async def test_query_returns_only_exact_selected_versions_and_bundle_is_atomic() -> None:
    reader = MockDocumentAccessFactsReader(FACTS)
    service = DocumentAccessService(reader)
    assert await service.permitted_sources(
        access=ACCESS, project_id=PROJECT_ID, selected=SELECTED, documents=DOCS
    ) == (S, V2)
    assert reader.calls[-1] == (ACCESS, PROJECT_ID, frozenset((G, H)))
    with pytest.raises(AccessDeniedError):
        await service.require_complete_evidence(
            access=ACCESS, project_id=PROJECT_ID, selected=SELECTED, documents=DOCS
        )
    assert await service.require_complete_evidence(
        access=ACCESS, project_id=PROJECT_ID, selected=SELECTED[:2], documents=(DOC,)
    ) == (S, V2)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    [
        "audience",
        "foreign-group",
        "empty-audience",
        "foreign-project",
        "erased-document",
        "erased-version",
    ],
)
async def test_current_logical_document_protects_all_selected_versions(change: str) -> None:
    doc = DOC
    selected = SELECTED[:2]
    if change == "audience":
        doc = replace(doc, audience=frozenset((H,)))
    if change == "foreign-group":
        doc = replace(doc, audience=frozenset((G, BAD)))
    if change == "empty-audience":
        doc = replace(doc, audience=frozenset())
    if change == "foreign-project":
        doc = replace(doc, project_id=ProjectId(UUID(int=900)))
    if change == "erased-document":
        doc = replace(doc, is_live=False)
    if change == "erased-version":
        selected = tuple(replace(s, is_live=False) for s in selected)
    service = DocumentAccessService(MockDocumentAccessFactsReader(FACTS))
    assert (
        await service.permitted_sources(
            access=ACCESS, project_id=PROJECT_ID, selected=selected, documents=(doc,)
        )
        == ()
    )
    with pytest.raises(AccessDeniedError):
        await service.require_complete_evidence(
            access=ACCESS, project_id=PROJECT_ID, selected=selected, documents=(doc,)
        )


@pytest.mark.asyncio
async def test_missing_observation_is_failure_not_empty_and_conflicts_fail_closed() -> None:
    service = DocumentAccessService(MockDocumentAccessFactsReader(FACTS))
    with pytest.raises(DependencyUnavailableError):
        await service.permitted_sources(
            access=ACCESS, project_id=PROJECT_ID, selected=SELECTED[:1], documents=()
        )
    with pytest.raises(RuntimeError, match="observations"):
        await service.permitted_sources(
            access=ACCESS,
            project_id=PROJECT_ID,
            selected=SELECTED[:1],
            documents=(DOC, replace(DOC, is_live=False)),
        )
    with pytest.raises(RuntimeError, match="observations"):
        await service.permitted_sources(
            access=ACCESS,
            project_id=PROJECT_ID,
            selected=(SELECTED[0], replace(SELECTED[0], is_live=False)),
            documents=(DOC,),
        )
    with pytest.raises(RuntimeError, match="observations"):
        await service.permitted_sources(
            access=ACCESS,
            project_id=PROJECT_ID,
            selected=(
                SELECTED[0],
                SelectedDocumentSourceDTO(DocumentSourceId(E, S.version_id), True),
            ),
            documents=DOCS,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "state",
    [
        "missing",
        "nonmember",
        "inactive",
        "deleting",
        "recovery",
        "wrong-actor",
        "wrong-project",
        "wrong-organization",
    ],
)
async def test_actor_and_scope_are_checked_before_empty_selection(state: str) -> None:
    facts = FACTS
    error = ResourceNotFoundError
    if state == "nonmember":
        facts = replace(facts, is_project_member=False)
    if state == "inactive":
        facts = replace(facts, principal=replace(PRINCIPAL, status=PrincipalStatus.SUSPENDED))
    if state == "deleting":
        facts = replace(facts, project_status=ProjectStatus.DELETING)
    if state == "recovery":
        facts = replace(facts, has_pending_recovery=True)
        error = AccessDeniedError
    if state == "wrong-actor":
        facts = replace(facts, principal=replace(PRINCIPAL, id=type(PRINCIPAL.id)(UUID(int=999))))
        error = RuntimeError
    if state == "wrong-project":
        facts = replace(facts, project_id=ProjectId(UUID(int=999)))
        error = RuntimeError
    if state == "wrong-organization":
        facts = replace(facts, organization_id=type(ORGANIZATION_ID)(UUID(int=999)))
        error = RuntimeError
    service = DocumentAccessService(
        MockDocumentAccessFactsReader(None if state == "missing" else facts)
    )
    with pytest.raises(error, match="requested actor or scope" if error is RuntimeError else None):
        await service.permitted_sources(
            access=ACCESS, project_id=PROJECT_ID, selected=(), documents=()
        )


@pytest.mark.asyncio
async def test_genuine_empty_and_repeated_decisions_observe_current_membership() -> None:
    reader = MockDocumentAccessFactsReader(FACTS)
    service = DocumentAccessService(reader)
    assert (
        await service.require_complete_evidence(
            access=ACCESS, project_id=PROJECT_ID, selected=(), documents=()
        )
        == ()
    )
    assert await service.permitted_sources(
        access=ACCESS, project_id=PROJECT_ID, selected=SELECTED[:1], documents=(DOC,)
    ) == (S,)
    reader.facts = replace(FACTS, member_group_ids=frozenset())
    assert (
        await service.permitted_sources(
            access=ACCESS, project_id=PROJECT_ID, selected=SELECTED[:1], documents=(DOC,)
        )
        == ()
    )
    assert len(reader.calls) == 3


@pytest.mark.asyncio
async def test_stale_oauth_precedes_empty_and_recovery() -> None:
    access = replace(ACCESS, authentication_evidence=MockAuthenticationEvidence.human_oauth())
    facts = replace(
        FACTS,
        has_pending_recovery=True,
        oauth_credential_facts=HumanCredentialFactsDTO(True, HumanCredentialVersion(2)),
    )
    service = DocumentAccessService(MockDocumentAccessFactsReader(facts))
    with pytest.raises(HumanOAuthCredentialRejectedError):
        await service.permitted_sources(
            access=access, project_id=PROJECT_ID, selected=(), documents=()
        )


@pytest.mark.asyncio
async def test_application_current_key_is_required_on_each_decision() -> None:
    evidence = MockAuthenticationEvidence.application_key()
    access = AccessContextDTO(PRINCIPAL.id, evidence)
    key = current_key_facts(
        key_id=evidence.key_id,
        principal_id=PRINCIPAL.id,
        organization_id=ORGANIZATION_ID,
        project_id=PROJECT_ID,
    )
    reader = MockDocumentAccessFactsReader(
        replace(
            FACTS,
            principal=replace(PRINCIPAL, kind=PrincipalKind.APPLICATION),
            application_key_facts=key,
        )
    )
    service = DocumentAccessService(reader)
    assert await service.permitted_sources(
        access=access, project_id=PROJECT_ID, selected=SELECTED[:1], documents=(DOC,)
    ) == (S,)
    assert reader.facts is not None
    reader.facts = replace(
        reader.facts, application_key_facts=replace(key, revoked_at=key.checked_at)
    )
    with pytest.raises(ApplicationKeyCredentialRejectedError):
        await service.permitted_sources(
            access=access, project_id=PROJECT_ID, selected=(), documents=()
        )
