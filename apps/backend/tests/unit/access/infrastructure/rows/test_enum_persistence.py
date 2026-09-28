"""Verify ORM enum conversion preserves the stored Access vocabulary."""

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import class_mapper

from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.infrastructure.rows.access_persistence_base import (
    AccessPersistenceBase,
)
from inframeld_backend.access.infrastructure.rows.application_account_row import (
    ApplicationAccountRow,
)
from inframeld_backend.access.infrastructure.rows.human_identity_link_row import (
    HumanIdentityLinkRow,
)
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.project_membership_row import ProjectMembershipRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow


@pytest.mark.parametrize(
    ("row_type", "column_name", "stored_value", "expected"),
    [
        (PrincipalRow, "kind", "human", PrincipalKind.HUMAN),
        (PrincipalRow, "status", "suspended", PrincipalStatus.SUSPENDED),
        (ProjectRow, "status", "deleting", ProjectStatus.DELETING),
        (ApplicationAccountRow, "principal_kind", "application", PrincipalKind.APPLICATION),
        (ProjectMembershipRow, "principal_kind", "application", PrincipalKind.APPLICATION),
        (ProjectActionGrantRow, "recipient_kind", "human", PrincipalKind.HUMAN),
        (HumanIdentityLinkRow, "principal_kind", "human", PrincipalKind.HUMAN),
    ],
)
def test_access_enum_columns_round_trip_existing_string_values(
    row_type: type[AccessPersistenceBase], column_name: str, stored_value: str, expected: object
) -> None:
    """ORM enum columns read typed members and keep their existing stored strings."""
    column_type = class_mapper(row_type).columns[column_name].type
    dialect = postgresql.dialect()
    read_value = column_type.result_processor(dialect, None)
    bind_value = column_type.bind_processor(dialect)

    assert read_value is not None
    assert bind_value is not None
    assert read_value(stored_value) is expected
    assert bind_value(expected) == stored_value
