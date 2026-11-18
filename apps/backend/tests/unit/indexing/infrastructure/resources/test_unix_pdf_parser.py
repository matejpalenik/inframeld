import asyncio
import json
import os
import socket
import sys
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast
from uuid import UUID

import pytest

from inframeld_backend.indexing.application.errors.pdf_parse_error import PdfParseError
from inframeld_backend.indexing.domain.value_objects.docling_processing_definition import (
    DoclingProcessingDefinition,
)
from inframeld_backend.indexing.infrastructure.resources.unix_pdf_parser import UnixPdfParser
from inframeld_backend.shared.application.value_objects.artifact_content_digest import (
    ArtifactContentDigest,
)

_SOURCE = b"%PDF-1.7\ncontrolled-example\n"
_DIGEST = ArtifactContentDigest.from_content(_SOURCE)
_ATTEMPT = UUID("509b7077-6b69-48b3-9bc1-59b4c398c852")
_UID = os.getuid() or 10001
_DEFINITION = DoclingProcessingDefinition(
    docling_slim_version="2.148.0",
    docling_core_version="2.106.0",
    asset_manifest_sha256="7ea9f3c967a7bc66d2501e466334e7aef46a639e01a11376888321e0f0a51d0e",
    max_content_tokens=8,
    merge_peers=False,
    repeat_table_header=True,
    ocr_enabled=False,
)
_CANONICAL = (
    '{"format":"inframeld-pdf-canonical-v1","blocks":['
    '{"kind":"text","pages":[1],"span":[0,3]},'
    '{"kind":"text","pages":[1,2],"span":[4,8]}],"text":"A🙂B\\nTail"}'
).encode()
_CANONICAL_DIGEST = ArtifactContentDigest.from_content(_CANONICAL)


@pytest.fixture
def parser_socket() -> Iterator[tuple[socket.socket, Path]]:
    with TemporaryDirectory(prefix="pdf-wire-") as scratch, socket.socket(socket.AF_UNIX) as server:
        path = Path(scratch) / "p"
        server.bind(os.fspath(path))
        server.listen(1)
        server.setblocking(False)
        yield server, path


@pytest.fixture
def observe_peer(monkeypatch: pytest.MonkeyPatch) -> None:
    if sys.platform == "linux" and os.getuid() != 0:
        return

    # Darwin or a root test runner cannot provide the supported Linux peer.
    def peer_uid(_connection: socket.socket) -> int:
        return _UID

    monkeypatch.setattr(UnixPdfParser, "_peer_uid", staticmethod(peer_uid))


def _frame(*, canonical: bytes = _CANONICAL, extra: bytes = b"", **changes: object) -> bytes:
    header = json.dumps(
        {
            "attempt_id": str(_ATTEMPT),
            "source_sha256": _DIGEST.value.hex(),
            "canonical_sha256": ArtifactContentDigest.from_content(canonical).value.hex(),
            "canonical_size": len(canonical),
            "chunk_ranges": [[1, 2], [4, 8]],
            **changes,
        }
    ).encode()
    return len(header).to_bytes(4, "big") + header + canonical + extra


async def _read(connection: socket.socket, count: int) -> bytes:
    loop = asyncio.get_running_loop()
    data = bytearray()
    while len(data) < count:
        piece = await loop.sock_recv(connection, count - len(data))
        assert piece, "The client closed before sending a complete request."
        data.extend(piece)
    return bytes(data)


async def _request(connection: socket.socket) -> dict[str, object]:
    count = int.from_bytes(await _read(connection, 4), "big")
    assert 0 < count <= 1024
    header = cast("dict[str, object]", json.loads(await _read(connection, count)))
    assert await _read(connection, len(_SOURCE)) == _SOURCE
    with pytest.raises(BlockingIOError):
        connection.recv(1)
    return header


async def _respond(server: socket.socket, reply: bytes) -> dict[str, object]:
    loop = asyncio.get_running_loop()
    connection, _ = await loop.sock_accept(server)
    with connection:
        header = await _request(connection)
        await loop.sock_sendall(connection, reply)
        return header


@pytest.mark.asyncio
@pytest.mark.usefixtures("observe_peer")
async def test_returns_a_verified_unpublished_result_without_half_closing(
    parser_socket: tuple[socket.socket, Path],
) -> None:
    server, path = parser_socket
    parser = UnixPdfParser(path, expected_peer_uid=_UID)
    async with asyncio.timeout(2), asyncio.TaskGroup() as tasks:
        response = tasks.create_task(_respond(server, _frame()))
        result = await parser.parse(
            _SOURCE,
            attempt_id=_ATTEMPT,
            source_digest=_DIGEST,
            definition=_DEFINITION,
            deadline=asyncio.get_running_loop().time() + 1,
        )
    assert response.result() == {
        "attempt_id": str(_ATTEMPT),
        "source_sha256": _DIGEST.value.hex(),
        "source_size": len(_SOURCE),
        "max_content_tokens": 8,
        "merge_peers": False,
    }
    assert (result.attempt_id, result.source_digest, result.canonical_digest) == (
        _ATTEMPT,
        _DIGEST,
        _CANONICAL_DIGEST,
    )
    assert result.canonical_bytes == _CANONICAL
    assert result.chunk_ranges == ((1, 2), (4, 8))
    assert "Tail" not in repr(result)


@pytest.mark.asyncio
async def test_refuses_wrong_sealed_input_or_unsupported_options_before_connecting(
    parser_socket: tuple[socket.socket, Path],
) -> None:
    server, path = parser_socket
    parser = UnixPdfParser(path, expected_peer_uid=_UID)
    for source, digest, definition in (
        (cast("bytes", bytearray(_SOURCE)), _DIGEST, _DEFINITION),
        (_SOURCE + b"other", _DIGEST, _DEFINITION),
        (_SOURCE, _DIGEST, replace(_DEFINITION, merge_peers=True)),
        (_SOURCE, _DIGEST, replace(_DEFINITION, repeat_table_header=False)),
        (b"x" * (25 * 1024**2 + 1), _DIGEST, _DEFINITION),
    ):
        with pytest.raises(PdfParseError) as failure:
            await parser.parse(
                source,
                attempt_id=_ATTEMPT,
                source_digest=digest,
                definition=definition,
                deadline=asyncio.get_running_loop().time() + 1,
            )
        assert failure.value.cleanup_confirmed
        with pytest.raises(BlockingIOError):
            server.accept()


@pytest.mark.asyncio
@pytest.mark.parametrize("observe_wrong_uid", [False, True])
async def test_sends_no_pdf_until_the_connected_peer_uid_is_verified(
    parser_socket: tuple[socket.socket, Path],
    monkeypatch: pytest.MonkeyPatch,
    observe_wrong_uid: bool,
) -> None:
    server, path = parser_socket
    loop = asyncio.get_running_loop()
    parser = UnixPdfParser(path, expected_peer_uid=_UID)

    def wrong_uid(_connection: socket.socket) -> int:
        return _UID + 1

    if observe_wrong_uid:
        monkeypatch.setattr(UnixPdfParser, "_peer_uid", staticmethod(wrong_uid))
    else:
        monkeypatch.delattr(socket, "SO_PEERCRED", raising=False)

    async def empty_request() -> bytes:
        connection, _ = await loop.sock_accept(server)
        with connection:
            return await loop.sock_recv(connection, 1)

    async with asyncio.timeout(2), asyncio.TaskGroup() as tasks:
        observed = tasks.create_task(empty_request())
        with pytest.raises(PdfParseError, match="peer") as failure:
            await parser.parse(
                _SOURCE,
                attempt_id=_ATTEMPT,
                source_digest=_DIGEST,
                definition=_DEFINITION,
                deadline=loop.time() + 1,
            )
    assert failure.value.cleanup_confirmed
    assert observed.result() == b""


@pytest.mark.asyncio
@pytest.mark.usefixtures("observe_peer")
@pytest.mark.parametrize(
    ("reply", "confirmed"),
    [
        (b"\0\0\0\0\x01", True),
        (b"\0\0\0\0\x02", True),
        (b"\0\0\0\0\x03", False),
        (b"\0\0\0\0\xff", False),
        (b"\0\0\0\0\x01x", False),
        ((64 * 1024 + 1).to_bytes(4, "big"), False),
        (_frame(canonical_size=32 * 1024**2), False),
        (_frame(attempt_id=str(UUID(int=0))), False),
        (_frame(source_sha256="0" * 64), False),
        (_frame(canonical_sha256="0" * 64), False),
        (_frame(extra=b"x"), False),
        (_frame()[:-1], False),
        (_frame(canonical=_CANONICAL.replace(b'"pages":[1]', b'"pages":[501]', 1)), False),
        (_frame(canonical=_CANONICAL.replace(b'"span":[0,3]', b'"span":[1,3]', 1)), False),
        (
            _frame(
                canonical=_CANONICAL.replace(b'"kind":"text"', b'"kind":"text","kind":"text"', 1)
            ),
            False,
        ),
        (_frame(canonical=b"\xff"), False),
        (_frame(chunk_ranges=[[3, 4]]), False),
        (_frame(chunk_ranges=[[1, 2], [1, 3]]), False),
    ],
)
async def test_only_returns_a_complete_validated_reply_or_expected_cleanup_state(
    parser_socket: tuple[socket.socket, Path], reply: bytes, confirmed: bool
) -> None:
    server, path = parser_socket
    parser = UnixPdfParser(path, expected_peer_uid=_UID)
    async with asyncio.timeout(2), asyncio.TaskGroup() as tasks:
        tasks.create_task(_respond(server, reply))
        with pytest.raises(PdfParseError) as failure:
            await parser.parse(
                _SOURCE,
                attempt_id=_ATTEMPT,
                source_digest=_DIGEST,
                definition=_DEFINITION,
                deadline=asyncio.get_running_loop().time() + 1,
            )
    assert failure.value.cleanup_confirmed is confirmed
    assert "controlled-example" not in str(failure.value)


@pytest.mark.asyncio
@pytest.mark.usefixtures("observe_peer")
@pytest.mark.parametrize("cancel", [False, True])
async def test_deadline_and_cancellation_close_the_connection_before_reply(
    parser_socket: tuple[socket.socket, Path], cancel: bool
) -> None:
    server, path = parser_socket
    loop = asyncio.get_running_loop()
    parser = UnixPdfParser(path, expected_peer_uid=_UID)
    async with asyncio.timeout(2):
        task = asyncio.create_task(
            parser.parse(
                _SOURCE,
                attempt_id=_ATTEMPT,
                source_digest=_DIGEST,
                definition=_DEFINITION,
                deadline=loop.time() + (1 if cancel else 0.15),
            )
        )
        try:
            connection, _ = await loop.sock_accept(server)
            with connection:
                await _request(connection)
                if cancel:
                    task.cancel()
                    with pytest.raises(asyncio.CancelledError):
                        await task
                else:
                    with pytest.raises(PdfParseError, match="deadline") as failure:
                        await task
                    assert not failure.value.cleanup_confirmed
                assert await loop.sock_recv(connection, 1) == b""
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
