import asyncio
import json
import socket
import struct
import sys
from pathlib import Path
from typing import cast, override
from uuid import UUID

from inframeld_backend.indexing.application.dtos.parsed_pdf_dto import ParsedPdfDTO
from inframeld_backend.indexing.application.errors.pdf_parse_error import PdfParseError
from inframeld_backend.indexing.application.protocols.pdf_parser import PdfParser
from inframeld_backend.indexing.domain.value_objects.docling_processing_definition import (
    DoclingProcessingDefinition,
)
from inframeld_backend.shared.application.value_objects.artifact_content_digest import (
    ArtifactContentDigest,
)

_WORK_SECONDS = 300
_MAX_SOURCE_BYTES = 25 * 1024**2
_MAX_RESPONSE_BYTES = 32 * 1024**2
_MAX_HEADER_BYTES = 64 * 1024
_MAX_TEXT_BYTES = 10 * 1024**2
_MAX_PAGES = 500
_MAX_CHUNKS = 2000
_PEER_CREDENTIALS = struct.Struct("=iII")
_PEER_NOT_VERIFIED = "The parser peer identity could not be verified."
_INVALID_RESULT = "The parser returned an invalid reply."


class UnixPdfParser(PdfParser):
    """Exchange one bounded request with the trusted Unix parser supervisor."""

    def __init__(self, path: Path, *, expected_peer_uid: int) -> None:
        if not path.is_absolute() or "\0" in str(path):
            raise ValueError("The parser requires an absolute Unix socket path.")
        if type(expected_peer_uid) is not int or not 0 < expected_peer_uid < 2**32 - 1:
            raise ValueError("The parser requires an explicit unprivileged peer UID.")
        self._path = path
        self._expected_peer_uid = expected_peer_uid

    @override
    async def parse(
        self,
        source: bytes,
        *,
        attempt_id: UUID,
        source_digest: ArtifactContentDigest,
        definition: DoclingProcessingDefinition,
        deadline: float,
    ) -> ParsedPdfDTO:
        loop = asyncio.get_running_loop()
        if not 0 < deadline - loop.time() <= _WORK_SECONDS:
            raise PdfParseError("The parser request deadline is invalid.", cleanup_confirmed=True)
        if (
            type(source) is not bytes
            or not 1 <= len(source) <= _MAX_SOURCE_BYTES
            or type(attempt_id) is not UUID
            or type(source_digest) is not ArtifactContentDigest
            or ArtifactContentDigest.from_content(source) != source_digest
        ):
            raise PdfParseError(
                "The parser source did not match its sealed expectation.", cleanup_confirmed=True
            )
        if (
            type(definition) is not DoclingProcessingDefinition
            or definition.merge_peers is not False
            or definition.repeat_table_header is not True
            or definition.ocr_enabled is not False
        ):
            raise PdfParseError(
                "The saved definition is unsupported by this parser.", cleanup_confirmed=True
            )

        header = json.dumps(
            {
                "attempt_id": str(attempt_id),
                "source_sha256": source_digest.value.hex(),
                "source_size": len(source),
                "max_content_tokens": definition.max_content_tokens,
                "merge_peers": False,
            },
            separators=(",", ":"),
        ).encode("utf-8")
        try:
            _check_deadline(loop, deadline)
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                connection.setblocking(False)
                async with asyncio.timeout_at(deadline):
                    await loop.sock_connect(connection, str(self._path))
                    if self._peer_uid(connection) != self._expected_peer_uid:
                        raise PdfParseError(_PEER_NOT_VERIFIED, cleanup_confirmed=True)
                    _check_deadline(loop, deadline)
                    await loop.sock_sendall(connection, len(header).to_bytes(4, "big") + header)
                    _check_deadline(loop, deadline)
                    await loop.sock_sendall(connection, source)
                    result = await _read_reply(
                        loop, connection, attempt_id, source_digest, deadline
                    )
                    _check_deadline(loop, deadline)
                    return result
        except TimeoutError:
            raise PdfParseError(
                "The parser request deadline elapsed.", cleanup_confirmed=False
            ) from None
        except OSError:
            raise PdfParseError("The parser connection failed.", cleanup_confirmed=False) from None

    @staticmethod
    def _peer_uid(connection: socket.socket) -> int:
        if sys.platform != "linux" or not hasattr(socket, "SO_PEERCRED"):
            raise PdfParseError(_PEER_NOT_VERIFIED, cleanup_confirmed=True)
        try:
            credentials = connection.getsockopt(
                socket.SOL_SOCKET, socket.SO_PEERCRED, _PEER_CREDENTIALS.size
            )
            _, uid, _ = _PEER_CREDENTIALS.unpack(credentials)
        except (OSError, struct.error):
            raise PdfParseError(_PEER_NOT_VERIFIED, cleanup_confirmed=True) from None
        return uid


def _check_deadline(loop: asyncio.AbstractEventLoop, deadline: float) -> None:
    if loop.time() >= deadline:
        raise TimeoutError


async def _read_reply(
    loop: asyncio.AbstractEventLoop,
    connection: socket.socket,
    attempt_id: UUID,
    source_digest: ArtifactContentDigest,
    deadline: float,
) -> ParsedPdfDTO:
    header_size = int.from_bytes(await _receive(loop, connection, 4), "big")
    if header_size == 0:
        status = await _receive(loop, connection, 1)
        if not await loop.sock_recv(connection, 1):
            _check_deadline(loop, deadline)
            if status == b"\x01":
                raise PdfParseError("The parser rejected the request.", cleanup_confirmed=True)
            if status == b"\x02":
                raise PdfParseError("The parser attempt failed.", cleanup_confirmed=True)
            if status == b"\x03":
                raise PdfParseError(
                    "The parser cleanup could not be confirmed.", cleanup_confirmed=False
                )
        raise PdfParseError(_INVALID_RESULT)
    if header_size > _MAX_HEADER_BYTES:
        raise PdfParseError(_INVALID_RESULT)

    header = _read_object(await _receive(loop, connection, header_size))
    canonical_size = header.get("canonical_size")
    if (
        header.keys()
        != {"attempt_id", "source_sha256", "canonical_sha256", "canonical_size", "chunk_ranges"}
        or header["attempt_id"] != str(attempt_id)
        or header["source_sha256"] != source_digest.value.hex()
        or type(canonical_size) is not int
        or not 1 <= canonical_size <= _MAX_RESPONSE_BYTES - 4 - header_size
    ):
        raise PdfParseError(_INVALID_RESULT)

    canonical = await _receive(loop, connection, canonical_size)
    if await loop.sock_recv(connection, 1):
        raise PdfParseError(_INVALID_RESULT)
    canonical_digest = ArtifactContentDigest.from_content(canonical)
    if header["canonical_sha256"] != canonical_digest.value.hex():
        raise PdfParseError(_INVALID_RESULT)
    blocks = _canonical_spans(canonical)
    ranges = _chunk_ranges(header["chunk_ranges"], blocks)
    return ParsedPdfDTO(
        attempt_id=attempt_id,
        source_digest=source_digest,
        canonical_digest=canonical_digest,
        canonical_bytes=canonical,
        chunk_ranges=ranges,
    )


async def _receive(loop: asyncio.AbstractEventLoop, connection: socket.socket, size: int) -> bytes:
    data = bytearray(size)
    view = memoryview(data)
    position = 0
    while position < size:
        received = await loop.sock_recv_into(connection, view[position:])
        if not received:
            raise PdfParseError(_INVALID_RESULT)
        position += received
    return bytes(data)


def _canonical_spans(canonical: bytes) -> list[tuple[int, int]]:
    document = _read_object(canonical)
    text = document.get("text")
    raw_blocks = document.get("blocks")
    if (
        tuple(document) != ("format", "blocks", "text")
        or document["format"] != "inframeld-pdf-canonical-v1"
        or not isinstance(text, str)
        or not text.strip()
        or "\r" in text
        or not isinstance(raw_blocks, list)
        or not raw_blocks
    ):
        raise PdfParseError(_INVALID_RESULT)
    try:
        if len(text.encode("utf-8")) > _MAX_TEXT_BYTES:
            raise PdfParseError(_INVALID_RESULT)
    except UnicodeEncodeError:
        raise PdfParseError(_INVALID_RESULT) from None

    spans: list[tuple[int, int]] = []
    end = 0
    for raw_block in cast("list[object]", raw_blocks):
        if not isinstance(raw_block, dict):
            raise PdfParseError(_INVALID_RESULT)
        block = cast("dict[str, object]", raw_block)
        if tuple(block) != ("kind", "pages", "span") or block["kind"] != "text":
            raise PdfParseError(_INVALID_RESULT)
        if spans:
            # Each canonical block contributes one explicit LF separator.
            if text[end : end + 1] != "\n":
                raise PdfParseError(_INVALID_RESULT)
            end += 1
        start, stop = _range(block["span"])
        if start != end or not start <= stop <= len(text) or not _valid_pages(block["pages"]):
            raise PdfParseError(_INVALID_RESULT)
        spans.append((start, stop))
        end = stop

    if (
        end != len(text)
        or json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        != canonical
    ):
        raise PdfParseError(_INVALID_RESULT)
    return spans


def _valid_pages(raw: object) -> bool:
    if not isinstance(raw, list):
        return False
    pages = cast("list[object]", raw)
    if not 1 <= len(pages) <= _MAX_PAGES:
        return False
    previous = 0
    for page in pages:
        if type(page) is not int or not previous < page <= _MAX_PAGES:
            return False
        previous = page
    return True


def _chunk_ranges(raw: object, blocks: list[tuple[int, int]]) -> tuple[tuple[int, int], ...]:
    if not isinstance(raw, list):
        raise PdfParseError(_INVALID_RESULT)
    ranges = cast("list[object]", raw)
    if not 1 <= len(ranges) <= _MAX_CHUNKS:
        raise PdfParseError(_INVALID_RESULT)
    result: list[tuple[int, int]] = []
    last_end = 0
    block = 0
    for raw_range in ranges:
        start, end = _range(raw_range)
        if not last_end <= start < end:
            raise PdfParseError(_INVALID_RESULT)
        while block < len(blocks) and blocks[block][1] <= start:
            block += 1
        if block == len(blocks) or not blocks[block][0] <= start < end <= blocks[block][1]:
            raise PdfParseError(_INVALID_RESULT)
        result.append((start, end))
        last_end = end
    return tuple(result)


def _range(raw: object) -> tuple[int, int]:
    if not isinstance(raw, list):
        raise PdfParseError(_INVALID_RESULT)
    coordinates = cast("list[object]", raw)
    if len(coordinates) != 2:
        raise PdfParseError(_INVALID_RESULT)
    start, end = coordinates
    if type(start) is not int or type(end) is not int:
        raise PdfParseError(_INVALID_RESULT)
    return start, end


def _read_object(raw: bytes) -> dict[str, object]:
    try:
        value: object = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_fields)
    except (ValueError, RecursionError):
        raise PdfParseError(_INVALID_RESULT) from None
    if not isinstance(value, dict):
        raise PdfParseError(_INVALID_RESULT)
    return cast("dict[str, object]", value)


def _unique_fields(pairs: list[tuple[str, object]]) -> dict[str, object]:
    fields = dict(pairs)
    if len(fields) != len(pairs):
        raise ValueError("The parser reply repeats a JSON field.")
    return fields
