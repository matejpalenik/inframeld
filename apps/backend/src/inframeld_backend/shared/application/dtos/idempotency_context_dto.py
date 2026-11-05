from dataclasses import dataclass

from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey


@dataclass(frozen=True, slots=True)
class IdempotencyContextDTO:
    """Identify a logical retry scope without supplying caller authority or request meaning."""

    method: HttpMethod
    requested_route: str
    key: IdempotencyKey
