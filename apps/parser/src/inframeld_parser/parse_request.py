"""Read one bounded request from the private parser socket."""

import json
import re
from dataclasses import dataclass, field
from hashlib import sha256
from math import isfinite
from socket import AF_UNIX, SOCK_STREAM, socket
from time import monotonic
from typing import cast
from uuid import UUID

from inframeld_parser.pdf_conversion import MAX_INPUT_BYTES

_MAX_HEADER_BYTES = 1024
_HEADER_FIELDS = {"attempt_id", "source_sha256", "source_size", "max_content_tokens", "merge_peers"}
_INVALID_HEADER = "The parser request header is invalid."
_DEADLINE_ELAPSED = "The parser request deadline elapsed."
# Keep the converter's version-bearing PDF first-line check at the intake boundary.
_PDF_HEADER = re.compile(rb"%PDF-(?:1\.[0-7]|2\.0)[\r\n]")


@dataclass(frozen=True, slots=True)
class ParseRequest:
    attempt_id: UUID
    source_sha256: str
    max_content_tokens: int
    source: bytes = field(repr=False)


class ParseRequestError(ValueError):
    """A request could not be accepted by the private parser."""


def read_parse_request(connection: socket, *, deadline: float) -> ParseRequest:
    """Read a u32 header length, strict UTF-8 JSON and the declared PDF bytes.

    The caller owns the connected Unix stream and an absolute monotonic deadline.
    The result represents one frame. The caller owns the remaining connection lifetime.
    """
    if connection.family != AF_UNIX or connection.type != SOCK_STREAM or connection.fileno() < 0:
        raise ParseRequestError("The parser requires an open Unix stream.")
    if not isfinite(deadline):
        raise ParseRequestError(_DEADLINE_ELAPSED)

    previous_timeout = connection.gettimeout()
    try:
        size = int.from_bytes(_read_exactly(connection, 4, deadline), "big")
        if not 1 <= size <= _MAX_HEADER_BYTES:
            raise ParseRequestError(_INVALID_HEADER)
        attempt_id, source_sha256, source_size, max_content_tokens = _read_header(
            _read_exactly(connection, size, deadline)
        )
        source = _read_exactly(connection, source_size, deadline)
    except TimeoutError:
        raise ParseRequestError(_DEADLINE_ELAPSED) from None
    except OSError:
        raise ParseRequestError("The parser request could not be read.") from None
    finally:
        connection.settimeout(previous_timeout)

    if not _PDF_HEADER.match(source):
        raise ParseRequestError("The parser source has no supported PDF header.")
    if sha256(source).hexdigest() != source_sha256:
        raise ParseRequestError("The parser source digest did not match.")
    if monotonic() >= deadline:
        raise ParseRequestError(_DEADLINE_ELAPSED)
    return ParseRequest(attempt_id, source_sha256, max_content_tokens, source)


def _read_exactly(connection: socket, size: int, deadline: float) -> bytes:
    data = bytearray(size)
    view = memoryview(data)
    position = 0
    while position < size:
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise ParseRequestError(_DEADLINE_ELAPSED)
        connection.settimeout(remaining)
        received = connection.recv_into(view[position:])
        if received == 0:
            raise ParseRequestError("The parser request was truncated.")
        position += received
    return bytes(data)


def _read_header(raw: bytes) -> tuple[UUID, str, int, int]:
    try:
        header: object = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_fields)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        raise ParseRequestError(_INVALID_HEADER) from None
    if not isinstance(header, dict) or header.keys() != _HEADER_FIELDS:
        raise ParseRequestError(_INVALID_HEADER)
    fields = cast("dict[str, object]", header)
    attempt = fields["attempt_id"]
    digest = fields["source_sha256"]
    size = fields["source_size"]
    tokens = fields["max_content_tokens"]
    if (
        not isinstance(attempt, str)
        or not isinstance(digest, str)
        or re.fullmatch(r"[0-9a-f]{64}", digest) is None
        or type(size) is not int
        or not 1 <= size <= MAX_INPUT_BYTES
        or type(tokens) is not int
        or not 1 <= tokens <= 1024
        or fields["merge_peers"] is not False
    ):
        raise ParseRequestError(_INVALID_HEADER)
    try:
        attempt_id = UUID(attempt)
    except ValueError:
        raise ParseRequestError(_INVALID_HEADER) from None
    if str(attempt_id) != attempt:
        raise ParseRequestError(_INVALID_HEADER)
    return attempt_id, digest, size, tokens


def _unique_fields(pairs: list[tuple[str, object]]) -> dict[str, object]:
    fields: dict[str, object] = {}
    for name, value in pairs:
        if name in fields:
            raise ParseRequestError(_INVALID_HEADER)
        fields[name] = value
    return fields
