import os
import subprocess
import sys
from unittest.mock import patch
from uuid import UUID

import pytest
from sqlalchemy import BigInteger
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.infrastructure.resources.postgres_identity_coordinator import (
    PostgresIdentityCoordinator,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId

INSTALLATION = InstallationId(UUID(int=1))
IDENTITY = VerifiedHumanIdentityDTO(IdentityAuthority("kratos:test"), IdentitySubject("alice"))


@pytest.mark.asyncio
async def test_identity_lock_uses_the_stable_signed_bigint_key() -> None:
    """API and worker processes must request the same PostgreSQL lock for Alice."""
    async with AsyncSession() as session, session.begin():
        with (
            patch.object(session, "scalar", return_value="read committed"),
            patch.object(session, "execute") as execute,
        ):
            await PostgresIdentityCoordinator(session).acquire(
                installation_id=INSTALLATION, identity=IDENTITY
            )
        execute.assert_awaited_once()
        statement = execute.call_args.args[0]
        assert "pg_advisory_xact_lock" in str(statement)
        assert statement.compile().params == {"identity_lock_key": -3760129518390752271}
        assert isinstance(statement.selected_columns[0].clauses.clauses[0].type, BigInteger)
        assert session.in_transaction()


@pytest.mark.asyncio
async def test_acquisition_requires_an_existing_transaction() -> None:
    """A lock cannot silently start a transaction whose lifetime nobody owns."""
    async with AsyncSession() as session:
        with pytest.raises(RuntimeError, match="active.*transaction"):
            await PostgresIdentityCoordinator(session).acquire(
                installation_id=INSTALLATION, identity=IDENTITY
            )
        assert not session.in_transaction()


@pytest.mark.asyncio
@pytest.mark.parametrize("isolation", ["repeatable read", "serializable"])
async def test_a_retained_transaction_snapshot_is_rejected(isolation: str) -> None:
    """Waiting for a lock must not leave subsequent decisions using an old snapshot."""
    async with AsyncSession() as session, session.begin():
        with (
            patch.object(session, "scalar", return_value=isolation),
            patch.object(session, "execute") as execute,
            pytest.raises(RuntimeError, match="READ COMMITTED"),
        ):
            await PostgresIdentityCoordinator(session).acquire(
                installation_id=INSTALLATION, identity=IDENTITY
            )
        execute.assert_not_awaited()


def test_key_is_independent_of_the_process_hash_seed() -> None:
    """Restarting an API or worker must not change which identity lock it requests."""
    script = """
import asyncio
from unittest.mock import patch
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from inframeld_backend.access.application.dtos.verified_human_identity_dto import VerifiedHumanIdentityDTO
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.infrastructure.resources.postgres_identity_coordinator import PostgresIdentityCoordinator
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId

async def main():
    async with AsyncSession() as session, session.begin():
        with patch.object(session, 'scalar', return_value='read committed'), patch.object(session, 'execute') as execute:
            await PostgresIdentityCoordinator(session).acquire(
                installation_id=InstallationId(UUID(int=1)),
                identity=VerifiedHumanIdentityDTO(IdentityAuthority('kratos:test'), IdentitySubject('alice')),
            )
        print(execute.call_args.args[0].compile().params['identity_lock_key'])

asyncio.run(main())
"""
    for seed in ("1", "29"):
        result = subprocess.run(
            [sys.executable, "-c", script],
            env={**os.environ, "PYTHONHASHSEED": seed},
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        assert result.stdout.strip() == "-3760129518390752271"
