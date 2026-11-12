from json import dumps

from inframeld_backend.access.application.commands.restore_human_command import RestoreHumanCommand
from inframeld_backend.access.application.commands.suspend_human_command import SuspendHumanCommand
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)


class HumanLifecycleFingerprintService:
    def __init__(self, request_fingerprint_service: RequestFingerprintService) -> None:
        self._request_fingerprint_service = request_fingerprint_service

    def for_suspend(self, command: SuspendHumanCommand) -> RequestFingerprint:
        canonical = dumps(
            {
                "organizationId": str(command.organization_id.value),
                "principalId": str(command.principal_id.value),
                "expectedAccessRevision": command.expected_access_revision,
                "reason": command.reason.value,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return self._request_fingerprint_service.fingerprint(
            purpose="access.human.suspend:v1", canonical_request=canonical
        )

    def for_restore(self, command: RestoreHumanCommand) -> RequestFingerprint:
        canonical = dumps(
            {
                "organizationId": str(command.organization_id.value),
                "principalId": str(command.principal_id.value),
                "expectedAccessRevision": command.expected_access_revision,
                "securityReviewReference": command.security_review_reference.value,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return self._request_fingerprint_service.fingerprint(
            purpose="access.human.restore:v1", canonical_request=canonical
        )
