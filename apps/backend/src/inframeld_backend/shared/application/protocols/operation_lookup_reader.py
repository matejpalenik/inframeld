from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.shared.application.dtos.original_operation_lookup_record_dto import (
    OriginalOperationLookupRecordDTO,
)
from inframeld_backend.shared.application.queries.lookup_original_operation_query import (
    LookupOriginalOperationQuery,
)


class OperationLookupReader(Protocol):
    """Read one exact original identity and immutable authority binding after authorization."""

    @abstractmethod
    async def read(
        self, *, principal_id: PrincipalId, query: LookupOriginalOperationQuery
    ) -> OriginalOperationLookupRecordDTO | None:
        """Return retained metadata or no authoritative match without changing history.

        Caller authorizes the expected guard first. Missing, mismatched, expired
        and insufficiently bound history are indistinguishable. Actual dependency
        failures propagate as failures. Never reserve, delete, repair or redispatch.

        A job reference requires an exact ordinary product binding and coherent
        original human identity/generation. It grants no execution or result access.
        Missing or non-authoritative job metadata leaves the retained admission
        observable with an unknown reference. Cleanup-origin attribution cannot
        identify a product job. The service validates the retained outcome itself.
        """
        ...
