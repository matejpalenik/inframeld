import asyncio
import json
from collections.abc import AsyncIterator, Callable
from dataclasses import replace
from struct import pack
from typing import cast, override
from uuid import UUID

import httpx
import pytest

from inframeld_backend.indexing.infrastructure.errors.chroma_shard_storage_error import (
    ChromaShardStorageError,
)
from inframeld_backend.indexing.infrastructure.resources import chroma_shard_storage
from inframeld_backend.indexing.infrastructure.resources.chroma_shard_storage import (
    ChromaShardStorage,
)
from inframeld_backend.indexing.infrastructure.types import chroma_shard_record
from inframeld_backend.indexing.infrastructure.types.chroma_shard_record import ChromaShardRecord

_ORIGIN = "http://chroma:8000"
_COLLECTIONS = "/api/v2/tenants/default_tenant/databases/default_database/collections"
_NAME = "inframeld-fixture-shard"
_ID = UUID("4e338fc7-9aed-41d9-b387-b85f222b9890")
_RECORD = ChromaShardRecord(
    record_id="first",
    vector=pack("<3f", -0.0, 0.1, 1.0),
    metadata=(("scope", "support"), ("generation", "g1"), ("version", 1)),
)


def _respond(
    monkeypatch: pytest.MonkeyPatch, handler: Callable[[httpx.Request], httpx.Response]
) -> None:
    async def receive(
        _transport: httpx.AsyncHTTPTransport, request: httpx.Request
    ) -> httpx.Response:
        return handler(request)

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", receive)


def _response(
    status: int, content: bytes, *, headers: dict[str, str] | None = None
) -> httpx.Response:
    return httpx.Response(
        status,
        headers={"Content-Type": "application/json", **(headers or {})},
        stream=httpx.ByteStream(content),
    )


def _collection(
    *,
    id: str = str(_ID),
    name: str = _NAME,
    space: str = "l2",
    tenant: str = "default_tenant",
    database: str = "default_database",
) -> bytes:
    return json.dumps(
        {
            "id": id,
            "name": name,
            "tenant": tenant,
            "database": database,
            "configuration_json": {"hnsw": {"space": space}},
        }
    ).encode()


@pytest.mark.asyncio
async def test_create_and_inspect_bind_the_exact_l2_shard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[httpx.Request] = []

    def peer(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return _response(200, _collection())

    _respond(monkeypatch, peer)
    storage = ChromaShardStorage(_ORIGIN)

    assert await storage.create(_NAME) == _ID
    assert await storage.inspect(_NAME, expected_id=_ID) == _ID
    assert [(req.method, str(req.url)) for req in requests] == [
        ("POST", _ORIGIN + _COLLECTIONS),
        ("GET", _ORIGIN + _COLLECTIONS + "/" + _NAME),
    ]
    assert json.loads(requests[0].content) == {
        "name": _NAME,
        "configuration": {"hnsw": {"space": "l2"}, "embedding_function": None},
        "get_or_create": False,
    }
    assert requests[0].headers["Content-Type"] == "application/json"
    assert all(req.headers["Accept-Encoding"] == "identity" for req in requests)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "content",
    [
        _collection(id=str(_ID).upper()),
        _collection(id=str(UUID(int=2))),
        _collection(name="unexpected"),
        _collection(space="cosine"),
        _collection(tenant="other"),
        _collection(database="other"),
    ],
)
async def test_inspect_rejects_an_inconsistent_shard(
    monkeypatch: pytest.MonkeyPatch, content: bytes
) -> None:
    _respond(monkeypatch, lambda _: _response(200, content))

    with pytest.raises(ChromaShardStorageError) as failure:
        await ChromaShardStorage(_ORIGIN).inspect(_NAME, expected_id=_ID)

    assert not failure.value.write_outcome_unknown


@pytest.mark.asyncio
async def test_inspect_fails_closed_on_unqualified_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _respond(monkeypatch, lambda _: _response(404, b'{"error":"NotFound"}'))
    with pytest.raises(ChromaShardStorageError) as failure:
        await ChromaShardStorage(_ORIGIN).inspect(_NAME, expected_id=_ID)
    assert not failure.value.write_outcome_unknown


@pytest.mark.asyncio
async def test_create_receipt_for_wrong_database_keeps_write_uncertain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _respond(monkeypatch, lambda _: _response(200, _collection(database="other")))
    with pytest.raises(ChromaShardStorageError) as failure:
        await ChromaShardStorage(_ORIGIN).create(_NAME)
    assert failure.value.write_outcome_unknown


@pytest.mark.asyncio
async def test_add_sends_explicit_vectors_and_read_returns_only_observed_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[httpx.Request] = []

    def peer(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/add"):
            return _response(201, b"{}")
        return _response(
            200,
            b'{"ids":["second","first"],"embeddings":[[1.0,2.0,3.0],[-0.0,0.1,1.0]],'
            b'"metadatas":[{"scope":"support"},{"generation":"g1","version":1,"scope":"support"}]}',
        )

    _respond(monkeypatch, peer)
    second = ChromaShardRecord(
        record_id="second",
        vector=pack("<3f", 1.0, 2.0, 3.0),
        metadata=(("scope", "support"),),
    )
    storage = ChromaShardStorage(_ORIGIN)

    await storage.add(_ID, (_RECORD, second))
    found = await storage.read(_ID, ("first", "missing", "second"), dimensions=3)

    assert found == {"first": _RECORD, "second": second}
    assert found["first"].vector[:4] == b"\x00\x00\x00\x80"
    assert json.loads(requests[0].content) == {
        "ids": ["first", "second"],
        "embeddings": [[-0.0, 0.10000000149011612, 1.0], [1.0, 2.0, 3.0]],
        "metadatas": [{"scope": "support", "generation": "g1", "version": 1}, {"scope": "support"}],
    }
    assert json.loads(requests[1].content) == {
        "ids": ["first", "missing", "second"],
        "include": ["embeddings", "metadatas"],
    }
    assert [(req.method, req.url.path) for req in requests] == [
        ("POST", f"{_COLLECTIONS}/{_ID}/add"),
        ("POST", f"{_COLLECTIONS}/{_ID}/get"),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        b'{"ids":["other"],"embeddings":[[1.0,2.0,3.0]],"metadatas":[{}]}',
        b'{"ids":["first","first"],"embeddings":[[1.0],[2.0]],"metadatas":[{},{}]}',
        b'{"ids":["first"],"embeddings":[],"metadatas":[{}]}',
        b'{"ids":["first"],"embeddings":[[1.0]],"metadatas":[{}]}',
        b'{"ids":["first"],"embeddings":[[1,false,3.0]],"metadatas":[{}]}',
        b'{"ids":["first"],"embeddings":[[1.0,1e400,3.0]],"metadatas":[{}]}',
        b'{"ids":["first"],"embeddings":[[1.0,1e50,3.0]],"metadatas":[{}]}',
        b'{"ids":["first"],"embeddings":[[1.0,2.0,3.0]],"metadatas":[{"a":1,"a":2}]}',
        b'{"ids":["first"],"embeddings":[[1.0,2.0,3.0]],"metadatas":[{"a":[] }]}',
        b'{"ids":["first"],"embeddings":[[1.0,2.0,3.0]],"metadatas":[null]}',
    ],
)
async def test_read_rejects_malformed_identity_shape_and_values(
    monkeypatch: pytest.MonkeyPatch, body: bytes
) -> None:
    _respond(monkeypatch, lambda _: _response(200, body))
    with pytest.raises(ChromaShardStorageError) as failure:
        await ChromaShardStorage(_ORIGIN).read(_ID, ("first",), dimensions=3)
    assert not failure.value.write_outcome_unknown


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status, body, headers",
    [
        (307, b"{}", {"Location": "http://unapproved.test/add"}),
        (307, b"{}", {"Location": "http://["}),
        (503, b'{"private":"never-echo-this"}', {}),
        (201, b"invalid-json", {}),
        (201, b"null", {}),
        (201, b'{"accepted":true}', {}),
        (201, b"{}", {"Content-Encoding": "gzip"}),
        (201, b"{}", {"Content-Type": "text/html"}),
        (201, b"{}", {"Content-Length": "3"}),
    ],
)
async def test_inconclusive_add_never_redirects_retries_or_exposes_response(
    monkeypatch: pytest.MonkeyPatch, status: int, body: bytes, headers: dict[str, str]
) -> None:
    requests: list[httpx.Request] = []

    def peer(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return _response(status, body, headers=headers)

    monkeypatch.setenv("HTTP_PROXY", "http://unapproved.test:1234")
    monkeypatch.setenv("ALL_PROXY", "http://unapproved.test:1234")
    _respond(monkeypatch, peer)

    with pytest.raises(ChromaShardStorageError) as failure:
        await ChromaShardStorage(_ORIGIN).add(_ID, (_RECORD,))

    assert failure.value.write_outcome_unknown
    assert "never-echo-this" not in str(failure.value)
    assert [str(request.url) for request in requests] == [f"{_ORIGIN}{_COLLECTIONS}/{_ID}/add"]


@pytest.mark.asyncio
async def test_transport_loss_after_start_keeps_write_uncertain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0

    def peer(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ReadError("private transport detail", request=request)

    _respond(monkeypatch, peer)
    with pytest.raises(ChromaShardStorageError) as failure:
        await ChromaShardStorage(_ORIGIN).create(_NAME)
    assert failure.value.write_outcome_unknown
    assert "private transport detail" not in str(failure.value)
    assert attempts == 1


@pytest.mark.asyncio
async def test_invalid_inputs_reject_before_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    def unexpected(_: httpx.Request) -> httpx.Response:
        pytest.fail("A locally invalid request reached the transport.")

    _respond(monkeypatch, unexpected)
    storage = ChromaShardStorage(_ORIGIN)
    for operation in (
        lambda: storage.create("../other"),
        lambda: storage.add(cast(UUID, str(_ID)), (_RECORD,)),
        lambda: storage.add(_ID, (_RECORD, _RECORD)),
        lambda: storage.add(_ID, tuple(replace(_RECORD, record_id=str(i)) for i in range(129))),
        lambda: storage.read(_ID, ("first",), dimensions=1537),
    ):
        with pytest.raises(ChromaShardStorageError) as failure:
            await operation()
        assert not failure.value.write_outcome_unknown


@pytest.mark.asyncio
@pytest.mark.parametrize("value", ["\x00" * 64, "🚀" * 64])
async def test_exact_wire_byte_caps_apply_after_encoding(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setattr(chroma_shard_storage, "_MAX_BODY_BYTES", 256, raising=False)
    attempts = 0

    def peer(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return _response(201, b" " * 257)

    _respond(monkeypatch, peer)
    storage = ChromaShardStorage(_ORIGIN)
    too_large = replace(_RECORD, metadata=(("payload", value),))
    with pytest.raises(ChromaShardStorageError) as oversized_request:
        await storage.add(_ID, (too_large,))
    assert not oversized_request.value.write_outcome_unknown
    assert attempts == 0

    with pytest.raises(ChromaShardStorageError) as oversized_response:
        await storage.add(_ID, (_RECORD,))
    assert oversized_response.value.write_outcome_unknown
    assert attempts == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("write", [True, False], ids=["add", "read"])
async def test_large_batch_fields_are_rejected_before_json_encoding(
    monkeypatch: pytest.MonkeyPatch, write: bool
) -> None:
    monkeypatch.setattr(chroma_shard_storage, "_MAX_BODY_BYTES", 256)
    oversized_records = (
        replace(_RECORD, metadata=(("body", "a" * 125),)),
        replace(_RECORD, record_id="second", metadata=(("body", "b" * 125),)),
    )
    storage = ChromaShardStorage(_ORIGIN)

    def unexpected_encoding(*_args: object, **_kwargs: object) -> str:
        pytest.fail("An oversized batch reached JSON encoding.")

    monkeypatch.setattr(chroma_shard_storage.json, "dumps", unexpected_encoding)
    with pytest.raises(ChromaShardStorageError) as failure:
        if write:
            await storage.add(_ID, oversized_records)
        else:
            await storage.read(_ID, ("a" * 129, "b" * 129), dimensions=3)
    assert not failure.value.write_outcome_unknown


def test_large_metadata_is_rejected_before_copy_and_sort(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(chroma_shard_record, "CHROMA_BATCH_BYTE_LIMIT", 64, raising=False)

    def unexpected_sort(*_args: object, **_kwargs: object) -> object:
        pytest.fail("Oversized metadata reached sorting.")

    monkeypatch.setattr(chroma_shard_record, "sorted", unexpected_sort, raising=False)
    with pytest.raises(ValueError):
        replace(_RECORD, metadata=(("a", "x" * 30), ("b", "y" * 30)))


class _PendingResponse(httpx.AsyncByteStream):
    def __init__(self) -> None:
        self.pending = asyncio.Event()
        self.closed = False

    @override
    async def __aiter__(self) -> AsyncIterator[bytes]:
        self.pending.set()
        await asyncio.Event().wait()
        yield b"{}"

    @override
    async def aclose(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_absolute_request_deadline_covers_response_stream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(chroma_shard_storage, "_REQUEST_TIMEOUT_SECONDS", 0.02)
    stream = _PendingResponse()
    _respond(
        monkeypatch,
        lambda _: httpx.Response(201, headers={"Content-Type": "application/json"}, stream=stream),
    )

    async with asyncio.timeout(1):
        with pytest.raises(ChromaShardStorageError) as failure:
            await ChromaShardStorage(_ORIGIN).add(_ID, (_RECORD,))

    assert failure.value.write_outcome_unknown and stream.pending.is_set() and stream.closed


@pytest.mark.asyncio
async def test_caller_cancellation_propagates_and_closes_the_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stream = _PendingResponse()
    _respond(
        monkeypatch,
        lambda _: httpx.Response(201, headers={"Content-Type": "application/json"}, stream=stream),
    )

    async with asyncio.timeout(1):
        task = asyncio.create_task(ChromaShardStorage(_ORIGIN).add(_ID, (_RECORD,)))
        try:
            await stream.pending.wait()
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

    assert stream.closed


def test_record_comparison_preserves_bits_and_scalar_types() -> None:
    assert replace(_RECORD, vector=pack("<3f", 0.0, 0.1, 1.0)) != _RECORD
    assert (
        replace(_RECORD, metadata=(("scope", "support"), ("generation", "g1"), ("version", True)))
        != _RECORD
    )
    assert (
        replace(_RECORD, metadata=(("scope", "support"), ("generation", "g1"), ("version", 1.0)))
        != _RECORD
    )
    assert replace(_RECORD, metadata=_RECORD.metadata[::-1]) == _RECORD


@pytest.mark.parametrize("value", [float("nan"), float("inf")])
def test_record_rejects_nonfinite_saved_f32(value: float) -> None:
    with pytest.raises(ValueError):
        replace(_RECORD, vector=pack("<f", value))
