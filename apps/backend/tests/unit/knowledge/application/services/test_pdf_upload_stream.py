from collections.abc import AsyncIterator

import pytest

from inframeld_backend.knowledge.application.errors.document_upload_errors import (
    PdfUploadTooLargeError,
)
from inframeld_backend.knowledge.application.services.pdf_upload_stream import PdfUploadStream
from inframeld_backend.shared.application.value_objects.artifact_content_digest import (
    ArtifactContentDigest,
)


async def _chunks(*parts: bytes) -> AsyncIterator[bytes]:
    for part in parts:
        yield part


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("version", "separator"),
    [(b"1.0", b"\r"), (b"1.7", b"\n"), (b"2.0", b"\r\n")],
)
async def test_hashes_the_actual_file_across_chunk_boundaries(
    version: bytes, separator: bytes
) -> None:
    parts = (b"%P", b"DF", b"-" + version, separator[:1], separator[1:] + b"original bytes\n")
    stream = PdfUploadStream("handbook.pdf", _chunks(*parts))

    observed = b"".join([part async for part in stream.read()])

    assert observed == b"".join(parts)
    assert stream.digest == ArtifactContentDigest.from_content(observed)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("filename", "parts"),
    [
        ("handbook.txt", (b"%PDF-1.7\n",)),
        ("handbook.pdf", (b"not a PDF",)),
        ("handbook.pdf", (b"%P", b"DF")),
        ("handbook.pdf", ()),
        ("handbook.pdf", (b"%PDF-",)),
        ("handbook.pdf", (b"%PDF-1.8\n",)),
        ("handbook.pdf", (b"%PDF-3.0\n",)),
        ("handbook.pdf", (b"%PDF-2.0",)),
        ("handbook.pdf", (b"%PDF-1.7", b" body")),
    ],
)
async def test_rejects_wrong_extension_or_invalid_header_before_yield(
    filename: str, parts: tuple[bytes, ...]
) -> None:
    with pytest.raises(ValueError):
        stream = PdfUploadStream(filename, _chunks(*parts))
        assert [part async for part in stream.read()] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("excess", [0, 1])
async def test_checks_the_actual_byte_limit(excess: int) -> None:
    prefix = b"%PDF-1.7\n"
    payload = b"x" * (25 * 1024 * 1024 - len(prefix))
    parts = (prefix, payload, b"x" * excess)
    stream = PdfUploadStream("handbook.pdf", _chunks(*parts))

    if excess:
        with pytest.raises(PdfUploadTooLargeError):
            assert sum([len(part) async for part in stream.read()]) == 0
    else:
        assert sum([len(part) async for part in stream.read()]) == 25 * 1024 * 1024
        assert stream.digest == ArtifactContentDigest.from_content(prefix + payload)
