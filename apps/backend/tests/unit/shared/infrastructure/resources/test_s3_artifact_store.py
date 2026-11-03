import asyncio
import hashlib
import threading
from collections.abc import Iterator
from io import BytesIO
from pathlib import Path
from typing import BinaryIO, cast
from uuid import UUID

import boto3
import pytest
from botocore.config import Config
from botocore.exceptions import EndpointConnectionError
from botocore.response import StreamingBody
from botocore.stub import ANY, Stubber
from mypy_boto3_s3.client import S3Client
from mypy_boto3_s3.type_defs import GetObjectOutputTypeDef, PutObjectOutputTypeDef

from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.dtos.artifact_attempt_dto import ArtifactAttemptDTO
from inframeld_backend.shared.application.dtos.artifact_scope_dto import ArtifactScopeDTO
from inframeld_backend.shared.application.errors.artifact_errors import (
    ArtifactIntegrityError,
    ArtifactStoreUnavailableError,
    ArtifactWriteOutcomeUnknownError,
)
from inframeld_backend.shared.application.value_objects.artifact_attempt_id import ArtifactAttemptId
from inframeld_backend.shared.application.value_objects.artifact_content_digest import (
    ArtifactContentDigest,
)
from inframeld_backend.shared.application.value_objects.artifact_id import ArtifactId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.infrastructure.resources.s3_artifact_store import S3ArtifactStore
from inframeld_backend.shared.infrastructure.settings.artifact_storage_settings import (
    ArtifactStorageSettings,
)

SCOPE = ArtifactScopeDTO(
    InstallationId(UUID(int=1)), OrganizationId(UUID(int=2)), ProjectId(UUID(int=3))
)
ATTEMPT = ArtifactAttemptDTO(
    ArtifactId(UUID(int=4)),
    ArtifactAttemptId(UUID(int=5)),
    SCOPE,
    3,
    ArtifactContentDigest(hashlib.sha256(b"abc").digest()),
)
PREFIX = "artifacts/00000000000000000000000000000001/00000000000000000000000000000002/00000000000000000000000000000003/"
KEY = PREFIX + "00000000000000000000000000000005"


def settings(tmp_path: Path, **changes: object) -> ArtifactStorageSettings:
    data: dict[str, object] = {
        "endpoint_url": "https://storage.test",
        "bucket": "private-artifacts",
        "access_key_id": "fixture-access",
        "secret_access_key": "fixture-secret",
    }
    data.update(changes)
    return ArtifactStorageSettings.model_validate(data)


@pytest.fixture
def client() -> Iterator[S3Client]:
    # The factory declares unused service overloads outside our installed S3 stubs.
    sdk = boto3.client(  # pyright: ignore[reportUnknownMemberType]
        "s3",
        endpoint_url="https://storage.test",
        region_name="us-east-1",
        aws_access_key_id="fixture-access",
        aws_secret_access_key="fixture-secret",
    )
    try:
        yield sdk
    finally:
        sdk.close()


@pytest.mark.asyncio
async def test_exact_scoped_put_and_streamed_readback_use_original_identity(
    tmp_path: Path, client: S3Client
) -> None:
    store = S3ArtifactStore(settings(tmp_path), client=client)
    body = StreamingBody(BytesIO(b"abc"), 3)
    with Stubber(client) as stub:
        stub.add_response(
            "put_object",
            {},
            {
                "Bucket": "private-artifacts",
                "Key": KEY,
                "Body": ANY,
                "ContentLength": 3,
                "IfNoneMatch": "*",
            },
        )
        stub.add_response(
            "get_object",
            {"Body": body, "ContentLength": 3},
            {"Bucket": "private-artifacts", "Key": KEY},
        )
        await store.put(ATTEMPT, BytesIO(b"abc"))
        assert b"".join([part async for part in store.read(ATTEMPT)]) == b"abc"
        stub.assert_no_pending_responses()
    await store.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("content", [b"ab", b"abcd", b"xyz"])
async def test_wrong_put_content_is_rejected_before_storage_effect(
    tmp_path: Path, client: S3Client, content: bytes
) -> None:
    store = S3ArtifactStore(settings(tmp_path), client=client)
    with Stubber(client), pytest.raises(ArtifactIntegrityError):
        await store.put(ATTEMPT, BytesIO(content))
    await store.close()


@pytest.mark.asyncio
async def test_head_absence_is_distinct_from_denied_observation(
    tmp_path: Path, client: S3Client
) -> None:
    store = S3ArtifactStore(settings(tmp_path), client=client)
    request = {"Bucket": "private-artifacts", "Key": KEY}
    with Stubber(client) as stub:
        stub.add_client_error("head_object", "404", http_status_code=404, expected_params=request)
        stub.add_client_error(
            "head_object",
            "AccessDenied",
            service_message="private-server-secret",
            http_status_code=403,
            expected_params=request,
        )
        assert await store.head(SCOPE, ATTEMPT.attempt_id) is None
        with pytest.raises(ArtifactStoreUnavailableError) as failure:
            await store.head(SCOPE, ATTEMPT.attempt_id)
        assert "private-server-secret" not in str(failure.value)
    await store.close()


@pytest.mark.asyncio
async def test_bounded_listing_returns_scoped_identity_cursor_and_exact_delete(
    tmp_path: Path, client: S3Client
) -> None:
    store = S3ArtifactStore(settings(tmp_path), client=client)
    with Stubber(client) as stub:
        stub.add_response(
            "list_objects_v2",
            {"Contents": [{"Key": KEY, "Size": 3}], "IsTruncated": True},
            {"Bucket": "private-artifacts", "Prefix": PREFIX, "MaxKeys": 1},
        )
        stub.add_response("delete_object", {}, {"Bucket": "private-artifacts", "Key": KEY})
        result = await store.list(SCOPE, after=None, limit=1)
        assert result.after == ATTEMPT.attempt_id
        assert (
            len(result.objects) == 1
            and result.objects[0].attempt_id == ATTEMPT.attempt_id
            and result.objects[0].length == 3
        )
        await store.delete(SCOPE, ATTEMPT.attempt_id)
    await store.close()


@pytest.mark.asyncio
async def test_foreign_listed_key_never_becomes_a_cleanup_target(
    tmp_path: Path, client: S3Client
) -> None:
    store = S3ArtifactStore(settings(tmp_path), client=client)
    with Stubber(client) as stub:
        stub.add_response(
            "list_objects_v2",
            {"Contents": [{"Key": "other-scope/object", "Size": 3}], "IsTruncated": False},
            {"Bucket": "private-artifacts", "Prefix": PREFIX, "MaxKeys": 1},
        )
        with pytest.raises(ArtifactIntegrityError):
            await store.list(SCOPE, after=None, limit=1)
    await store.close()


@pytest.mark.asyncio
async def test_failed_delete_keeps_outcome_unknown_instead_of_confirming_cleanup(
    tmp_path: Path, client: S3Client
) -> None:
    store = S3ArtifactStore(settings(tmp_path), client=client)
    with Stubber(client) as stub:
        stub.add_client_error(
            "delete_object",
            "InternalError",
            service_message="private-server-secret",
            http_status_code=500,
            expected_params={"Bucket": "private-artifacts", "Key": KEY},
        )
        with pytest.raises(ArtifactWriteOutcomeUnknownError) as failure:
            await store.delete(SCOPE, ATTEMPT.attempt_id)
        assert "private-server-secret" not in str(failure.value)
    await store.close()


@pytest.mark.asyncio
async def test_transport_failure_has_one_actual_sdk_send_without_implicit_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Preserve the SDK factory while replacing the module entry point.
    original = boto3.client  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    sends: list[int] = []

    def failed_send(**kwargs: object) -> None:
        sends.append(1)
        raise EndpointConnectionError(endpoint_url="https://storage.test")

    def configured_client(
        service_name: str,
        *,
        endpoint_url: str,
        region_name: str,
        aws_access_key_id: str,
        aws_secret_access_key: str,
        verify: bool | str,
        config: Config,
    ) -> S3Client:
        sdk = original(
            "s3",
            endpoint_url=endpoint_url,
            region_name=region_name,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            verify=verify,
            config=config,
        )
        sdk.meta.events.register("before-send.s3.PutObject", failed_send)
        return sdk

    monkeypatch.setattr(boto3, "client", configured_client)
    store = S3ArtifactStore(settings(tmp_path))
    try:
        with pytest.raises(ArtifactWriteOutcomeUnknownError):
            await store.put(ATTEMPT, BytesIO(b"abc"))
        assert sends == [1]
    finally:
        await store.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("interruption", ["timeout", "cancel"])
async def test_interrupted_offloop_put_keeps_original_unknown_and_drains_without_retry(
    tmp_path: Path, client: S3Client, monkeypatch: pytest.MonkeyPatch, interruption: str
) -> None:
    entered = threading.Event()
    release = threading.Event()
    stored: list[bytes] = []
    sends: list[int] = []

    def delayed_put(
        *, Bucket: str, Key: str, Body: BinaryIO, ContentLength: int, IfNoneMatch: str
    ) -> PutObjectOutputTypeDef:
        assert (
            Bucket == "private-artifacts"
            and Key == KEY
            and ContentLength == 3
            and IfNoneMatch == "*"
        )
        sends.append(1)
        data = Body.read()
        entered.set()
        assert release.wait(2)
        stored.append(data)
        # SDK output stubs require optional AWS-only fields absent from this response.
        return cast(PutObjectOutputTypeDef, {})

    monkeypatch.setattr(client, "put_object", delayed_put)
    store = S3ArtifactStore(
        settings(tmp_path, operation_timeout_seconds=0.02 if interruption == "timeout" else 1),
        client=client,
    )
    work = asyncio.create_task(store.put(ATTEMPT, BytesIO(b"abc")))
    try:
        assert await asyncio.to_thread(entered.wait, 1)
        if interruption == "cancel":
            work.cancel()
        with pytest.raises(ArtifactWriteOutcomeUnknownError):
            await work
        assert sends == [1] and stored == []
        closing = asyncio.create_task(store.close())
        await asyncio.sleep(0)
        assert not closing.done()
        release.set()
        await asyncio.wait_for(closing, 1)
        assert stored == [b"abc"] and sends == [1]
    finally:
        release.set()
        await asyncio.gather(work, return_exceptions=True)
        await store.close()


@pytest.mark.asyncio
async def test_existing_attempt_requires_conditional_write_without_replacement(
    tmp_path: Path, client: S3Client
) -> None:
    store = S3ArtifactStore(settings(tmp_path), client=client)
    with Stubber(client) as stub:
        stub.add_client_error(
            "put_object",
            "PreconditionFailed",
            http_status_code=412,
            expected_params={
                "Bucket": "private-artifacts",
                "Key": KEY,
                "Body": ANY,
                "ContentLength": 3,
                "IfNoneMatch": "*",
            },
        )
        with pytest.raises(ArtifactWriteOutcomeUnknownError):
            await store.put(ATTEMPT, BytesIO(b"abc"))
        stub.assert_no_pending_responses()
    await store.close()


@pytest.mark.asyncio
async def test_readback_budget_does_not_restart_after_each_yield(
    tmp_path: Path, client: S3Client
) -> None:
    raw = BytesIO(b"abc")
    store = S3ArtifactStore(settings(tmp_path, operation_timeout_seconds=0.1), client=client)
    with Stubber(client) as stub:
        stub.add_response(
            "get_object",
            {"Body": StreamingBody(raw, 3), "ContentLength": 3},
            {"Bucket": "private-artifacts", "Key": KEY},
        )
        stream = store.read(ATTEMPT)
        try:
            assert await anext(stream) == b"abc"
            await asyncio.sleep(0.12)
            with pytest.raises(ArtifactStoreUnavailableError):
                async for _ in stream:
                    pass
        finally:
            await stream.aclose()
            await store.close()
    assert raw.closed


@pytest.mark.asyncio
async def test_canceled_observation_closes_even_a_late_native_response(
    tmp_path: Path, client: S3Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    entered, release = threading.Event(), threading.Event()
    raw = BytesIO(b"abc")

    def delayed_get(*, Bucket: str, Key: str) -> GetObjectOutputTypeDef:
        assert Bucket == "private-artifacts" and Key == KEY
        entered.set()
        assert release.wait(2)
        # Model only the concrete SDK response fields consumed by this fixture.
        return cast(GetObjectOutputTypeDef, {"Body": StreamingBody(raw, 3), "ContentLength": 3})

    monkeypatch.setattr(client, "get_object", delayed_get)
    store = S3ArtifactStore(settings(tmp_path), client=client)
    stream = store.read(ATTEMPT)
    work = asyncio.create_task(anext(stream))
    try:
        assert await asyncio.to_thread(entered.wait, 1)
        work.cancel()
        with pytest.raises(asyncio.CancelledError):
            await work
        release.set()
        await store.close()
        assert raw.closed
    finally:
        release.set()
        await asyncio.gather(work, return_exceptions=True)
        await stream.aclose()
        await store.close()


@pytest.mark.asyncio
async def test_canceled_body_read_keeps_drain_ownership_until_native_read_finishes(
    tmp_path: Path, client: S3Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    raw = BytesIO(b"abc")
    body = StreamingBody(raw, 3)
    reads: list[int | None] = []
    results: list[bytes] = []
    gets: list[int] = []
    closures: list[bool] = []
    original_read, original_close = body.read, body.close

    def get_body(*, Bucket: str, Key: str) -> GetObjectOutputTypeDef:
        assert Bucket == "private-artifacts" and Key == KEY
        gets.append(1)
        # Model only the concrete SDK response fields consumed by this fixture.
        return cast(GetObjectOutputTypeDef, {"Body": body, "ContentLength": 3})

    def delayed_read(amt: int | None = None) -> bytes:
        reads.append(amt)
        entered.set()
        try:
            assert release.wait(2)
            result = original_read(amt)
            results.append(result)
            return result
        finally:
            finished.set()

    def close_body() -> None:
        closures.append(finished.is_set())
        original_close()

    monkeypatch.setattr(client, "get_object", get_body)
    monkeypatch.setattr(body, "read", delayed_read)
    monkeypatch.setattr(body, "close", close_body)
    store = S3ArtifactStore(settings(tmp_path), client=client)
    stream = store.read(ATTEMPT)
    work = asyncio.create_task(anext(stream))
    closing: asyncio.Task[None] | None = None
    try:
        assert await asyncio.to_thread(entered.wait, 1)
        work.cancel()
        with pytest.raises(asyncio.CancelledError):
            await work
        assert not raw.closed and closures == []

        closing = asyncio.create_task(store.close())
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert not closing.done() and not raw.closed

        release.set()
        await asyncio.wait_for(closing, 1)
        assert raw.closed and closures == [True]
        assert gets == [1] and reads == [65536] and results == [b"abc"]
    finally:
        release.set()
        await asyncio.gather(work, return_exceptions=True)
        if closing is not None:
            await asyncio.gather(closing, return_exceptions=True)
        await stream.aclose()
        await store.close()


@pytest.mark.asyncio
async def test_canceling_close_keeps_native_put_owned_until_repeated_close_drains(
    tmp_path: Path, client: S3Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    pool_closed = threading.Event()
    sends: list[int] = []
    stored: list[bytes] = []
    closures: list[bool] = []
    original_close = client.close

    def delayed_put(
        *, Bucket: str, Key: str, Body: BinaryIO, ContentLength: int, IfNoneMatch: str
    ) -> PutObjectOutputTypeDef:
        assert (
            Bucket == "private-artifacts"
            and Key == KEY
            and ContentLength == 3
            and IfNoneMatch == "*"
        )
        sends.append(1)
        data = Body.read()
        entered.set()
        try:
            assert release.wait(3)
            stored.append(data)
            return cast(PutObjectOutputTypeDef, {})
        finally:
            finished.set()

    def close_pool() -> None:
        closures.append(finished.is_set())
        pool_closed.set()
        original_close()

    monkeypatch.setattr(client, "put_object", delayed_put)
    monkeypatch.setattr(client, "close", close_pool)
    store = S3ArtifactStore(settings(tmp_path), client=client)
    work = asyncio.create_task(store.put(ATTEMPT, BytesIO(b"abc")))
    first_close: asyncio.Task[None] | None = None
    second_close: asyncio.Task[None] | None = None
    try:
        assert await asyncio.to_thread(entered.wait, 1)
        work.cancel()
        with pytest.raises(ArtifactWriteOutcomeUnknownError):
            await work
        first_close = asyncio.create_task(store.close())
        await asyncio.sleep(0)
        first_close.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first_close
        second_close = asyncio.create_task(store.close())
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert not pool_closed.is_set() and not second_close.done(), (
            "Canceling the first close must not discard the live native PUT."
        )
        release.set()
        await asyncio.wait_for(second_close, 1)
        await store.close()
        assert stored == [b"abc"] and sends == [1]
        assert closures == [True]
    finally:
        release.set()
        assert await asyncio.to_thread(finished.wait, 1)
        await asyncio.gather(
            *(task for task in (work, first_close, second_close) if task is not None),
            return_exceptions=True,
        )
        await store.close()
