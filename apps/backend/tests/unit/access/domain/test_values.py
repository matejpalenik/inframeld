"""Verify Access values reject unusable identifiers before they reach persistence."""

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import class_mapper

from inframeld_backend.access.domain.values import (
    ActionId,
    IdentityAuthority,
    IdentitySubject,
    PrincipalKind,
    PrincipalStatus,
    ProjectStatus,
)
from inframeld_backend.access.infrastructure.persistence_models import (
    AccessPersistenceBase,
    ApplicationAccountRow,
    HumanIdentityLinkRow,
    PrincipalRow,
    ProjectActionGrantRow,
    ProjectMembershipRow,
    ProjectRow,
)


@pytest.mark.parametrize("raw", ["", " ", "\t"])
def test_identity_authority_rejects_blank_values(raw: str) -> None:
    """A verified identity source must have a nonblank authority."""
    with pytest.raises(ValueError):
        IdentityAuthority(raw)


@pytest.mark.parametrize("raw", ["", " ", "\t"])
def test_identity_subject_rejects_blank_values(raw: str) -> None:
    """A verified identity must have a nonblank subject."""
    with pytest.raises(ValueError):
        IdentitySubject(raw)


@pytest.mark.parametrize("raw", ["", " ", "\t", "x" * 101])
def test_action_id_rejects_values_outside_the_grant_column(raw: str) -> None:
    """An action identifier must fit the nonblank grant column."""
    with pytest.raises(ValueError):
        ActionId(raw)


def test_identity_values_preserve_exact_verified_text() -> None:
    """Identity lookup uses the exact verified pair without normalizing it."""
    assert IdentityAuthority("kratos:Local ").value == "kratos:Local "
    assert IdentitySubject(" Alice ").value == " Alice "


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
