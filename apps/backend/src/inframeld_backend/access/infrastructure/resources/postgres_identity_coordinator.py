from hashlib import sha256
from json import dumps

from sqlalchemy import BigInteger, String, bindparam, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.types import NullType

from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


class PostgresIdentityCoordinator:
    """Give local database changes a turn for Alice's verified provider identity."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def acquire(
        self, *, installation_id: InstallationId, identity: VerifiedHumanIdentityDTO
    ) -> None:
        """Hold Alice's identity turn in the caller's bounded database stage.

        Require an active READ COMMITTED transaction. Read decision facts in a
        later statement after this returns. Commit or rollback releases the lock.
        This establishes no identity proof or permission.
        """
        transaction = self._session.get_nested_transaction() or self._session.get_transaction()
        if transaction is None or not transaction.is_active:
            raise RuntimeError("Identity coordination requires an active caller transaction.")

        with self._session.no_autoflush:
            isolation = await self._session.scalar(
                select(func.current_setting("transaction_isolation", type_=String()))
            )
            if isolation != "read committed":
                raise RuntimeError("Identity coordination requires READ COMMITTED isolation.")

            canonical = dumps(
                [
                    "inframeld.access.identity-coordination:v1",
                    str(installation_id.value),
                    identity.authority.value,
                    identity.subject.value,
                ],
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
            key = int.from_bytes(sha256(canonical).digest()[:8], "big", signed=True)
            await self._session.execute(
                select(
                    func.pg_advisory_xact_lock(
                        bindparam("identity_lock_key", key, type_=BigInteger()), type_=NullType()
                    )
                )
            )
