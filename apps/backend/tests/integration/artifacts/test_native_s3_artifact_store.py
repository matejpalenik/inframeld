"""Exercise real live-instance S3 behavior, without claiming durable or physical cleanup."""

import os
from collections.abc import Iterator
from contextlib import closing
from dataclasses import replace
from io import BytesIO
from pathlib import Path
from uuid import UUID

import pytest
import trustme
from botocore.awsrequest import AWSResponse
from botocore.exceptions import ClientError, EndpointConnectionError, SSLError
from tests.support.seaweedfs_fixture import (
    BUCKET,
    MAX_OBJECT_BYTES,
    SeaweedFixture,
    create_client,
    new_attempt,
)

from inframeld_backend.shared.application.errors.artifact_errors import (
    ArtifactIntegrityError,
    ArtifactWriteOutcomeUnknownError,
)
from inframeld_backend.shared.application.services.artifact_verification_service import (
    ArtifactVerificationService,
)
from inframeld_backend.shared.application.value_objects.artifact_attempt_id import ArtifactAttemptId

pytestmark = pytest.mark.skipif(
    os.environ.get("INFRAMELD_RUN_ARTIFACT_INTEGRATION") != "1",
    reason="Requires the private maintained SeaweedFS test service.",
)


@pytest.fixture(scope="module")
def seaweed() -> Iterator[SeaweedFixture]:
    with closing(create_client(bootstrap=True)) as bootstrap:
        try:
            bootstrap.create_bucket(Bucket=BUCKET)
        except ClientError as error:
            response_error = error.response.get("Error")
            if (
                not isinstance(response_error, dict)
                or response_error.get("Code") != "BucketAlreadyOwnedByYou"
            ):
                raise
    yield SeaweedFixture()


@pytest.mark.asyncio
@pytest.mark.parametrize("size", [0, 65537, MAX_OBJECT_BYTES], ids=["empty", "stream", "8-mib"])
async def test_conditional_put_verifies_complete_actual_stream(
    seaweed: SeaweedFixture, size: int
) -> None:
    content = b"x" * size
    attempt = new_attempt(content)
    async with seaweed.open_store() as store:
        await store.put(attempt, BytesIO(seaweed.body(content)))
        verified = await ArtifactVerificationService(store).verify(attempt)
        assert verified.attempt == attempt
        observed = await store.head(attempt.scope, attempt.attempt_id)
        assert observed is not None and observed.length == len(content)


@pytest.mark.asyncio
async def test_immutable_key_conflict_preserves_original_bytes(seaweed: SeaweedFixture) -> None:
    attempt = new_attempt(b"abc")
    conflicting = replace(attempt, digest=new_attempt(b"xyz").digest)
    async with seaweed.open_store() as store:
        await store.put(attempt, BytesIO(seaweed.body(b"abc")))
        with pytest.raises(ArtifactWriteOutcomeUnknownError):
            await store.put(conflicting, BytesIO(seaweed.body(b"xyz")))
        assert (await ArtifactVerificationService(store).verify(attempt)).attempt == attempt
        with pytest.raises(ArtifactIntegrityError):
            await ArtifactVerificationService(store).verify(conflicting)


@pytest.mark.asyncio
async def test_bounded_scoped_inventory_and_exact_delete(seaweed: SeaweedFixture) -> None:
    first = replace(new_attempt(b"abc"), attempt_id=ArtifactAttemptId(UUID(int=10)))
    second = replace(first, attempt_id=ArtifactAttemptId(UUID(int=20)))
    foreign = new_attempt(b"abc")
    async with seaweed.open_store() as store:
        for attempt in (first, second, foreign):
            await store.put(attempt, BytesIO(seaweed.body(b"abc")))
        page = await store.list(first.scope, after=None, limit=1)
        assert [item.attempt_id for item in page.objects] == [first.attempt_id]
        assert page.after == first.attempt_id
        next_page = await store.list(first.scope, after=page.after, limit=1)
        assert [item.attempt_id for item in next_page.objects] == [second.attempt_id]
        assert next_page.after is None
        await store.delete(first.scope, first.attempt_id)
        assert await store.head(first.scope, first.attempt_id) is None
        for retained in (second, foreign):
            assert (await ArtifactVerificationService(store).verify(retained)).attempt == retained


@pytest.mark.asyncio
@pytest.mark.parametrize("stored", [b"ab", b"xyz"])
async def test_partial_or_mismatched_real_object_never_verifies(
    seaweed: SeaweedFixture, stored: bytes
) -> None:
    expected = new_attempt(b"abc")
    actual = replace(expected, length=len(stored), digest=new_attempt(stored).digest)
    async with seaweed.open_store() as store:
        await store.put(actual, BytesIO(seaweed.body(stored)))
        with pytest.raises(ArtifactIntegrityError):
            await ArtifactVerificationService(store).verify(expected)


@pytest.mark.asyncio
async def test_controlled_response_discard_reconciles_original_real_object(
    seaweed: SeaweedFixture,
) -> None:
    """Discard a real success locally, without representing a server-accepted late PUT."""
    sends = 0

    def discard(**values: object) -> None:
        nonlocal sends
        response = values.get("http_response")
        assert isinstance(response, AWSResponse) and response.status_code == 200
        sends += 1
        raise EndpointConnectionError(endpoint_url="https://seaweedfs:8333")

    client = create_client()
    client.meta.events.register("after-call.s3.PutObject", discard)
    attempt = new_attempt(b"abc")
    async with seaweed.open_store(client=client) as store:
        with pytest.raises(ArtifactWriteOutcomeUnknownError):
            await store.put(attempt, BytesIO(seaweed.body(b"abc")))
        verified = await ArtifactVerificationService(store).verify(attempt)
        assert verified.attempt == attempt and sends == 1


def test_anonymous_and_wrong_credentials_are_rejected() -> None:
    with closing(create_client(anonymous=True)) as client:
        with pytest.raises(ClientError) as denied:
            client.head_bucket(Bucket=BUCKET)
        assert denied.value.response.get("ResponseMetadata", {}).get("HTTPStatusCode") == 403
    with closing(create_client(invalid_credentials=True)) as client:
        with pytest.raises(ClientError) as denied:
            client.head_bucket(Bucket=BUCKET)
        assert denied.value.response.get("ResponseMetadata", {}).get("HTTPStatusCode") == 403


def test_storage_certificate_requires_the_explicit_fixture_ca(tmp_path: Path) -> None:
    other_ca = tmp_path / "other-ca.pem"
    trustme.CA().cert_pem.write_to_path(other_ca)
    with closing(create_client(ca_bundle=other_ca)) as client, pytest.raises(SSLError):
        client.head_bucket(Bucket=BUCKET)
