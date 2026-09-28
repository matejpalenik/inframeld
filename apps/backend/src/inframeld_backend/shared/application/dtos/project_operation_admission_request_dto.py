"""Carry the request details needed to admit one project operation."""

from dataclasses import dataclass
from typing import Literal

from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey


@dataclass(frozen=True, slots=True)
class ProjectOperationAdmissionRequestDTO:
    """Describe the request; the service obtains its principal and organization."""

    project_id: ProjectId
    method: Literal["POST", "PUT", "PATCH", "DELETE"]
    requested_route: str
    key: IdempotencyKey
    fingerprint: bytes
