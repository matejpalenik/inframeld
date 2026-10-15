from typing import override

from inframeld_backend.access.application.dtos.identity_recovery_event_dto import (
    IdentityRecoveryEventDTO,
)
from inframeld_backend.access.application.protocols.identity_recovery_admission_writer import (
    IdentityRecoveryAdmissionWriter,
)
from inframeld_backend.access.application.protocols.identity_recovery_admitter import (
    IdentityRecoveryAdmitter,
)
from inframeld_backend.shared.application.errors.application_errors import ConflictError
from inframeld_backend.shared.application.value_objects.operation_id import OperationId


class IdentityRecoveryAdmissionService(IdentityRecoveryAdmitter):
    def __init__(self, writer: IdentityRecoveryAdmissionWriter) -> None:
        self._writer = writer

    @override
    async def admit(self, event: IdentityRecoveryEventDTO) -> OperationId:
        admission = await self._writer.reserve(event)
        if admission.event != event:
            raise ConflictError("The recovery flow is already bound to another event.")
        return admission.operation_id
