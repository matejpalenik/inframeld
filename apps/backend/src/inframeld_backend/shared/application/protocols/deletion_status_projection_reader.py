from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.deletion_status_authorization_dto import (
    DeletionStatusAuthorizationDTO,
)
from inframeld_backend.shared.application.dtos.deletion_status_observation_dto import (
    DeletionStatusObservationDTO,
)


class DeletionStatusProjectionReader(Protocol):
    """Observe retained binding/owner facts and database time in checked actor scope.

    Filter by the exact installation, Organization, principal and operation.
    Never require surviving Project membership or mutate/repair retained data.
    Return no observation when matching history is absent. Required dependency
    failures raise DependencyUnavailableError rather than an empty observation.
    """

    @abstractmethod
    async def read(
        self, *, authorization: DeletionStatusAuthorizationDTO
    ) -> DeletionStatusObservationDTO | None: ...
