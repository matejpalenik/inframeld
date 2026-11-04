import json

from inframeld_backend.access.application.commands.admit_human_command import AdmitHumanCommand
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)


class HumanAdmissionFingerprintService:
    def __init__(self, fingerprints: RequestFingerprintService) -> None:
        self._fingerprints = fingerprints

    def for_admit(self, command: AdmitHumanCommand) -> RequestFingerprint:
        return self._fingerprints.fingerprint(
            purpose="access.human-admission:v1",
            canonical_request=json.dumps(
                [
                    str(command.organization_id.value),
                    str(command.identity_id),
                    command.expected_access_revision,
                ],
                separators=(",", ":"),
            ).encode("utf-8"),
        )
