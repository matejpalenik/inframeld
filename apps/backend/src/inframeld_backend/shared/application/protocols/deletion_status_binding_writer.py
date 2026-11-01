from abc import abstractmethod
from typing import Protocol

from inframeld_backend.shared.application.dtos.deletion_status_binding_dto import (
    DeletionStatusBindingDTO,
)
from inframeld_backend.shared.application.dtos.new_operation_reservation_dto import (
    NewOperationReservationDTO,
)
from inframeld_backend.shared.application.dtos.operation_reservation_request_dto import (
    OperationReservationRequestDTO,
)
from inframeld_backend.shared.application.value_objects.request_id import RequestId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


class DeletionStatusBindingWriter(Protocol):
    """Correlate a native reservation in its trusted caller's active transaction.

    Reload and match the real original reservation, human and Project scope before
    inserting. RequestId is trusted owning-workflow attribution, not a field in
    native idempotency storage. It cannot be recovered from a reservation.
    Identical retained bindings survive reservation expiry without changing their
    captured profile or timestamp. Changed attribution or meaning raises ConflictError.
    Never commit, create deletion effects or start the settlement retention clock.
    """

    @abstractmethod
    async def bind_original_request(
        self,
        *,
        reservation: NewOperationReservationDTO,
        request_id: RequestId,
        expected_installation_id: InstallationId,
        expected_request: OperationReservationRequestDTO,
    ) -> DeletionStatusBindingDTO: ...
