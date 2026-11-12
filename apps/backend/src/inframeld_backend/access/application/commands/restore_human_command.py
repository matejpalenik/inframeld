from dataclasses import dataclass

from inframeld_backend.access.application.value_objects.security_review_reference import (
    SecurityReviewReference,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId


@dataclass(frozen=True, slots=True)
class RestoreHumanCommand:
    organization_id: OrganizationId
    principal_id: PrincipalId
    expected_access_revision: int
    security_review_reference: SecurityReviewReference
