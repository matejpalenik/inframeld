from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.human_admission_facts_dto import (
    HumanAdmissionFactsDTO,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.shared.application.value_objects.operation_id import OperationId


class HumanAdmissionWriter(Protocol):
    """Save admission, audit and immutable original meaning without committing.

    Require the coordinated caller transaction and IN_PROGRESS Org reservation.
    New admission inserts the exact principal/link and advances the Org revision
    once. Only that path may initialize absent generation 1 without history.
    Already-admitted work records one no-change audit and original outcome, with
    no principal/link/version/revision update. Never create resources or grants.
    """

    @abstractmethod
    async def save(
        self,
        *,
        facts: HumanAdmissionFactsDTO,
        principal: Principal,
        actor_id: PrincipalId,
        operation_id: OperationId,
    ) -> None: ...
