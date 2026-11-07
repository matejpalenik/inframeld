"""Check the real verifier decisions with controlled SQLAlchemy I/O outcomes.

These cases do not establish SQL execution or lock behavior. PostgreSQL scenarios do.
"""

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import cast
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from inframeld_backend.access.application.dtos.application_key_verification_profile_dto import (
    ApplicationKeyVerificationProfileDTO,
)
from inframeld_backend.access.application.dtos.verified_application_key_dto import (
    VerifiedApplicationKeyDTO,
)
from inframeld_backend.access.application.value_objects.application_key_credential import (
    ApplicationKeyCredential,
)
from inframeld_backend.access.domain.enums.application_key_adapter import ApplicationKeyAdapter
from inframeld_backend.access.domain.value_objects.application_key_audience import (
    ApplicationKeyAudience,
)
from inframeld_backend.access.domain.value_objects.application_key_id import ApplicationKeyId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.infrastructure.rows.application_key_row import ApplicationKeyRow
from inframeld_backend.access.infrastructure.verifiers.postgres_application_key_verifier import (
    PostgresApplicationKeyVerifier,
)
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.infrastructure.resources.database import Database

pytestmark = pytest.mark.asyncio
INSTALLED = UUID(int=11)
ACTOR = UUID(int=12)
KEY_ID = UUID(int=13)
NOW = datetime(2030, 1, 1, tzinfo=UTC)
CREDENTIAL = ApplicationKeyCredential(f"ifm_app_{KEY_ID}_" + "A" * 43)
PROFILE = ApplicationKeyVerificationProfileDTO(
    ApplicationKeyAudience("https://api.test"), ApplicationKeyAdapter.HTTP
)


def key_row() -> ApplicationKeyRow:
    return ApplicationKeyRow(
        key_id=KEY_ID,
        organization_id=UUID(int=14),
        project_id=UUID(int=15),
        application_principal_id=ACTOR,
        installation_id=INSTALLED,
        audience=PROFILE.audience.value,
        allowed_adapters=["http"],
        verifier=sha256(CREDENTIAL.value.encode()).digest(),
        expires_at=NOW + timedelta(days=1),
    )


def verifier_for(
    row: ApplicationKeyRow | None,
    *,
    installed: UUID | None = INSTALLED,
    failure: BaseException | None = None,
) -> PostgresApplicationKeyVerifier:
    result = MagicMock()
    result.tuples.return_value.one_or_none.return_value = (
        (installed, row, NOW) if installed is not None else None
    )
    session = AsyncMock()
    session.execute.return_value = result
    session.execute.side_effect = failure
    manager = AsyncMock()
    manager.__aenter__.return_value = session
    database = MagicMock(spec=Database)
    database.session.return_value = manager
    return PostgresApplicationKeyVerifier(cast(Database, database))


async def test_complete_digest_and_trusted_bindings_produce_only_two_ids() -> None:
    result = await verifier_for(key_row()).verify(CREDENTIAL, profile=PROFILE)
    assert result == VerifiedApplicationKeyDTO(ApplicationKeyId(KEY_ID), PrincipalId(ACTOR))
    assert CREDENTIAL.value not in repr(result)


@pytest.mark.parametrize(
    "row",
    [
        None,
        replace(key_row(), verifier=b"X" * 32),
        replace(key_row(), installation_id=UUID(int=99)),
        replace(key_row(), audience="https://other.test"),
        replace(key_row(), allowed_adapters=["mcp"]),
        replace(key_row(), expires_at=NOW),
        replace(key_row(), revoked_at=NOW),
    ],
)
async def test_invalid_key_is_rejected_without_identity(row: ApplicationKeyRow | None) -> None:
    assert await verifier_for(row).verify(CREDENTIAL, profile=PROFILE) is None


async def test_missing_required_installation_metadata_is_unavailable() -> None:
    with pytest.raises(DependencyUnavailableError):
        await verifier_for(key_row(), installed=None).verify(CREDENTIAL, profile=PROFILE)


@pytest.mark.parametrize(
    "failure", [TimeoutError(), asyncio.CancelledError(), RuntimeError("unexpected")]
)
async def test_failures_do_not_become_credential_success(failure: BaseException) -> None:
    expected = DependencyUnavailableError if isinstance(failure, TimeoutError) else type(failure)
    with pytest.raises(expected):
        await verifier_for(key_row(), failure=failure).verify(CREDENTIAL, profile=PROFILE)
