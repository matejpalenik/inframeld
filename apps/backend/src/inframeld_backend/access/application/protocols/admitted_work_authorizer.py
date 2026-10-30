from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.admitted_work_authority_dto import (
    AdmittedWorkAuthorityDTO,
)


class AdmittedWorkAuthorizer(Protocol):
    """Recheck an original job's current principal authority, without an incoming token.

    Supply authority loaded from server-owned durable admission and separately
    check the current attempt fence. This contract neither adds actions nor
    authorizes unknown external effects to repeat.
    """

    @abstractmethod
    async def require_current(self, authority: AdmittedWorkAuthorityDTO) -> None: ...
