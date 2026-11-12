from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.commands.restore_human_command import RestoreHumanCommand
from inframeld_backend.access.application.commands.suspend_human_command import SuspendHumanCommand
from inframeld_backend.access.application.dtos.human_lifecycle_facts_dto import (
    HumanLifecycleFactsDTO,
)
from inframeld_backend.access.application.dtos.human_restoration_result_dto import (
    HumanRestorationResultDTO,
)
from inframeld_backend.access.application.dtos.human_suspension_result_dto import (
    HumanSuspensionResultDTO,
)
from inframeld_backend.access.domain.entities.human_suspension import HumanSuspension
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.shared.application.dtos.new_operation_reservation_dto import (
    NewOperationReservationDTO,
)
from inframeld_backend.shared.application.value_objects.request_id import RequestId


class HumanLifecycleWriter(Protocol):
    """Persist checked lifecycle effects and originals without committing.

    Suspension saves local state, one original durable obligation/admission,
    revision and audit atomically, preserving an existing obligation on no-op.
    Restoration conditionally saves state/version/revision/audit together.
    Neither path edits assignments or releases independent recovery blocks.
    The SERVICE completes the shared reservation in this same transaction.
    """

    @abstractmethod
    async def save_suspension(
        self,
        *,
        facts: HumanLifecycleFactsDTO,
        command: SuspendHumanCommand,
        target: Principal,
        suspension: HumanSuspension,
        operation: NewOperationReservationDTO,
        request_id: RequestId,
    ) -> None: ...

    @abstractmethod
    async def save_restoration(
        self,
        *,
        facts: HumanLifecycleFactsDTO,
        command: RestoreHumanCommand,
        target: Principal,
        version: HumanCredentialVersion,
        operation: NewOperationReservationDTO,
    ) -> None: ...

    @abstractmethod
    async def save_result(
        self,
        *,
        facts: HumanLifecycleFactsDTO,
        result: HumanSuspensionResultDTO | HumanRestorationResultDTO,
    ) -> None: ...
