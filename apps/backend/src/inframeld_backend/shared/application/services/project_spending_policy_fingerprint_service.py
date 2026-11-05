import json

from inframeld_backend.shared.application.commands.change_project_spending_policy_command import (
    ChangeProjectSpendingPolicyCommand,
)
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)


class ProjectSpendingPolicyFingerprintService:
    """Keep conditional policy request meaning stable without storing credentials."""

    def __init__(self, request_fingerprint_service: RequestFingerprintService) -> None:
        self._request_fingerprint_service = request_fingerprint_service

    def for_change(self, command: ChangeProjectSpendingPolicyCommand) -> RequestFingerprint:
        amount = command.monthly_limit
        canonical = json.dumps(
            [
                str(command.project_id.value),
                command.expected_policy_revision,
                None if amount is None else [str(part) for part in amount.value.as_integer_ratio()],
            ],
            separators=(",", ":"),
        ).encode("utf-8")
        return self._request_fingerprint_service.fingerprint(
            purpose="project-spending-policy.change.v1", canonical_request=canonical
        )
