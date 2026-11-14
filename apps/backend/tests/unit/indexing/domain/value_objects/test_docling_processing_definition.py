from dataclasses import FrozenInstanceError, replace
from typing import Literal, cast

import pytest

from inframeld_backend.indexing.domain.value_objects.docling_processing_definition import (
    DoclingProcessingDefinition,
)

_DEFINITION = DoclingProcessingDefinition(
    docling_slim_version="2.148.0",
    docling_core_version="2.106.0",
    asset_manifest_sha256="7ea9f3c967a7bc66d2501e466334e7aef46a639e01a11376888321e0f0a51d0e",
    max_content_tokens=1024,
    merge_peers=True,
    repeat_table_header=True,
    ocr_enabled=False,
)


def test_chunk_settings_change_the_definition_without_changing_pinned_assets() -> None:
    smaller_chunks = replace(_DEFINITION, max_content_tokens=1)
    separate_peers = replace(_DEFINITION, merge_peers=False)
    omit_repeated_headers = replace(_DEFINITION, repeat_table_header=False)

    assert len({_DEFINITION, smaller_chunks, separate_peers, omit_repeated_headers}) == 4
    assert smaller_chunks.asset_manifest_sha256 == _DEFINITION.asset_manifest_sha256
    assert _DEFINITION.max_content_tokens == 1024
    with pytest.raises(FrozenInstanceError):
        _DEFINITION.__setattr__("max_content_tokens", 1)


@pytest.mark.parametrize("tokens", [0, 1025])
def test_rejects_content_token_limits_outside_the_supported_range(tokens: int) -> None:
    with pytest.raises(ValueError, match="content tokens"):
        replace(_DEFINITION, max_content_tokens=tokens)


@pytest.mark.parametrize("tokens", [True, 12.0])
def test_rejects_implicitly_coerced_token_limits(tokens: object) -> None:
    with pytest.raises(TypeError, match="whole number"):
        replace(_DEFINITION, max_content_tokens=cast(int, tokens))


@pytest.mark.parametrize(
    "slim,core,manifest",
    [
        ("2.148.1", _DEFINITION.docling_core_version, _DEFINITION.asset_manifest_sha256),
        (_DEFINITION.docling_slim_version, "2.106.1", _DEFINITION.asset_manifest_sha256),
        (_DEFINITION.docling_slim_version, _DEFINITION.docling_core_version, "a" * 64),
    ],
)
def test_rejects_unapproved_source_identities(slim: str, core: str, manifest: str) -> None:
    with pytest.raises(ValueError, match="pinned"):
        replace(
            _DEFINITION,
            docling_slim_version=slim,
            docling_core_version=core,
            asset_manifest_sha256=manifest,
        )


@pytest.mark.parametrize("merge_peers,repeat_table_header", [(1, True), (True, "false")])
def test_rejects_implicitly_coerced_chunk_switches(
    merge_peers: object, repeat_table_header: object
) -> None:
    with pytest.raises(TypeError, match="booleans"):
        replace(
            _DEFINITION,
            merge_peers=cast(bool, merge_peers),
            repeat_table_header=cast(bool, repeat_table_header),
        )


@pytest.mark.parametrize("ocr", [True, 0])
def test_requires_explicitly_disabled_ocr(ocr: object) -> None:
    with pytest.raises(ValueError, match="OCR"):
        replace(_DEFINITION, ocr_enabled=cast(Literal[False], ocr))
