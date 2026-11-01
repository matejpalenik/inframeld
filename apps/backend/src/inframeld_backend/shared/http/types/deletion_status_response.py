from typing import Annotated

from pydantic import Field

from inframeld_backend.shared.http.responses.retained_deletion_status_response import (
    RetainedDeletionStatusResponse,
)
from inframeld_backend.shared.http.responses.unresolved_deletion_status_response import (
    UnresolvedDeletionStatusResponse,
)

type DeletionStatusResponse = Annotated[
    RetainedDeletionStatusResponse | UnresolvedDeletionStatusResponse,
    Field(discriminator="outcome"),
]
