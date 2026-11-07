"""Exercise real live-instance S3 behavior, without claiming durable or physical cleanup."""

import os
from collections.abc import AsyncIterator, Iterator
from contextlib import closing
from dataclasses import replace
from io import BytesIO
from pathlib import Path
from uuid import UUID

import pytest
import trustme
from botocore.awsrequest import AWSResponse
from botocore.exceptions import ClientError, EndpointConnectionError, SSLError
from tests.support.artifact_scenarios import (
    allocate_artifact,
    artifact_scenario,
    seed_artifact_scope,
)
from tests.support.seaweedfs_fixture import (
    BUCKET,
    MAX_OBJECT_BYTES,
    SeaweedFixture,
    create_client,
    new_attempt,
    storage_settings,
)

from inframeld_backend.bootstrap.artifact_preparation_composition import create_artifact_preparation
from inframeld_backend.shared.application.dtos.artifact_attempt_dto import ArtifactAttemptDTO
from inframeld_backend.shared.application.dtos.artifact_capacity_dto import ArtifactCapacityDTO
from inframeld_backend.shared.application.errors.artifact_errors import (
    ArtifactIntegrityError,
    ArtifactWriteOutcomeUnknownError,
)
from inframeld_backend.shared.application.services.artifact_verification_service import (
    ArtifactVerificationService,
)
from inframeld_backend.shared.application.value_objects.artifact_attempt_id import ArtifactAttemptId
from inframeld_backend.shared.application.value_objects.artifact_content_digest import (
    ArtifactContentDigest,
)
from inframeld_backend.shared.infrastructure.readers.postgres_artifact_staging_reservation_reader import (
    PostgresArtifactStagingReservationReader,
)
from inframeld_backend.shared.infrastructure.repositories.postgres_artifact_attempt_repository import (
    PostgresArtifactAttemptRepository,
)
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.rows.artifact_cleanup_obligation_row import (
    ArtifactCleanupObligationRow,
)
from inframeld_backend.shared.infrastructure.rows.artifact_staging_reservation_row import (
    ArtifactStagingReservationRow,
)
from inframeld_backend.shared.infrastructure.settings.artifact_staging_settings import (
    ArtifactStagingSettings,
)

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
async def test_private_preparation_resumes_and_publishes_original_allocation(
    seaweed: SeaweedFixture, database: Database, tmp_path: Path
) -> None:
    """Join real private preparation and SQL without claiming capacity or physical retirement."""
    scope = await seed_artifact_scope(database)
    # Supplied capacity qualifies allocation's SQL policy, not filesystem measurement.
    allocation = await allocate_artifact(
        database,
        artifact_scenario(scope),
        physical_capacity=ArtifactCapacityDTO(usable_bytes=1024**4, free_bytes=512 * 1024**3),
    )
    original = allocation.reservation
    content = seaweed.body(b"prepared storage bytes" * 4096)
    expected = ArtifactAttemptDTO(
        original.artifact_id,
        original.attempt_id,
        original.scope,
        len(content),
        ArtifactContentDigest.from_content(content),
    )
    async with database.session() as session:
        reservation = await session.get(
            ArtifactStagingReservationRow, original.reservation_id.value
        )
        assert reservation is not None
        remote_charge = reservation.remote_reserved_bytes
    assert remote_charge == original.limit_bytes
    staging_root = tmp_path / "staging"
    staging_root.mkdir(mode=0o700)
    preparation = await create_artifact_preparation(
        database, ArtifactStagingSettings(root=staging_root), storage_settings()
    )

    async def chunks() -> AsyncIterator[bytes]:
        for offset in range(0, len(content), 4096):
            yield content[offset : offset + 4096]

    verified = await preparation.prepare(allocation, chunks())
    assert verified.attempt == expected
    resumed = await preparation.resume(allocation)
    assert resumed == verified
    async with seaweed.open_store() as store:
        assert (await ArtifactVerificationService(store).verify(expected)) == verified
    async with database.session() as session, session.begin():
        await PostgresArtifactAttemptRepository(session).publish_verified(allocation, resumed)
    facts = await PostgresArtifactStagingReservationReader(database).read(original.reservation_id)
    assert facts is not None
    assert (
        facts.reservation_id,
        facts.artifact_id,
        facts.attempt_id,
        facts.scope,
        facts.expires_at,
        facts.length,
        facts.digest,
    ) == (
        original.reservation_id,
        expected.artifact_id,
        expected.attempt_id,
        expected.scope,
        original.expires_at,
        expected.length,
        expected.digest,
    )
    assert facts.published and facts.put_confirmed and facts.put_pending
    assert not facts.retired and not facts.released and not facts.staging_removed
    async with database.session() as session:
        reservation = await session.get(
            ArtifactStagingReservationRow, original.reservation_id.value
        )
        obligation = await session.get(
            ArtifactCleanupObligationRow, allocation.cleanup_binding.obligation_id.value
        )
        assert reservation is not None and reservation.remote_reserved_bytes == remote_charge
        assert obligation is not None and not obligation.physically_complete


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
