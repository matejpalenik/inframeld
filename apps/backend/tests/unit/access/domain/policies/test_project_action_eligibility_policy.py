from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.policies.project_action_eligibility_policy import (
    ProjectActionEligibilityPolicy,
)
from inframeld_backend.access.domain.value_objects.action_id import ActionId


def test_metadata_is_human_only_while_budget_inspection_stays_application_eligible() -> None:
    assert ProjectActionEligibilityPolicy.may_use(
        action_id=ActionId("edit-project-metadata"), principal_kind=PrincipalKind.HUMAN
    )
    assert not ProjectActionEligibilityPolicy.may_use(
        action_id=ActionId("edit-project-metadata"), principal_kind=PrincipalKind.APPLICATION
    )
    assert ProjectActionEligibilityPolicy.may_use(
        action_id=ActionId("inspect-budget"), principal_kind=PrincipalKind.APPLICATION
    )
