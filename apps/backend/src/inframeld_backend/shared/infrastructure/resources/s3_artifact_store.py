from __future__ import annotations

import asyncio
import hashlib
from collections.abc import AsyncGenerator, Callable
from typing import TYPE_CHECKING, BinaryIO, override
from uuid import UUID

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from inframeld_backend.shared.application.dtos.artifact_attempt_dto import ArtifactAttemptDTO
from inframeld_backend.shared.application.dtos.artifact_listing_dto import ArtifactListingDTO
from inframeld_backend.shared.application.dtos.artifact_object_dto import ArtifactObjectDTO
from inframeld_backend.shared.application.dtos.artifact_scope_dto import ArtifactScopeDTO
from inframeld_backend.shared.application.errors.artifact_errors import (
    ArtifactCapacityError,
    ArtifactIntegrityError,
    ArtifactStoreUnavailableError,
    ArtifactWriteOutcomeUnknownError,
)
from inframeld_backend.shared.application.protocols.artifact_store import ArtifactStore
from inframeld_backend.shared.application.value_objects.artifact_attempt_id import ArtifactAttemptId
from inframeld_backend.shared.infrastructure.settings.artifact_storage_settings import (
    ArtifactStorageSettings,
)

if TYPE_CHECKING:
    from mypy_boto3_s3.client import S3Client
    from mypy_boto3_s3.type_defs import GetObjectOutputTypeDef, HeadObjectOutputTypeDef


class _ReadInterruptedError(ArtifactStoreUnavailableError):
    pass


class S3ArtifactStore(ArtifactStore):
    """Use one immutable scoped object per attempt with controlled SDK dispatch.

    SDK work runs off the event loop. At most two local calls remain in flight.
    A canceled or timed-out write reports uncertainty and stays tracked until
    close drains it. Callers must retain source bytes and durable pending-write
    evidence until reconciliation. This adapter supplies no completion barrier.
    """

    def __init__(
        self, settings: ArtifactStorageSettings, *, client: S3Client | None = None
    ) -> None:
        self._settings = settings
        self._client = (
            client
            if client is not None
            # Only S3 service stubs are installed. Unused factory overloads are untyped.
            else boto3.client(  # pyright: ignore[reportUnknownMemberType]
                "s3",
                endpoint_url=settings.endpoint_url,
                region_name=settings.region,
                aws_access_key_id=settings.access_key_id.get_secret_value(),
                aws_secret_access_key=settings.secret_access_key.get_secret_value(),
                verify=str(settings.ca_bundle) if settings.ca_bundle is not None else True,
                config=Config(
                    signature_version="s3v4",
                    s3={
                        "addressing_style": settings.addressing_style.value,
                        "payload_signing_enabled": True,
                    },
                    retries={"total_max_attempts": 1, "mode": "standard"},
                    connect_timeout=settings.connect_timeout_seconds,
                    read_timeout=settings.read_timeout_seconds,
                    max_pool_connections=2,
                    request_checksum_calculation="when_required",
                    response_checksum_validation="when_required",
                ),
            )
        )
        self._pending: set[asyncio.Task[None]] = set()
        self._closed = False
        self._closing: asyncio.Task[None] | None = None

    @override
    async def put(self, attempt: ArtifactAttemptDTO, content: BinaryIO) -> None:
        self._require_attempt(attempt)

        def upload() -> None:
            content.seek(0)
            digest = hashlib.sha256()
            length = 0
            while chunk := content.read(65536):
                length += len(chunk)
                if length > attempt.length:
                    raise ArtifactIntegrityError(
                        "Upload bytes exceed the original sealed expectation."
                    )
                digest.update(chunk)
            if length != attempt.length or digest.digest() != attempt.digest.value:
                raise ArtifactIntegrityError(
                    "Upload bytes differ from the original sealed expectation."
                )
            content.seek(0)
            self._client.put_object(
                Bucket=self._settings.bucket,
                Key=self._key(attempt.scope, attempt.attempt_id),
                Body=content,
                ContentLength=attempt.length,
                IfNoneMatch="*",
            )

        await self._call(upload, mutating=True)

    @override
    async def read(self, attempt: ArtifactAttemptDTO) -> AsyncGenerator[bytes]:
        self._require_attempt(attempt)
        deadline = asyncio.get_running_loop().time() + self._settings.operation_timeout_seconds

        def close_late_response(response: GetObjectOutputTypeDef | None) -> None:
            if response is not None:
                response["Body"].close()

        response = await self._call(
            lambda: self._client.get_object(
                Bucket=self._settings.bucket, Key=self._key(attempt.scope, attempt.attempt_id)
            ),
            mutating=False,
            cleanup=close_late_response,
            deadline=deadline,
        )
        body = response["Body"]
        deferred_close = False
        length = 0
        try:
            while True:
                try:
                    chunk = await self._call(
                        lambda: body.read(65536),
                        mutating=False,
                        cleanup=lambda _: body.close(),
                        deadline=deadline,
                    )
                except (_ReadInterruptedError, asyncio.CancelledError):
                    deferred_close = True
                    raise
                if not chunk:
                    break
                length += len(chunk)
                if length > attempt.length:
                    raise ArtifactIntegrityError(
                        "Stored bytes exceed the original sealed expectation."
                    )
                yield chunk
        finally:
            if not deferred_close:
                body.close()

    @override
    async def head(
        self, scope: ArtifactScopeDTO, attempt_id: ArtifactAttemptId
    ) -> ArtifactObjectDTO | None:
        def observe() -> HeadObjectOutputTypeDef | None:
            try:
                return self._client.head_object(
                    Bucket=self._settings.bucket, Key=self._key(scope, attempt_id)
                )
            except ClientError as error:
                # ClientError is an SDK serialization boundary, never application data.
                if (
                    error.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound")
                    and error.response.get("ResponseMetadata", {}).get("HTTPStatusCode") == 404
                ):
                    return None
                raise

        response = await self._call(observe, mutating=False)
        if response is None:
            return None
        length = response.get("ContentLength")
        if type(length) is not int or not 0 <= length <= self._settings.max_object_bytes:
            raise ArtifactIntegrityError("Storage returned invalid object length metadata.")
        return ArtifactObjectDTO(attempt_id, length)

    @override
    async def list(
        self, scope: ArtifactScopeDTO, *, after: ArtifactAttemptId | None, limit: int
    ) -> ArtifactListingDTO:
        if type(limit) is not int or not 1 <= limit <= self._settings.list_page_size:
            raise ValueError("The object listing exceeds its configured page bound.")
        prefix = self._prefix(scope)
        if after is None:
            response = await self._call(
                lambda: self._client.list_objects_v2(
                    Bucket=self._settings.bucket, Prefix=prefix, MaxKeys=limit
                ),
                mutating=False,
            )
        else:
            response = await self._call(
                lambda: self._client.list_objects_v2(
                    Bucket=self._settings.bucket,
                    Prefix=prefix,
                    MaxKeys=limit,
                    StartAfter=self._key(scope, after),
                ),
                mutating=False,
            )
        entries = response.get("Contents", [])
        if len(entries) > limit:
            raise ArtifactIntegrityError("Storage exceeded the requested listing bound.")
        objects: list[ArtifactObjectDTO] = []
        previous = after.value.hex if after is not None else ""
        for entry in entries:
            key, length = entry.get("Key"), entry.get("Size")
            if (
                key is None
                or not key.startswith(prefix)
                or type(length) is not int
                or not 0 <= length <= self._settings.max_object_bytes
            ):
                raise ArtifactIntegrityError("Storage listed an invalid or foreign object.")
            suffix = key.removeprefix(prefix)
            try:
                identity = UUID(hex=suffix)
            except ValueError:
                raise ArtifactIntegrityError(
                    "Storage listed an unknown physical identity."
                ) from None
            if suffix != identity.hex or suffix <= previous:
                raise ArtifactIntegrityError("Storage listed an invalid identity ordering.")
            objects.append(ArtifactObjectDTO(ArtifactAttemptId(identity), length))
            previous = suffix
        truncated = response.get("IsTruncated", False)
        if truncated and not objects:
            raise ArtifactIntegrityError("Storage cannot continue an empty truncated inventory.")
        return ArtifactListingDTO(tuple(objects), objects[-1].attempt_id if truncated else None)

    @override
    async def delete(self, scope: ArtifactScopeDTO, attempt_id: ArtifactAttemptId) -> None:
        await self._call(
            lambda: self._client.delete_object(
                Bucket=self._settings.bucket, Key=self._key(scope, attempt_id)
            ),
            mutating=True,
        )

    async def close(self) -> None:
        """Drain native calls before pool closure, retaining one owner across cancellation.

        Canceling a waiter leaves shutdown running. Repeated close waits for that
        same drain and does not close the pool again or redispatch storage work.
        """
        if self._closing is None:
            self._closed = True
            self._closing = asyncio.create_task(self._drain_and_close())
        await asyncio.shield(self._closing)

    async def _drain_and_close(self) -> None:
        """Wait for owned SDK threads before closing the client they may still use."""
        await asyncio.gather(*tuple(self._pending), return_exceptions=True)
        self._client.close()

    def _require_attempt(self, attempt: ArtifactAttemptDTO) -> None:
        """Enforce the sealed artifact length and configured capacity before storage work."""
        if type(attempt.length) is not int or attempt.length < 0:
            raise ArtifactIntegrityError("The original sealed length is invalid.")
        if attempt.length > self._settings.max_object_bytes:
            raise ArtifactCapacityError("The artifact exceeds its configured storage bound.")

    @staticmethod
    def _prefix(scope: ArtifactScopeDTO) -> str:
        """Keep artifact keys scoped to the installation, Organization and Project."""
        return f"artifacts/{scope.installation_id.value.hex}/{scope.organization_id.value.hex}/{scope.project_id.value.hex}/"

    @staticmethod
    def _key(scope: ArtifactScopeDTO, attempt_id: ArtifactAttemptId) -> str:
        return S3ArtifactStore._prefix(scope) + attempt_id.value.hex

    async def _call[T](
        self,
        action: Callable[[], T],
        *,
        mutating: bool,
        cleanup: Callable[[T | None], None] | None = None,
        deadline: float | None = None,
    ) -> T:
        """Bound the SDK wait while retaining ownership of a thread that may still finish.

        A timed-out write keeps its uncertain-outcome meaning.
        """
        if self._closed or len(self._pending) >= 2:
            raise ArtifactStoreUnavailableError(
                "The private storage client is unavailable or busy."
            )
        budget = self._settings.operation_timeout_seconds
        if deadline is not None:
            budget = min(budget, deadline - asyncio.get_running_loop().time())
        if budget <= 0:
            if cleanup is not None:
                cleanup(None)
            raise _ReadInterruptedError("The original storage observation deadline expired.")
        result: list[T] = []
        abandoned = False

        def perform() -> None:
            result.append(action())

        task = asyncio.create_task(asyncio.to_thread(perform))
        self._pending.add(task)

        def finished(done: asyncio.Task[None]) -> None:
            self._pending.discard(done)
            if not done.cancelled():
                done.exception()
            if abandoned and cleanup is not None:
                cleanup(result[0] if result else None)

        task.add_done_callback(finished)
        try:
            async with asyncio.timeout(budget):
                await asyncio.shield(task)
        except (TimeoutError, asyncio.CancelledError) as error:
            abandoned = True
            if task.done() and cleanup is not None:
                cleanup(result[0] if result else None)
            if mutating:
                raise ArtifactWriteOutcomeUnknownError(
                    "The original storage write outcome is unknown."
                ) from None
            if isinstance(error, asyncio.CancelledError):
                raise
            raise _ReadInterruptedError("The storage observation could not be confirmed.") from None
        except (BotoCoreError, ClientError, OSError):
            if mutating:
                raise ArtifactWriteOutcomeUnknownError(
                    "The original storage write outcome is unknown."
                ) from None
            raise ArtifactStoreUnavailableError(
                "The storage observation could not be confirmed."
            ) from None
        return result[0]
