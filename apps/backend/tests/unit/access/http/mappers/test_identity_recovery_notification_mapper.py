import json
from uuid import UUID

import pytest
from starlette.exceptions import HTTPException

from inframeld_backend.access.application.dtos.identity_recovery_event_dto import (
    IdentityRecoveryEventDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_settings_evidence_dto import (
    IdentityRecoverySettingsEvidenceDTO,
)
from inframeld_backend.access.application.enums.identity_recovery_evidence_type import (
    IdentityRecoveryEvidenceType as Event,
)
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.http.mappers.identity_recovery_notification_mapper import (
    IdentityRecoveryNotificationMapper as Mapper,
)

AUTHORITY = IdentityAuthority("https://identity.example.test")
IDENTITY = "10000000-0000-0000-0000-000000000001"
FLOW = "20000000-0000-0000-0000-000000000001"
SESSION = "30000000-0000-0000-0000-000000000001"
ADMISSION = {
    "schemaVersion": 2,
    "eventType": Event.RECOVERY_CODE_VERIFIED.value,
    "identityId": IDENTITY,
    "recoveryFlowId": FLOW,
    "eventKind": "recovery",
}


def test_admission_maps_only_configured_authority() -> None:
    event = Mapper.from_json(
        json.dumps(ADMISSION).encode(), event_type=Event.RECOVERY_CODE_VERIFIED, authority=AUTHORITY
    )
    assert isinstance(event, IdentityRecoveryEventDTO)
    assert event.identity.authority == AUTHORITY
    assert event.identity.subject.value == IDENTITY
    assert event.flow_id.value == UUID(FLOW)


@pytest.mark.parametrize("kind", [Event.SETTINGS_FLOW_ASSOCIATED, Event.PASSWORD_SETTINGS_SAVED])
def test_settings_requires_nullable_native_source(kind: Event) -> None:
    body = {
        "schemaVersion": 2,
        "eventType": kind.value,
        "identityId": IDENTITY,
        "settingsFlowId": FLOW,
        "sessionId": SESSION,
        "sourceRecoveryFlowId": None,
    }
    result = Mapper.from_json(json.dumps(body).encode(), event_type=kind, authority=AUTHORITY)
    assert isinstance(result, IdentityRecoverySettingsEvidenceDTO)
    assert result.source_recovery_flow_id is None
    assert result.session_id.value == UUID(SESSION)
    del body["sourceRecoveryFlowId"]
    with pytest.raises(HTTPException) as error:
        Mapper.from_json(json.dumps(body).encode(), event_type=kind, authority=AUTHORITY)
    assert error.value.status_code == 422


@pytest.mark.parametrize(
    "body",
    [
        b'{"schemaVersion":2,"schemaVersion":2}',
        b"{} {}",
        b"[]",
        b"null",
        b"\xff",
        b'{"x":NaN}',
        json.dumps(ADMISSION | {"schemaVersion": 2.0}).encode(),
        json.dumps(ADMISSION | {"schemaVersion": True}).encode(),
        json.dumps(ADMISSION | {"schemaVersion": "2"}).encode(),
        json.dumps(ADMISSION | {"identityId": "not-a-uuid"}).encode(),
        json.dumps(ADMISSION | {"authority": "secret"}).encode(),
        json.dumps(ADMISSION | {"eventType": Event.PASSWORD_SETTINGS_SAVED.value}).encode(),
    ],
)
def test_invalid_envelopes_have_safe_errors(body: bytes) -> None:
    with pytest.raises(HTTPException) as error:
        Mapper.from_json(body, event_type=Event.RECOVERY_CODE_VERIFIED, authority=AUTHORITY)
    assert error.value.status_code == 422
    assert "secret" not in str(error.value)
