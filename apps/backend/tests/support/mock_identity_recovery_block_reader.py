"""Supply recovery outcomes without opening database sessions."""

import asyncio
from typing import override

from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.protocols.identity_recovery_block_reader import (
    IdentityRecoveryBlockReader,
)


class MockIdentityRecoveryBlockReader(IdentityRecoveryBlockReader):
    """Control current block state, failures, and overdue reads in unit tests."""

    def __init__(self) -> None:
        self.result = False
        self.failure: Exception | None = None
        self.stall = False
        self.return_after_cancellation = False
        self.identities: list[VerifiedHumanIdentityDTO] = []

    @override
    async def is_blocked(self, identity: VerifiedHumanIdentityDTO) -> bool:
        self.identities.append(identity)
        if self.failure is not None:
            raise self.failure

        if self.stall:
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                if not self.return_after_cancellation:
                    raise

        return self.result
