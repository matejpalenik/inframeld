"""Bind retirement fingerprints to the exact target and reviewed revision."""

from dataclasses import replace
from json import dumps
from uuid import UUID

import pytest

from inframeld_backend.access.application.commands.delete_application_account_command import (
    DeleteApplicationAccountCommand,
)
from inframeld_backend.access.application.services.application_account_deletion_fingerprint_service import (
    ApplicationAccountDeletionFingerprintService,
)
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.request_fingerprint_key import (
    RequestFingerprintKey,
)

COMMAND = DeleteApplicationAccountCommand(ProjectId(UUID(int=3)), PrincipalId(UUID(int=8)), 7)


def test_fingerprint_is_stable_and_matches_the_canonical_request() -> None:
    requests = RequestFingerprintService(RequestFingerprintKey(b"f" * 32))
    service = ApplicationAccountDeletionFingerprintService(requests)
    expected = requests.fingerprint(
        purpose="access.application-account.delete:v1",
        canonical_request=dumps(
            {
                "projectId": str(COMMAND.project_id.value),
                "applicationPrincipalId": str(COMMAND.application_principal_id.value),
                "expectedAccessRevision": 7,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8"),
    )
    assert service.for_delete(COMMAND) == expected == service.for_delete(COMMAND)


@pytest.mark.parametrize(
    "changed",
    [
        replace(COMMAND, project_id=ProjectId(UUID(int=20))),
        replace(COMMAND, application_principal_id=PrincipalId(UUID(int=20))),
        replace(COMMAND, expected_access_revision=8),
    ],
)
def test_every_reviewed_request_field_changes_fingerprint(
    changed: DeleteApplicationAccountCommand,
) -> None:
    service = ApplicationAccountDeletionFingerprintService(
        RequestFingerprintService(RequestFingerprintKey(b"f" * 32))
    )
    assert service.for_delete(changed) != service.for_delete(COMMAND)


@pytest.mark.parametrize(
    "revision,error",
    [
        (-1, ValueError),
        (True, TypeError),
        (9007199254740992, ValueError),
    ],
)
def test_command_rejects_invalid_reviewed_revision(
    revision: int,
    error: type[Exception],
) -> None:
    with pytest.raises(error):
        replace(COMMAND, expected_access_revision=revision)
