import asyncio
from dataclasses import dataclass, field
from typing import override
from uuid import UUID

from inframeld_backend.access.application.dtos.human_credential_state_dto import (
    HumanCredentialStateDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.protocols.human_credential_state_initializer import (
    HumanCredentialStateInitializer,
)
from inframeld_backend.access.application.protocols.human_credential_state_reader import (
    HumanCredentialStateReader,
)
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


@dataclass
class MockHumanCredentialStateReader(HumanCredentialStateReader, HumanCredentialStateInitializer):
    installation_id: InstallationId = InstallationId(UUID(int=123))
    version: HumanCredentialVersion | None = HumanCredentialVersion(1)
    result: bool = False
    failure: Exception | None = None
    initialization_failure: Exception | None = None
    initialization_stall: bool = False
    stall: bool = False
    return_after_cancellation: bool = False
    identities: list[VerifiedHumanIdentityDTO] = field(
        default_factory=list[VerifiedHumanIdentityDTO]
    )
    calls: list[str] = field(default_factory=list[str])
    events: list[str] | None = None
    snapshots: list[HumanCredentialStateDTO] = field(default_factory=list[HumanCredentialStateDTO])

    async def _observe(
        self, identity: VerifiedHumanIdentityDTO, action: str
    ) -> HumanCredentialStateDTO:
        self.calls.append(action)
        if self.events is not None:
            self.events.append("block" if action == "state" else action)
        self.identities.append(identity)
        failure = self.failure if action == "state" else self.initialization_failure
        if failure is not None:
            raise failure
        if self.stall if action == "state" else self.initialization_stall:
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                if not self.return_after_cancellation:
                    raise
        if self.snapshots:
            return self.snapshots.pop(0)
        return HumanCredentialStateDTO(self.installation_id, identity, self.version, self.result)

    @override
    async def read(self, identity: VerifiedHumanIdentityDTO) -> HumanCredentialStateDTO:
        return await self._observe(identity, "state")

    @override
    async def initialize(self, identity: VerifiedHumanIdentityDTO) -> HumanCredentialStateDTO:
        return await self._observe(identity, "initialize")
