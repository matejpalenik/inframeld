from dataclasses import replace
from typing import Literal, cast
from uuid import UUID

import pytest

from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.indexing.domain.value_objects.embedding_profile_id import EmbeddingProfileId
from inframeld_backend.indexing.domain.value_objects.vector_layout_id import VectorLayoutId
from inframeld_backend.indexing.domain.value_objects.vector_shard_layout import VectorShardLayout

_LAYOUT = VectorShardLayout(
    organization_id=OrganizationId(UUID("00112233-4455-4677-8899-aabbccddeeff")),
    project_id=ProjectId(UUID("fedcba98-7654-4321-8abc-def001234567")),
    embedding_profile_id=EmbeddingProfileId(UUID("39d43702-e1b6-4395-bfcd-1e8aaec38009")),
    layout_id=VectorLayoutId(UUID("8ee0d03d-099e-449d-8533-c9fab6648ad2")),
    shard_count=2,
)


def test_v1_collection_names_are_stable_for_each_saved_shard() -> None:
    assert _LAYOUT.version == 1
    assert (
        _LAYOUT.collection_name(0) == "im-v1-vbldmbiamxnjrpw7ewfhvwb6lz6dagbkqv4ocx3q5tnnpl72xl6q"
    )
    assert (
        _LAYOUT.collection_name(1) == "im-v1-r2uanthcfj6cbetkyegzf3serpm2ejpwdvrmxw5xb6cwqstmwezq"
    )


def test_each_scope_identity_separates_physical_collections() -> None:
    changed_id = UUID("d7cf458d-5eae-4682-9b6d-b976fe6155a1")
    layouts = (
        _LAYOUT,
        replace(_LAYOUT, organization_id=OrganizationId(changed_id)),
        replace(_LAYOUT, project_id=ProjectId(changed_id)),
        replace(_LAYOUT, embedding_profile_id=EmbeddingProfileId(changed_id)),
        replace(_LAYOUT, layout_id=VectorLayoutId(changed_id)),
    )

    assert len({layout.collection_name(0) for layout in layouts}) == len(layouts)


def test_v1_placement_uses_the_exact_opaque_bytes_and_saved_count() -> None:
    single_shard = replace(_LAYOUT, shard_count=1)

    # These two binary IDs differ only by a trailing zero byte.
    assert _LAYOUT.shard_for(b"\x00\xff") == 0
    assert _LAYOUT.shard_for(b"\x00\xff\x00") == 1
    assert single_shard.shard_for(b"\x00\xff\x00") == 0
    with pytest.raises(ValueError, match="ordinal"):
        single_shard.collection_name(1)


@pytest.mark.parametrize("version", [0, 2])
def test_rejects_an_unsupported_placement_version(version: int) -> None:
    with pytest.raises(ValueError, match="version"):
        replace(_LAYOUT, version=cast(Literal[1], version))


@pytest.mark.parametrize("count", [0, 3])
def test_rejects_an_unsupported_shard_count(count: int) -> None:
    with pytest.raises(ValueError, match="shard count"):
        replace(_LAYOUT, shard_count=count)


@pytest.mark.parametrize("ordinal", [-1, 2])
def test_rejects_an_ordinal_outside_the_saved_layout(ordinal: int) -> None:
    with pytest.raises(ValueError, match="ordinal"):
        _LAYOUT.collection_name(ordinal)


def test_does_not_coerce_layout_numbers() -> None:
    with pytest.raises(TypeError, match="version"):
        replace(_LAYOUT, version=cast(Literal[1], True))
    with pytest.raises(TypeError, match="shard count"):
        replace(_LAYOUT, shard_count=True)
    with pytest.raises(TypeError, match="ordinal"):
        _LAYOUT.collection_name(True)


def test_does_not_coerce_record_ids() -> None:
    with pytest.raises(TypeError, match="bytes"):
        _LAYOUT.shard_for(cast(bytes, "record-1"))


def test_rejects_misplaced_typed_identifiers() -> None:
    with pytest.raises(TypeError, match="typed"):
        replace(_LAYOUT, project_id=cast(ProjectId, _LAYOUT.organization_id))
    with pytest.raises(TypeError, match="typed"):
        replace(_LAYOUT, layout_id=cast(VectorLayoutId, _LAYOUT.embedding_profile_id))


def test_requires_parsed_uuids_for_both_identifiers() -> None:
    unparsed = cast(UUID, "00112233-4455-4677-8899-aabbccddeeff")

    with pytest.raises(TypeError, match="parsed UUID"):
        EmbeddingProfileId(unparsed)
    with pytest.raises(TypeError, match="parsed UUID"):
        VectorLayoutId(unparsed)
