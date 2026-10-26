"""Convert persisted enum values to application-owned members and back."""

from enum import Enum as PythonEnum

from sqlalchemy import Enum

from inframeld_backend.access.application.enums.identity_recovery_event_kind import (
    IdentityRecoveryEventKind,
)
from inframeld_backend.access.application.enums.identity_recovery_evidence_type import (
    IdentityRecoveryEvidenceType,
)
from inframeld_backend.access.application.enums.identity_recovery_run_source import (
    IdentityRecoveryRunSource,
)
from inframeld_backend.access.domain.enums.identity_recovery_cleanup_state import (
    IdentityRecoveryCleanupState,
)
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

IDENTITY_RECOVERY_EVENT_KIND_TYPE = Enum(
    IdentityRecoveryEventKind,
    native_enum=False,
    values_callable=_enum_values,
    length=20,
    validate_strings=True,
)

IDENTITY_RECOVERY_CLEANUP_STATE_TYPE = Enum(
    IdentityRecoveryCleanupState,
    native_enum=False,
    values_callable=_enum_values,
    length=16,
    validate_strings=True,
)

IDENTITY_RECOVERY_EVIDENCE_TYPE = Enum(
    IdentityRecoveryEvidenceType,
    native_enum=False,
    values_callable=_enum_values,
    length=32,
    validate_strings=True,
)

IDENTITY_RECOVERY_RUN_SOURCE_TYPE = Enum(
    IdentityRecoveryRunSource,
    native_enum=False,
    values_callable=_enum_values,
    length=24,
    validate_strings=True,
)
