"""Fingerprint the meaningful fields of a project grant command."""

from json import dumps

from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)

_ASSIGN_USE_ONLY_PURPOSE = "access.project-grant.assign-use-only:v1"


class ProjectGrantChangeFingerprintService:
    """Define grant-command meaning before the shared keyed fingerprint is made."""

    def __init__(self, fingerprints: RequestFingerprintService) -> None:
        self._fingerprints = fingerprints

    def for_assign_use_only(
        self,
        *,
        project_id: ProjectId,
        recipient_principal_id: PrincipalId,
        action_id: ActionId,
        expected_access_revision: int,
    ) -> bytes:
        """Include every field that can change this particular grant decision."""
        canonical_request = dumps(
            {
                "actionId": action_id.value,
                "expectedAccessRevision": expected_access_revision,
                "projectId": str(project_id.value),
                "recipientPrincipalId": str(recipient_principal_id.value),
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

        return self._fingerprints.fingerprint(
            purpose=_ASSIGN_USE_ONLY_PURPOSE,
            canonical_request=canonical_request,
        )
