"""Supply bounded test-only clients for one disposable live SeaweedFS instance."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

import boto3
from botocore import UNSIGNED
from botocore.config import Config
from pydantic import SecretStr

from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.dtos.artifact_attempt_dto import ArtifactAttemptDTO
from inframeld_backend.shared.application.dtos.artifact_scope_dto import ArtifactScopeDTO
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
from tests.support.integration_services import ARTIFACT_STORAGE_URL, TLS_CA_FILE

if TYPE_CHECKING:
    from mypy_boto3_s3.client import S3Client

BUCKET = "inframeld-artifact-test"
ACCESS_KEY = "inframeld-artifact-client"
SECRET_KEY = "inframeld-artifact-client-test-only"
BOOTSTRAP_ACCESS_KEY = "inframeld-artifact-bootstrap"
BOOTSTRAP_SECRET_KEY = "inframeld-artifact-bootstrap-test-only"
MAX_OBJECT_BYTES = 8 * 1024**2
MAX_SUBMITTED_BYTES = 32 * 1024**2


def storage_settings() -> ArtifactStorageSettings:
    return ArtifactStorageSettings(
        endpoint_url=ARTIFACT_STORAGE_URL,
        bucket=BUCKET,
        access_key_id=SecretStr(ACCESS_KEY),
        secret_access_key=SecretStr(SECRET_KEY),
        ca_bundle=TLS_CA_FILE,
        max_object_bytes=MAX_OBJECT_BYTES,
    )


def create_client(
    *,
    bootstrap: bool = False,
    anonymous: bool = False,
    invalid_credentials: bool = False,
    ca_bundle: Path = TLS_CA_FILE,
) -> S3Client:
    # These credentials belong only to the committed disposable test configuration.
    return boto3.client(  # pyright: ignore[reportUnknownMemberType]
        "s3",
        endpoint_url=ARTIFACT_STORAGE_URL,
        region_name="us-east-1",
        aws_access_key_id=BOOTSTRAP_ACCESS_KEY if bootstrap else ACCESS_KEY,
        aws_secret_access_key=(
            "wrong-test-secret"
            if invalid_credentials
            else BOOTSTRAP_SECRET_KEY
            if bootstrap
            else SECRET_KEY
        ),
        verify=str(ca_bundle),
        config=Config(
            signature_version=UNSIGNED if anonymous else "s3v4",
            s3={"addressing_style": "path", "payload_signing_enabled": True},
            retries={"total_max_attempts": 1},
            connect_timeout=5,
            read_timeout=30,
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        ),
    )


def new_attempt(content: bytes, *, scope: ArtifactScopeDTO | None = None) -> ArtifactAttemptDTO:
    return ArtifactAttemptDTO(
        ArtifactId(uuid4()),
        ArtifactAttemptId(uuid4()),
        scope
        or ArtifactScopeDTO(InstallationId(uuid4()), OrganizationId(uuid4()), ProjectId(uuid4())),
        len(content),
        ArtifactContentDigest.from_content(content),
    )


class SeaweedFixture:
    """Charge every submitted body, including conflicts, without refunding DELETEs."""

    def __init__(self) -> None:
        self.submitted_bytes = 0

    def body(self, content: bytes) -> bytes:
        assert len(content) <= MAX_OBJECT_BYTES
        assert self.submitted_bytes + len(content) <= MAX_SUBMITTED_BYTES
        self.submitted_bytes += len(content)
        return content

    @asynccontextmanager
    async def open_store(
        self, *, client: S3Client | None = None
    ) -> AsyncGenerator[S3ArtifactStore]:
        store = S3ArtifactStore(storage_settings(), client=client)
        try:
            yield store
        finally:
            await store.close()
