"""Validate the captured reply from one confined parser attempt."""

import json
from dataclasses import dataclass, field
from hashlib import sha256
from typing import TYPE_CHECKING, cast
from uuid import UUID

from inframeld_parser.canonical_pdf import (
    MAX_OUTPUT_BYTES,
    InvalidCanonicalPdf,
    TextBlock,
    canonicalize,
)

if TYPE_CHECKING:
    from inframeld_parser.canonical_pdf import CanonicalPdf
    from inframeld_parser.parse_request import ParseRequest

_MAX_HEADER_BYTES = 64 * 1024
_MAX_CHUNKS = 2000
_MAX_PAGES = 500
_FRAME_SIZE = "The parser result is outside the frame size limit."
_INVALID_HEADER = "The parser result header is invalid."
_INVALID_CANONICAL = "The parser result canonical artifact is invalid."
_INVALID_RANGES = "The parser result chunk ranges are invalid."


@dataclass(frozen=True, slots=True)
class ParseResult:
    attempt_id: UUID
    source_sha256: str
    canonical_sha256: str
    chunk_ranges: tuple[tuple[int, int], ...]
    canonical_bytes: bytes = field(repr=False)


class ParseResultError(ValueError):
    """A captured child reply failed verification."""


def encode_parse_result(
    attempt_id: UUID,
    artifact: "CanonicalPdf",
    chunk_ranges: tuple[tuple[int, int], ...],
) -> bytes:
    """Encode one bounded child frame for independent validation by the supervisor."""
    return _encode(attempt_id, artifact, chunk_ranges)


def encode_verified_result(result: ParseResult) -> bytes:
    """Return the same frame format after the supervisor has verified the child reply."""
    return _encode(result.attempt_id, result, result.chunk_ranges)


def _encode(
    attempt_id: UUID,
    artifact: "CanonicalPdf | ParseResult",
    chunk_ranges: tuple[tuple[int, int], ...],
) -> bytes:
    canonical = artifact.canonical_bytes
    if not 0 < len(canonical) < MAX_OUTPUT_BYTES - 4:
        raise ParseResultError(_FRAME_SIZE)
    if not 1 <= len(chunk_ranges) <= _MAX_CHUNKS:
        raise ParseResultError(_INVALID_RANGES)
    header = json.dumps(
        {
            "attempt_id": str(attempt_id),
            "source_sha256": artifact.source_sha256,
            "canonical_sha256": artifact.canonical_sha256,
            "canonical_size": len(canonical),
            "chunk_ranges": chunk_ranges,
        },
        separators=(",", ":"),
    ).encode("utf-8")
    if len(header) > _MAX_HEADER_BYTES or 4 + len(header) + len(canonical) > MAX_OUTPUT_BYTES:
        raise ParseResultError(_FRAME_SIZE)
    return len(header).to_bytes(4, "big") + header + canonical


def validate_parse_result(capture: bytes, *, request: "ParseRequest") -> ParseResult:
    """Bind a complete captured frame to the request and verify its canonical ranges.

    A frame contains a u32 header length, strict UTF-8 JSON and the exact canonical
    bytes. Range validation establishes source positions. Publication requires its
    own verification of the processing outcome.
    """
    if not 4 < len(capture) <= MAX_OUTPUT_BYTES:
        raise ParseResultError(_FRAME_SIZE)
    header_size = int.from_bytes(capture[:4], "big")
    body_start = 4 + header_size
    if not 1 <= header_size <= _MAX_HEADER_BYTES or body_start >= len(capture):
        raise ParseResultError(_INVALID_HEADER)

    header = _read_object(capture[4:body_start], _INVALID_HEADER)
    if header.keys() != {
        "attempt_id",
        "source_sha256",
        "canonical_sha256",
        "canonical_size",
        "chunk_ranges",
    }:
        raise ParseResultError(_INVALID_HEADER)
    canonical_size = header["canonical_size"]
    if (
        header["attempt_id"] != str(request.attempt_id)
        or header["source_sha256"] != request.source_sha256
        or type(canonical_size) is not int
        or canonical_size != len(capture) - body_start
    ):
        raise ParseResultError(_INVALID_HEADER)

    canonical_bytes = capture[body_start:]
    canonical_sha256 = sha256(canonical_bytes).hexdigest()
    if header["canonical_sha256"] != canonical_sha256:
        raise ParseResultError("The parser result canonical digest did not match.")

    spans = _canonical_spans(canonical_bytes, request.source_sha256)
    ranges = _chunk_ranges(header["chunk_ranges"], spans)
    return ParseResult(
        request.attempt_id, request.source_sha256, canonical_sha256, ranges, canonical_bytes
    )


def _canonical_spans(canonical_bytes: bytes, source_sha256: str) -> list[tuple[int, int]]:
    canonical = _read_object(canonical_bytes, _INVALID_CANONICAL)
    text = canonical.get("text")
    raw_blocks = canonical.get("blocks")
    if (
        canonical.keys() != {"format", "text", "blocks"}
        or canonical["format"] != "inframeld-pdf-canonical-v1"
        or not isinstance(text, str)
        or not isinstance(raw_blocks, list)
    ):
        raise ParseResultError(_INVALID_CANONICAL)

    spans: list[tuple[int, int]] = []
    blocks: list[TextBlock] = []
    previous_end = 0
    for raw_block in cast("list[object]", raw_blocks):
        if not isinstance(raw_block, dict):
            raise ParseResultError(_INVALID_CANONICAL)
        block = cast("dict[str, object]", raw_block)
        if block.keys() != {"kind", "span", "pages"} or block["kind"] != "text":
            raise ParseResultError(_INVALID_CANONICAL)
        start, end = _span(block["span"], _INVALID_CANONICAL)
        if not previous_end <= start <= end <= len(text):
            raise ParseResultError(_INVALID_CANONICAL)
        pages = _source_pages(block["pages"])
        spans.append((start, end))
        blocks.append(TextBlock(text[start:end], pages))
        previous_end = end

    try:
        regenerated = canonicalize(blocks, source_sha256=source_sha256)
    except InvalidCanonicalPdf:
        raise ParseResultError(_INVALID_CANONICAL) from None
    if regenerated.canonical_bytes != canonical_bytes:
        raise ParseResultError(_INVALID_CANONICAL)
    return spans


def _source_pages(raw: object) -> tuple[int, ...]:
    if not isinstance(raw, list):
        raise ParseResultError(_INVALID_CANONICAL)
    values = cast("list[object]", raw)
    if not 1 <= len(values) <= _MAX_PAGES:
        raise ParseResultError(_INVALID_CANONICAL)
    pages: list[int] = []
    previous = 0
    for page in values:
        if type(page) is not int or not previous < page <= _MAX_PAGES:
            raise ParseResultError(_INVALID_CANONICAL)
        pages.append(page)
        previous = page
    return tuple(pages)


def _chunk_ranges(raw: object, spans: list[tuple[int, int]]) -> tuple[tuple[int, int], ...]:
    if not isinstance(raw, list):
        raise ParseResultError(_INVALID_RANGES)
    values = cast("list[object]", raw)
    if not 1 <= len(values) <= _MAX_CHUNKS:
        raise ParseResultError(_INVALID_RANGES)
    ranges: list[tuple[int, int]] = []
    previous_end = 0
    block = 0
    for item in values:
        start, end = _span(item, _INVALID_RANGES)
        if not previous_end <= start < end:
            raise ParseResultError(_INVALID_RANGES)
        while block < len(spans) and spans[block][1] <= start:
            block += 1
        if block == len(spans) or not (spans[block][0] <= start and end <= spans[block][1]):
            raise ParseResultError(_INVALID_RANGES)
        ranges.append((start, end))
        previous_end = end
    return tuple(ranges)


def _span(raw: object, failure: str) -> tuple[int, int]:
    if not isinstance(raw, list):
        raise ParseResultError(failure)
    values = cast("list[object]", raw)
    if len(values) != 2:
        raise ParseResultError(failure)
    start, end = values
    if type(start) is not int or type(end) is not int:
        raise ParseResultError(failure)
    return start, end


def _read_object(raw: bytes, failure: str) -> dict[str, object]:
    try:
        value: object = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_fields)
    except (ValueError, RecursionError):
        raise ParseResultError(failure) from None
    if not isinstance(value, dict):
        raise ParseResultError(failure)
    return cast("dict[str, object]", value)


def _unique_fields(pairs: list[tuple[str, object]]) -> dict[str, object]:
    fields = dict(pairs)
    if len(fields) != len(pairs):
        raise ValueError("A JSON object has duplicate fields.")
    return fields
