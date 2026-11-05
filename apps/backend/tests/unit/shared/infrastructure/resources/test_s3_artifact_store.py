import asyncio
import hashlib
import threading
from collections.abc import Callable, Iterator
from io import BytesIO
from pathlib import Path
from typing import BinaryIO, cast, override
from uuid import UUID, uuid4

import boto3
import pytest
from botocore.config import Config
from botocore.exceptions import EndpointConnectionError
from botocore.response import StreamingBody
from botocore.stub import ANY, Stubber
from mypy_boto3_s3.client import S3Client
from mypy_boto3_s3.type_defs import (
    DeleteObjectOutputTypeDef,
    GetObjectOutputTypeDef,
    PutObjectOutputTypeDef,
)

from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.dtos.artifact_attempt_dto import ArtifactAttemptDTO
from inframeld_backend.shared.application.dtos.artifact_scope_dto import ArtifactScopeDTO
from inframeld_backend.shared.application.errors.application_errors import (
    ConflictError,
    DependencyUnavailableError,
)
from inframeld_backend.shared.application.errors.artifact_errors import (
    ArtifactIntegrityError,
    ArtifactStoreUnavailableError,
    ArtifactWriteOutcomeUnknownError,
)
from inframeld_backend.shared.application.errors.job_errors import SafeJobRetryError
from inframeld_backend.shared.application.protocols.job_effect_observation_recorder import (
    JobEffectObservationRecorder,
)
from inframeld_backend.shared.application.value_objects.artifact_attempt_id import ArtifactAttemptId
from inframeld_backend.shared.application.value_objects.artifact_content_digest import (
    ArtifactContentDigest,
)
from inframeld_backend.shared.application.value_objects.artifact_id import ArtifactId
from inframeld_backend.shared.application.value_objects.job_effect_id import JobEffectId
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


class MockInvocationRecorder(JobEffectObservationRecorder):
    """Control admission and commit observations without claiming database qualification."""

    def __init__(self) -> None:
        self.admitted: set[JobEffectId] = set()
        self.aborted: list[tuple[str, JobEffectId]] = []
        self.failure: Exception | None = None
        self.abort_failure: Exception | None = None
        self.admitting = asyncio.Event()
        self.release: asyncio.Event | None = None

    async def _admit(self, observation: JobEffectId) -> None:
        self.admitting.set()
        if self.release is not None:
            await self.release.wait()
        if self.failure is not None:
            raise self.failure
        if observation in self.admitted:
            raise ConflictError("The invocation was already admitted.")
        self.admitted.add(observation)

    @override
    async def admit_put(self, observation: JobEffectId, attempt: ArtifactAttemptDTO) -> None:
        assert attempt == ATTEMPT
        await self._admit(observation)

    @override
    async def admit_delete(
        self, observation: JobEffectId, scope: ArtifactScopeDTO, attempt_id: ArtifactAttemptId
    ) -> None:
        assert (scope, attempt_id) == (SCOPE, ATTEMPT.attempt_id)
        await self._admit(observation)

    @override
    async def record_put_abort(self, observation: JobEffectId, attempt: ArtifactAttemptDTO) -> None:
        assert attempt == ATTEMPT and observation in self.admitted
        self.aborted.append(("put", observation))
        if self.abort_failure is not None:
            raise self.abort_failure

    @override
    async def record_delete_abort(
        self, observation: JobEffectId, scope: ArtifactScopeDTO, attempt_id: ArtifactAttemptId
    ) -> None:
        assert (scope, attempt_id) == (SCOPE, ATTEMPT.attempt_id)
        assert observation in self.admitted
        self.aborted.append(("delete", observation))
        if self.abort_failure is not None:
            raise self.abort_failure


def _capture_mutations(client: S3Client, monkeypatch: pytest.MonkeyPatch, sends: list[str]) -> None:
    def put(**_values: object) -> PutObjectOutputTypeDef:
        sends.append("put")
        return cast(PutObjectOutputTypeDef, {})

    def delete(**_values: object) -> DeleteObjectOutputTypeDef:
        sends.append("delete")
        return cast(DeleteObjectOutputTypeDef, {})

    monkeypatch.setattr(client, "put_object", put)
    monkeypatch.setattr(client, "delete_object", delete)


async def _invoke_bound(store: S3ArtifactStore, action: str, observation: JobEffectId) -> None:
    if action == "put":
        await store.put(ATTEMPT, BytesIO(b"abc"), observation=observation)
    else:
        await store.delete(SCOPE, ATTEMPT.attempt_id, observation=observation)


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["put", "delete"])
async def test_bound_mutation_requires_a_recorder_before_scheduling(
    tmp_path: Path, client: S3Client, monkeypatch: pytest.MonkeyPatch, action: str
) -> None:
    sends: list[str] = []
    _capture_mutations(client, monkeypatch, sends)
    store = S3ArtifactStore(settings(tmp_path), client=client)
    try:
        with pytest.raises(ArtifactStoreUnavailableError):
            await _invoke_bound(store, action, JobEffectId(uuid4()))
        assert sends == []
    finally:
        await store.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["put", "delete"])
async def test_duplicate_invocation_cannot_enter_again_in_a_fresh_adapter(
    tmp_path: Path, client: S3Client, monkeypatch: pytest.MonkeyPatch, action: str
) -> None:
    sends: list[str] = []
    _capture_mutations(client, monkeypatch, sends)
    recorder = MockInvocationRecorder()
    observation = JobEffectId(uuid4())
    first = S3ArtifactStore(settings(tmp_path), client=client, effect_observation_recorder=recorder)
    second = S3ArtifactStore(
        settings(tmp_path), client=client, effect_observation_recorder=recorder
    )
    try:
        await _invoke_bound(first, action, observation)
        with pytest.raises(ConflictError):
            await _invoke_bound(second, action, observation)
        assert sends == [action] and recorder.aborted == []
    finally:
        await first.close()
        await second.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["put", "delete"])
async def test_ambiguous_admission_never_schedules_or_records_abort(
    tmp_path: Path, client: S3Client, monkeypatch: pytest.MonkeyPatch, action: str
) -> None:
    sends: list[str] = []
    _capture_mutations(client, monkeypatch, sends)
    recorder = MockInvocationRecorder()
    recorder.failure = DependencyUnavailableError("The admission commit acknowledgment was lost.")
    store = S3ArtifactStore(settings(tmp_path), client=client, effect_observation_recorder=recorder)
    try:
        with pytest.raises(DependencyUnavailableError):
            await _invoke_bound(store, action, JobEffectId(uuid4()))
        assert sends == [] and recorder.aborted == []
    finally:
        await store.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["put", "delete"])
async def test_waiting_abort_excludes_the_late_callable_and_retains_exact_observation(
    tmp_path: Path, client: S3Client, monkeypatch: pytest.MonkeyPatch, action: str
) -> None:
    sends: list[str] = []
    _capture_mutations(client, monkeypatch, sends)
    recorder = MockInvocationRecorder()
    observation = JobEffectId(uuid4())
    scheduled = asyncio.Event()
    release = asyncio.Event()
    original = asyncio.to_thread

    async def delayed(function: Callable[[], None]) -> None:
        scheduled.set()
        await release.wait()
        await original(function)

    monkeypatch.setattr(asyncio, "to_thread", delayed)
    store = S3ArtifactStore(settings(tmp_path), client=client, effect_observation_recorder=recorder)
    task = asyncio.create_task(_invoke_bound(store, action, observation))
    try:
        await asyncio.wait_for(scheduled.wait(), 1)
        task.cancel()
        with pytest.raises(SafeJobRetryError):
            await task
        release.set()
        await asyncio.wait_for(store.close(), 1)
        assert sends == []
        assert recorder.admitted == {observation}
        assert recorder.aborted == [(action, observation)]
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
        await store.close()


@pytest.mark.asyncio
async def test_admission_wait_spends_the_original_storage_deadline(
    tmp_path: Path, client: S3Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    sends: list[str] = []
    _capture_mutations(client, monkeypatch, sends)
    recorder = MockInvocationRecorder()
    recorder.release = asyncio.Event()
    store = S3ArtifactStore(
        settings(tmp_path, operation_timeout_seconds=0.02),
        client=client,
        effect_observation_recorder=recorder,
    )
    task = asyncio.create_task(_invoke_bound(store, "put", JobEffectId(uuid4())))
    try:
        with pytest.raises(TimeoutError):
            await task
        assert sends == [] and recorder.aborted == []
    finally:
        recorder.release.set()
        await asyncio.gather(task, return_exceptions=True)
        await store.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["put", "delete"])
async def test_entered_invocation_cancellation_keeps_unknown_without_abort_proof(
    tmp_path: Path, client: S3Client, monkeypatch: pytest.MonkeyPatch, action: str
) -> None:
    entered = threading.Event()
    release = threading.Event()
    sends: list[str] = []

    def native() -> None:
        sends.append(action)
        entered.set()
        assert release.wait(2)

    def put(**_values: object) -> PutObjectOutputTypeDef:
        native()
        return cast(PutObjectOutputTypeDef, {})

    def delete(**_values: object) -> DeleteObjectOutputTypeDef:
        native()
        return cast(DeleteObjectOutputTypeDef, {})

    monkeypatch.setattr(client, "put_object", put)
    monkeypatch.setattr(client, "delete_object", delete)
    recorder = MockInvocationRecorder()
    observation = JobEffectId(uuid4())
    store = S3ArtifactStore(settings(tmp_path), client=client, effect_observation_recorder=recorder)
    task = asyncio.create_task(_invoke_bound(store, action, observation))
    try:
        assert await asyncio.to_thread(entered.wait, 1)
        task.cancel()
        with pytest.raises(ArtifactWriteOutcomeUnknownError):
            await task
        assert sends == [action] and recorder.aborted == []
        assert recorder.admitted == {observation}
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
        await asyncio.wait_for(store.close(), 1)


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["put", "delete"])
async def test_abort_recording_acknowledgment_loss_cannot_report_safe_retry(
    tmp_path: Path, client: S3Client, monkeypatch: pytest.MonkeyPatch, action: str
) -> None:
    sends: list[str] = []
    _capture_mutations(client, monkeypatch, sends)
    recorder = MockInvocationRecorder()
    recorder.abort_failure = DependencyUnavailableError("The proof commit acknowledgment was lost.")
    observation = JobEffectId(uuid4())
    scheduled = asyncio.Event()
    release = asyncio.Event()
    original = asyncio.to_thread

    async def delayed(function: Callable[[], None]) -> None:
        scheduled.set()
        await release.wait()
        await original(function)

    monkeypatch.setattr(asyncio, "to_thread", delayed)
    store = S3ArtifactStore(settings(tmp_path), client=client, effect_observation_recorder=recorder)
    task = asyncio.create_task(_invoke_bound(store, action, observation))
    try:
        await asyncio.wait_for(scheduled.wait(), 1)
        task.cancel()
        with pytest.raises(DependencyUnavailableError):
            await task
        release.set()
        await asyncio.wait_for(store.close(), 1)
        assert sends == []
        assert recorder.aborted == [(action, observation)]
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
        await store.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["put", "delete"])
@pytest.mark.parametrize("interruption", ["cancel", "timeout"])
async def test_abort_recording_cannot_outlive_the_original_operation_deadline(
    tmp_path: Path,
    client: S3Client,
    monkeypatch: pytest.MonkeyPatch,
    action: str,
    interruption: str,
) -> None:
    sends: list[str] = []
    _capture_mutations(client, monkeypatch, sends)
    recorder = MockInvocationRecorder()
    observation = JobEffectId(uuid4())
    scheduled = asyncio.Event()
    native_release = asyncio.Event()
    recording_started = asyncio.Event()
    record_release = asyncio.Event()
    original = asyncio.to_thread

    async def delayed(function: Callable[[], None]) -> None:
        scheduled.set()
        await native_release.wait()
        await original(function)

    async def record_put(bound: JobEffectId, attempt: ArtifactAttemptDTO) -> None:
        assert (bound, attempt) == (observation, ATTEMPT)
        recording_started.set()
        await record_release.wait()

    async def record_delete(
        bound: JobEffectId, scope: ArtifactScopeDTO, attempt_id: ArtifactAttemptId
    ) -> None:
        assert (bound, scope, attempt_id) == (observation, SCOPE, ATTEMPT.attempt_id)
        recording_started.set()
        await record_release.wait()

    monkeypatch.setattr(asyncio, "to_thread", delayed)
    monkeypatch.setattr(recorder, "record_put_abort", record_put)
    monkeypatch.setattr(recorder, "record_delete_abort", record_delete)
    store = S3ArtifactStore(
        settings(tmp_path, operation_timeout_seconds=1),
        client=client,
        effect_observation_recorder=recorder,
    )
    task = asyncio.create_task(_invoke_bound(store, action, observation))
    operation_completed = False
    outcome: BaseException | None = None
    try:
        await asyncio.wait_for(scheduled.wait(), 1)
        if interruption == "cancel":
            task.cancel()
            await asyncio.wait_for(recording_started.wait(), 1)
        done, _ = await asyncio.wait((task,), timeout=3)
        operation_completed = task in done
        if operation_completed:
            result = (await asyncio.gather(task, return_exceptions=True))[0]
            assert isinstance(result, BaseException)
            outcome = result
    finally:
        record_release.set()
        native_release.set()
        await asyncio.wait_for(asyncio.gather(task, return_exceptions=True), 1)
        await asyncio.wait_for(store.close(), 1)

    assert operation_completed, "Only the independent test watchdog completed."
    assert sends == [] and recorder.aborted == []
    assert recording_started.is_set() == (interruption == "cancel")
    assert isinstance(outcome, ArtifactWriteOutcomeUnknownError)
    cause = outcome.__cause__
    assert isinstance(cause, BaseExceptionGroup)
    failures = cast(BaseExceptionGroup[BaseException], cause).exceptions
    assert len(failures) == 2
    assert isinstance(
        failures[0], asyncio.CancelledError if interruption == "cancel" else TimeoutError
    )
    assert isinstance(failures[1], TimeoutError)
