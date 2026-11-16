import asyncio
import json
import re
from math import isfinite
from struct import pack
from typing import cast
from uuid import UUID

import httpx

from inframeld_backend.indexing.infrastructure.errors.chroma_shard_storage_error import (
    ChromaShardStorageError,
)
from inframeld_backend.indexing.infrastructure.types.chroma_shard_record import (
    CHROMA_BATCH_BYTE_LIMIT,
    ChromaShardRecord,
)

_TENANT = "default_tenant"
_DATABASE = "default_database"
_COLLECTIONS = f"/api/v2/tenants/{_TENANT}/databases/{_DATABASE}/collections"
_SHARD_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{1,61}[A-Za-z0-9]")
_REQUEST_TIMEOUT_SECONDS = 30.0
_MAX_BATCH_RECORDS = 128
_MAX_BODY_BYTES = CHROMA_BATCH_BYTE_LIMIT


class ChromaShardStorage:
    """Access one trusted private Chroma service with explicit stored shard identities."""

    def __init__(self, origin: str) -> None:
        try:
            url = httpx.URL(origin)
        except httpx.InvalidURL:
            raise ChromaShardStorageError(
                "Chroma requires an explicit private HTTP origin."
            ) from None
        if (
            url.scheme not in {"http", "https"}
            or not url.host
            or url.userinfo
            or url.raw_path != b"/"
            or url.fragment
        ):
            raise ChromaShardStorageError("Chroma requires an explicit private HTTP origin.")
        self._origin = url

    async def create(self, shard_name: str) -> UUID:
        """Create the exact L2 name once. The caller retains uncertain creation."""
        self._require_name(shard_name)
        payload = await self._exchange(
            "POST",
            _COLLECTIONS,
            expected_status=200,
            body={
                "name": shard_name,
                "configuration": {"hnsw": {"space": "l2"}, "embedding_function": None},
                "get_or_create": False,
            },
            write=True,
        )
        try:
            return self._collection_id(payload, shard_name)
        except ValueError:
            raise ChromaShardStorageError(
                "The Chroma creation receipt does not identify the exact L2 shard.",
                write_outcome_unknown=True,
            ) from None

    async def inspect(self, shard_name: str, *, expected_id: UUID | None = None) -> UUID:
        """Verify a named shard and its optional saved UUID. Failed lookups raise."""
        self._require_name(shard_name)
        if expected_id is not None:
            self._require_id(expected_id)
        payload = await self._exchange("GET", f"{_COLLECTIONS}/{shard_name}", expected_status=200)
        try:
            found_id = self._collection_id(payload, shard_name)
            if expected_id is not None and found_id != expected_id:
                raise ValueError("The shard UUID changed.")
            return found_id
        except ValueError:
            raise ChromaShardStorageError("Chroma did not identify the exact L2 shard.") from None

    async def add(self, shard_id: UUID, records: tuple[ChromaShardRecord, ...]) -> None:
        """Submit explicit saved records once. Readback establishes individual outcomes."""
        self._require_id(shard_id)
        if type(records) is not tuple or not 1 <= len(records) <= _MAX_BATCH_RECORDS:
            raise ChromaShardStorageError("A Chroma add requires 1 to 128 saved records.")
        if any(type(record) is not ChromaShardRecord for record in records):
            raise ChromaShardStorageError("A Chroma add requires typed saved records.")
        self._require_source_size(sum(record.minimum_wire_bytes for record in records))

        ids = tuple(record.record_id for record in records)
        self._require_record_ids(ids)
        if len({len(record.vector) for record in records}) != 1:
            raise ChromaShardStorageError("A Chroma add requires consistent vector dimensions.")

        receipt = await self._exchange(
            "POST",
            f"{_COLLECTIONS}/{shard_id}/add",
            expected_status=201,
            body={
                "ids": ids,
                "embeddings": [record.float_values() for record in records],
                "metadatas": [dict(record.metadata) for record in records],
            },
            write=True,
        )
        if not isinstance(receipt, dict) or receipt:
            raise ChromaShardStorageError(
                "Chroma returned a malformed add receipt.", write_outcome_unknown=True
            )

    async def read(
        self, shard_id: UUID, record_ids: tuple[str, ...], *, dimensions: int
    ) -> dict[str, ChromaShardRecord]:
        """Return only observed requested IDs. A missing key denotes an absent record."""
        self._require_id(shard_id)
        self._require_record_ids(record_ids)
        if type(dimensions) is not int or not 1 <= dimensions <= 1536:
            raise ChromaShardStorageError("Chroma readback requires 1 to 1536 dimensions.")
        payload = await self._exchange(
            "POST",
            f"{_COLLECTIONS}/{shard_id}/get",
            expected_status=200,
            body={"ids": record_ids, "include": ["embeddings", "metadatas"]},
        )
        try:
            return self._records(payload, record_ids=record_ids, dimensions=dimensions)
        except (ValueError, OverflowError):
            raise ChromaShardStorageError("Chroma returned incoherent record readback.") from None

    async def _exchange(
        self,
        method: str,
        path: str,
        *,
        expected_status: int,
        body: dict[str, object] | None = None,
        write: bool = False,
    ) -> object:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + _REQUEST_TIMEOUT_SECONDS
        entered = False
        try:
            content: bytes | None = None
            headers = {"Accept": "application/json", "Accept-Encoding": "identity"}
            if body is not None:
                content = json.dumps(
                    body, ensure_ascii=False, allow_nan=False, separators=(",", ":")
                ).encode("utf-8")
                if len(content) > _MAX_BODY_BYTES:
                    raise ValueError("The request exceeds its byte limit.")
                headers["Content-Type"] = "application/json"
            if loop.time() >= deadline:
                raise TimeoutError

            async with (
                asyncio.timeout_at(deadline),
                httpx.AsyncClient(
                    base_url=self._origin,
                    transport=httpx.AsyncHTTPTransport(trust_env=False, retries=0),
                    trust_env=False,
                    follow_redirects=False,
                    timeout=None,
                ) as client,
            ):
                # The caller reconciles a write once request entry could have dispatched it.
                entered = True
                async with client.stream(
                    method, path, content=content, headers=headers
                ) as response:
                    if response.status_code != expected_status:
                        raise ValueError("Unexpected Chroma response status.")
                    raw = await self._read_body(response)
                payload: object = json.loads(
                    raw.decode("utf-8"),
                    object_pairs_hook=self._unique_object,
                    parse_float=self._finite_float,
                    parse_constant=self._finite_float,
                )
            if loop.time() >= deadline:
                raise TimeoutError
            return payload
        except (httpx.HTTPError, httpx.InvalidURL, TimeoutError, ValueError, RecursionError):
            if write and entered:
                raise ChromaShardStorageError(
                    "The Chroma write outcome is unknown.", write_outcome_unknown=True
                ) from None
            raise ChromaShardStorageError("The Chroma request did not complete safely.") from None

    @staticmethod
    async def _read_body(response: httpx.Response) -> bytearray:
        content_types = response.headers.get_list("Content-Type")
        encodings = response.headers.get_list("Content-Encoding")
        if (
            len(content_types) != 1
            or content_types[0].strip().lower()
            not in {"application/json", "application/json; charset=utf-8"}
            or [encoding.strip().lower() for encoding in encodings] not in ([], ["identity"])
        ):
            raise ValueError("Unexpected Chroma response media or encoding.")

        lengths = response.headers.get_list("Content-Length")
        length = None
        if lengths:
            if len(lengths) != 1 or re.fullmatch("[0-9]+", lengths[0]) is None:
                raise ValueError("Invalid Chroma response length.")
            length = int(lengths[0])
            if length > _MAX_BODY_BYTES:
                raise ValueError("The Chroma response exceeds its byte limit.")

        raw = bytearray()
        async for chunk in response.aiter_raw():
            if len(raw) + len(chunk) > _MAX_BODY_BYTES:
                raise ValueError("The Chroma response exceeds its byte limit.")
            raw.extend(chunk)
        if length is not None and len(raw) != length:
            raise ValueError("Unexpected Chroma response length.")
        return raw

    @staticmethod
    def _require_name(shard_name: str) -> None:
        if type(shard_name) is not str or _SHARD_NAME.fullmatch(shard_name) is None:
            raise ChromaShardStorageError("A Chroma shard requires a safe saved name.")

    @staticmethod
    def _require_id(shard_id: UUID) -> None:
        if type(shard_id) is not UUID:
            raise ChromaShardStorageError("A Chroma shard requires its parsed UUID.")

    @classmethod
    def _require_record_ids(cls, record_ids: tuple[str, ...]) -> None:
        if (
            type(record_ids) is not tuple
            or not 1 <= len(record_ids) <= _MAX_BATCH_RECORDS
            or any(type(record_id) is not str or not record_id for record_id in record_ids)
        ):
            raise ChromaShardStorageError("A Chroma batch requires 1 to 128 distinct record IDs.")
        cls._require_source_size(sum(map(len, record_ids)))
        if len(set(record_ids)) != len(record_ids):
            raise ChromaShardStorageError("A Chroma batch requires 1 to 128 distinct record IDs.")

    @staticmethod
    def _require_source_size(minimum_wire_bytes: int) -> None:
        if minimum_wire_bytes > _MAX_BODY_BYTES:
            raise ChromaShardStorageError("The Chroma request exceeds its byte limit.")

    @staticmethod
    def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
        value = dict(pairs)
        if len(value) != len(pairs):
            raise ValueError("Repeated Chroma JSON object key.")
        return value

    @staticmethod
    def _finite_float(text: str) -> float:
        value = float(text)
        if not isfinite(value):
            raise ValueError("Nonfinite Chroma JSON number.")
        return value

    @staticmethod
    def _object(value: object) -> dict[str, object]:
        if not isinstance(value, dict):
            raise ValueError("Expected a Chroma JSON object.")
        return cast(dict[str, object], value)

    @staticmethod
    def _array(value: object) -> list[object]:
        if not isinstance(value, list):
            raise ValueError("Expected a Chroma JSON array.")
        return cast(list[object], value)

    @classmethod
    def _collection_id(cls, payload: object, shard_name: str) -> UUID:
        collection = cls._object(payload)
        configuration = cls._object(collection.get("configuration_json"))
        hnsw = cls._object(configuration.get("hnsw"))
        raw_id = collection.get("id")
        if (
            collection.get("name") != shard_name
            or collection.get("tenant") != _TENANT
            or collection.get("database") != _DATABASE
            or hnsw.get("space") != "l2"
            or type(raw_id) is not str
        ):
            raise ValueError("Unexpected Chroma shard identity or configuration.")

        shard_id = UUID(raw_id)
        if str(shard_id) != raw_id:
            raise ValueError("Noncanonical Chroma UUID.")
        return shard_id

    @classmethod
    def _records(
        cls, payload: object, *, record_ids: tuple[str, ...], dimensions: int
    ) -> dict[str, ChromaShardRecord]:
        result = cls._object(payload)
        ids = cls._array(result.get("ids"))
        embeddings = cls._array(result.get("embeddings"))
        metadatas = cls._array(result.get("metadatas"))
        if not len(ids) == len(embeddings) == len(metadatas) <= len(record_ids):
            raise ValueError("Incoherent Chroma result columns.")

        requested = set(record_ids)
        records: dict[str, ChromaShardRecord] = {}
        for record_id, raw_embedding, raw_metadata in zip(ids, embeddings, metadatas, strict=True):
            if type(record_id) is not str or record_id not in requested or record_id in records:
                raise ValueError("Unexpected Chroma record ID.")
            embedding = cls._array(raw_embedding)
            if len(embedding) != dimensions or any(type(value) is not float for value in embedding):
                raise ValueError("Unexpected Chroma float32 vector shape.")

            metadata: list[tuple[str, str | bool | int | float]] = []
            for key, value in cls._object(raw_metadata).items():
                if not isinstance(value, str | bool | int | float):
                    raise ValueError("Unexpected Chroma metadata value.")
                metadata.append((key, value))
            records[record_id] = ChromaShardRecord(
                record_id=record_id,
                vector=pack(f"<{dimensions}f", *cast(list[float], embedding)),
                metadata=tuple(metadata),
            )
        return records
