"""Keep conditional policy retries sensitive to meaning, not decimal spelling."""

from dataclasses import replace
from decimal import Decimal
from uuid import UUID

import pytest
from tests.unit.shared.application.services.test_spending_accounting_service import PROJECT, money

from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.commands.change_project_spending_policy_command import (
    ChangeProjectSpendingPolicyCommand,
)
from inframeld_backend.shared.application.services.project_spending_policy_fingerprint_service import (
    ProjectSpendingPolicyFingerprintService,
)
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.request_fingerprint_key import (
    RequestFingerprintKey,
)
from inframeld_backend.shared.domain.value_objects.usd_amount import UsdAmount


def test_equivalent_amounts_have_identical_request_meaning() -> None:
    service = ProjectSpendingPolicyFingerprintService(
        RequestFingerprintService(RequestFingerprintKey(b"k" * 32))
    )
    command = ChangeProjectSpendingPolicyCommand(PROJECT, 0, money("1"))
    assert service.for_change(command) == service.for_change(
        replace(command, monthly_limit=UsdAmount(Decimal("1.00")))
    )


def test_unlimited_zero_revision_and_project_have_distinct_meaning() -> None:
    service = ProjectSpendingPolicyFingerprintService(
        RequestFingerprintService(RequestFingerprintKey(b"k" * 32))
    )
    command = ChangeProjectSpendingPolicyCommand(PROJECT, 0, None)
    fingerprints = {
        service.for_change(command),
        service.for_change(replace(command, monthly_limit=money("0"))),
        service.for_change(replace(command, expected_policy_revision=1)),
        service.for_change(replace(command, project_id=ProjectId(UUID(int=9)))),
    }
    assert len(fingerprints) == 4


@pytest.mark.parametrize("revision", [-1, True])
def test_policy_command_rejects_invalid_revision(revision: int) -> None:
    with pytest.raises((TypeError, ValueError)):
        ChangeProjectSpendingPolicyCommand(PROJECT, revision, None)


def test_policy_command_rejects_negative_cap() -> None:
    with pytest.raises(ValueError):
        ChangeProjectSpendingPolicyCommand(PROJECT, 0, money("-1"))
