from dataclasses import dataclass
from typing import Literal

from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey


@dataclass(frozen=True, slots=True)
class OperationAdmissionContextDTO:
    """Identify a logical retry scope without supplying caller authority or request meaning."""

    method: Literal["POST", "PUT", "PATCH", "DELETE"]
    requested_route: str
    key: IdempotencyKey
