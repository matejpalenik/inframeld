from dataclasses import dataclass
from datetime import datetime

from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.domain.value_objects.usd_amount import UsdAmount


@dataclass(frozen=True, slots=True)
class ProjectSpendingPolicyDTO:
    """Observe policy and the database instant used for captured-period accounting."""

    organization_id: OrganizationId
    project_id: ProjectId
    revision: int
    monthly_limit: UsdAmount | None
    observed_at: datetime
