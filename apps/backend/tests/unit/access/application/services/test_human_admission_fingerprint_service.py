from dataclasses import replace
from uuid import UUID

import pytest
from tests.support.human_admission_scenarios import COMMAND, HumanAdmissionScenario

from inframeld_backend.access.application.commands.admit_human_command import AdmitHumanCommand
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId


def test_equivalent_admission_retains_meaning() -> None:
    fingerprints = HumanAdmissionScenario().fingerprints
    assert fingerprints.for_admit(COMMAND) == fingerprints.for_admit(replace(COMMAND))


@pytest.mark.parametrize(
    "changed",
    [
        replace(COMMAND, identity_id=UUID(int=200)),
        replace(COMMAND, organization_id=OrganizationId(UUID(int=200))),
        replace(COMMAND, expected_access_revision=8),
    ],
)
def test_admission_fingerprint_covers_target_scope_and_revision(changed: AdmitHumanCommand) -> None:
    fingerprints = HumanAdmissionScenario().fingerprints
    assert fingerprints.for_admit(COMMAND) != fingerprints.for_admit(changed)
