from dataclasses import replace
from uuid import UUID

import pytest
from tests.support.mock_human_lifecycle import RESTORE, SUSPEND

from inframeld_backend.access.application.services.human_lifecycle_fingerprint_service import (
    HumanLifecycleFingerprintService,
)
from inframeld_backend.access.application.value_objects.security_review_reference import (
    SecurityReviewReference,
)
from inframeld_backend.access.application.value_objects.suspension_reason import SuspensionReason
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.request_fingerprint_key import (
    RequestFingerprintKey,
)


@pytest.mark.parametrize(
    "field", ["organization_id", "principal_id", "expected_access_revision", "reason"]
)
def test_suspension_fingerprint_binds_exact_reviewed_intent(field: str) -> None:
    service = HumanLifecycleFingerprintService(
        RequestFingerprintService(RequestFingerprintKey(b"s" * 32))
    )
    changes = {
        "organization_id": OrganizationId(UUID(int=70)),
        "principal_id": PrincipalId(UUID(int=71)),
        "expected_access_revision": 8,
        "reason": SuspensionReason("Another review"),
    }
    assert service.for_suspend(SUSPEND) == service.for_suspend(SUSPEND)
    assert service.for_suspend(SUSPEND) != service.for_suspend(
        replace(SUSPEND, **{field: changes[field]})
    )


@pytest.mark.parametrize(
    "field",
    ["organization_id", "principal_id", "expected_access_revision", "security_review_reference"],
)
def test_restoration_fingerprint_binds_exact_reviewed_intent(field: str) -> None:
    service = HumanLifecycleFingerprintService(
        RequestFingerprintService(RequestFingerprintKey(b"s" * 32))
    )
    changes = {
        "organization_id": OrganizationId(UUID(int=70)),
        "principal_id": PrincipalId(UUID(int=71)),
        "expected_access_revision": 8,
        "security_review_reference": SecurityReviewReference("Another-review"),
    }
    assert service.for_restore(RESTORE) == service.for_restore(RESTORE)
    assert service.for_restore(RESTORE) != service.for_restore(
        replace(RESTORE, **{field: changes[field]})
    )


def test_suspend_and_restore_use_distinct_fingerprint_purposes() -> None:
    service = HumanLifecycleFingerprintService(
        RequestFingerprintService(RequestFingerprintKey(b"s" * 32))
    )
    assert service.for_suspend(SUSPEND) != service.for_restore(RESTORE)
