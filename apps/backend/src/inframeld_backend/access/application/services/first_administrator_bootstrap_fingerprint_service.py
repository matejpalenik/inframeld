import json

from inframeld_backend.access.application.commands.bootstrap_first_administrator_command import (
    BootstrapFirstAdministratorCommand,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)


class FirstAdministratorBootstrapFingerprintService:
    def __init__(self, request_fingerprint_service: RequestFingerprintService) -> None:
        self._request_fingerprint_service = request_fingerprint_service

    def for_bootstrap(
        self, command: BootstrapFirstAdministratorCommand, identity: VerifiedHumanIdentityDTO
    ) -> RequestFingerprint:
        return self._request_fingerprint_service.fingerprint(
            purpose="first-administrator-bootstrap",
            canonical_request=json.dumps(
                [
                    "bootstrap-first-administrator",
                    str(command.expected_installation_id.value),
                    identity.authority.value,
                    identity.subject.value,
                    str(command.expected_identity_id),
                    command.expected_access_revision,
                    command.operator_label,
                    command.reason,
                ],
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8"),
        )
