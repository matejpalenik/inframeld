"""Convert persisted enum values to application-owned members and back."""

from enum import Enum as PythonEnum

from sqlalchemy import Enum

from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.enums.project_status import ProjectStatus


def _enum_values(members: type[PythonEnum]) -> list[str]:
    """Persist each enum member's existing string value, independently of its Python member name."""
    return [str(member.value) for member in members]


PRINCIPAL_KIND_TYPE = Enum(
    PrincipalKind,
    native_enum=False,
    values_callable=_enum_values,
    length=20,
    validate_strings=True,
)

PRINCIPAL_STATUS_TYPE = Enum(
    PrincipalStatus,
    native_enum=False,
    values_callable=_enum_values,
    length=20,
    validate_strings=True,
)

PROJECT_STATUS_TYPE = Enum(
    ProjectStatus,
    native_enum=False,
    values_callable=_enum_values,
    length=20,
    validate_strings=True,
)
