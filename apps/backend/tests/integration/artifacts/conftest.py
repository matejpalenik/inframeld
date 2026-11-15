from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

import pytest
from botocore.exceptions import ClientError
from tests.support.seaweedfs_fixture import BUCKET, SeaweedFixture, create_client


@pytest.fixture(scope="session")
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


@pytest.fixture(scope="module")
def alice_pdf() -> bytes:
    fixture_dir = Path(__file__).resolve().parents[2] / "fixtures" / "documents"
    return (fixture_dir / "alice-in-wonderland.pdf").read_bytes()
