from uuid import UUID

import pytest

from inframeld_backend.access.domain.policies.document_read_policy import DocumentReadPolicy
from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
from inframeld_backend.access.domain.value_objects.document_id import DocumentId
from inframeld_backend.access.domain.value_objects.document_source_id import DocumentSourceId
from inframeld_backend.access.domain.value_objects.document_version_id import DocumentVersionId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId

P = ProjectId(UUID(int=1))
OTHER = ProjectId(UUID(int=2))
G = AccessGroupId(UUID(int=3))
H = AccessGroupId(UUID(int=4))
BAD = AccessGroupId(UUID(int=5))


@pytest.mark.parametrize(
    ("project", "source_live", "document_live", "audience", "valid", "members", "allowed"),
    [
        (P, True, True, (G,), (G,), (G,), True),
        (P, True, True, (G, H), (G, H), (H,), True),
        (P, True, True, (G,), (G,), (), False),
        (P, True, True, (), (), (G,), False),
        (P, True, True, (G, BAD), (G,), (G,), False),
        (P, True, True, (BAD,), (), (BAD,), False),
        (OTHER, True, True, (G,), (G,), (G,), False),
        (P, False, True, (G,), (G,), (G,), False),
        (P, True, False, (G,), (G,), (G,), False),
    ],
)
def test_complete_current_audience_before_membership_or(
    project: ProjectId,
    source_live: bool,
    document_live: bool,
    audience: tuple[AccessGroupId, ...],
    valid: tuple[AccessGroupId, ...],
    members: tuple[AccessGroupId, ...],
    allowed: bool,
) -> None:
    assert (
        DocumentReadPolicy.may_read(
            requested_project_id=P,
            document_project_id=project,
            source_is_live=source_live,
            document_is_live=document_live,
            audience=frozenset(audience),
            valid_group_ids=frozenset(valid),
            member_group_ids=frozenset(members),
        )
        is allowed
    )


def test_source_preserves_both_runtime_identities() -> None:
    document = DocumentId(UUID(int=10))
    first = DocumentSourceId(document, DocumentVersionId(UUID(int=11)))
    second = DocumentSourceId(document, DocumentVersionId(UUID(int=12)))
    assert first != second
    assert first.document_id == second.document_id
    assert first.version_id != second.version_id


@pytest.mark.parametrize("kind", [DocumentId, DocumentVersionId])
def test_ids_reject_unparsed_input(kind: type[DocumentId] | type[DocumentVersionId]) -> None:
    with pytest.raises(TypeError):
        kind("not-a-uuid")  # type: ignore[arg-type]
