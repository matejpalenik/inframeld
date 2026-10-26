import json
from uuid import UUID

from pydantic import TypeAdapter
from starlette.exceptions import HTTPException

from inframeld_backend.access.application.dtos.identity_recovery_event_dto import (
    IdentityRecoveryEventDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_notification_result_dto import (
    IdentityRecoveryNotificationResultDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_settings_evidence_dto import (
    IdentityRecoverySettingsEvidenceDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.enums.identity_recovery_event_kind import (
    IdentityRecoveryEventKind,
)
from inframeld_backend.access.application.enums.identity_recovery_evidence_type import (
    IdentityRecoveryEvidenceType,
)
from inframeld_backend.access.application.value_objects.identity_session_id import IdentitySessionId
from inframeld_backend.access.application.value_objects.identity_settings_flow_id import (
    IdentitySettingsFlowId,
)
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_recovery_flow_id import (
    IdentityRecoveryFlowId,
)
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.http.responses.identity_recovery_notification_response import (
    IdentityRecoveryNotificationResponse,
)


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate field.")
        result[key] = value
    return result


def _reject_constant(_value: str) -> object:
    raise ValueError("Invalid JSON constant.")


def _uuid(value: object) -> UUID:
    if not isinstance(value, str):
        raise ValueError("A native identifier is required.")
    return UUID(value)


class IdentityRecoveryNotificationMapper:
    """Convert the private allowlisted envelope without retaining provider context."""

    @staticmethod
    def from_json(
        body: bytes, *, event_type: IdentityRecoveryEvidenceType, authority: IdentityAuthority
    ) -> IdentityRecoveryEventDTO | IdentityRecoverySettingsEvidenceDTO:
        try:
            data: object = json.loads(
                body.decode("utf-8"),
                object_pairs_hook=_unique_object,
                parse_constant=_reject_constant,
            )
            values = TypeAdapter(dict[str, object]).validate_python(data, strict=True)
            common = {"schemaVersion", "eventType", "identityId"}
            fields = (
                {"recoveryFlowId", "eventKind"}
                if event_type is IdentityRecoveryEvidenceType.RECOVERY_CODE_VERIFIED
                else {"settingsFlowId", "sessionId", "sourceRecoveryFlowId"}
            )
            if (
                set(values) != common | fields
                or type(values["schemaVersion"]) is not int
                or values["schemaVersion"] != 2
                or values["eventType"] != event_type.value
            ):
                raise ValueError("Invalid envelope.")
            identity = VerifiedHumanIdentityDTO(
                authority, IdentitySubject(str(_uuid(values["identityId"])))
            )
            if event_type is IdentityRecoveryEvidenceType.RECOVERY_CODE_VERIFIED:
                kind = values["eventKind"]
                if not isinstance(kind, str):
                    raise ValueError("Invalid event kind.")
                return IdentityRecoveryEventDTO(
                    IdentityRecoveryFlowId(_uuid(values["recoveryFlowId"])),
                    identity,
                    IdentityRecoveryEventKind(kind),
                )
            source = values["sourceRecoveryFlowId"]
            return IdentityRecoverySettingsEvidenceDTO(
                identity=identity,
                settings_flow_id=IdentitySettingsFlowId(_uuid(values["settingsFlowId"])),
                session_id=IdentitySessionId(_uuid(values["sessionId"])),
                source_recovery_flow_id=None
                if source is None
                else IdentityRecoveryFlowId(_uuid(source)),
            )
        except (ValueError, TypeError, UnicodeError, RecursionError):
            raise HTTPException(422, "Invalid recovery notification.") from None

    @staticmethod
    def to_response(
        result: IdentityRecoveryNotificationResultDTO,
    ) -> IdentityRecoveryNotificationResponse:
        return IdentityRecoveryNotificationResponse(
            operationId=result.operation_id.value, eventType=result.event_type
        )
