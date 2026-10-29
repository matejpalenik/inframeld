from typing import Annotated

from pydantic import Field

from inframeld_backend.shared.http.responses.accepted_operation_lookup_response import (
    AcceptedOperationLookupResponse,
)
from inframeld_backend.shared.http.responses.completed_operation_lookup_response import (
    CompletedOperationLookupResponse,
)
from inframeld_backend.shared.http.responses.in_progress_operation_lookup_response import (
    InProgressOperationLookupResponse,
)
from inframeld_backend.shared.http.responses.recovery_required_operation_lookup_response import (
    RecoveryRequiredOperationLookupResponse,
)
from inframeld_backend.shared.http.responses.unresolved_operation_lookup_response import (
    UnresolvedOperationLookupResponse,
)

type OperationLookupResponse = Annotated[
    CompletedOperationLookupResponse
    | AcceptedOperationLookupResponse
    | InProgressOperationLookupResponse
    | RecoveryRequiredOperationLookupResponse
    | UnresolvedOperationLookupResponse,
    Field(discriminator="outcome"),
]
