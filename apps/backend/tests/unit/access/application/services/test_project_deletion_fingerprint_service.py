"""Bind deletion meaning independently of transport metadata or current state."""

from dataclasses import replace
from uuid import UUID

import pytest

from inframeld_backend.access.application.commands.delete_project_command import (
    DeleteProjectCommand,
)
from inframeld_backend.access.application.services.project_deletion_fingerprint_service import (
    ProjectDeletionFingerprintService,
)
from inframeld_backend.access.domain.value_objects.project_deletion_obligation_id import (
    ProjectDeletionObligationId,
)
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.request_fingerprint_key import (
    RequestFingerprintKey,
)
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation

COMMAND = DeleteProjectCommand(ProjectId(UUID(int=3)), 7)


def test_fingerprint_has_fixed_purpose_and_complete_canonical_meaning() -> None:
    keyed = RequestFingerprintService(RequestFingerprintKey(b"K" * 32))
    service = ProjectDeletionFingerprintService(keyed)
    assert service.for_delete(COMMAND) == keyed.fingerprint(
        purpose="access.project.delete:v1",
        canonical_request=(
            b'{"expectedAccessRevision":7,"projectId":"00000000-0000-0000-0000-000000000003"}'
        ),
    )


@pytest.mark.parametrize(
    "command",
    [
        replace(COMMAND, project_id=ProjectId(UUID(int=4))),
        replace(COMMAND, expected_access_revision=8),
    ],
)
def test_changed_project_or_reviewed_revision_changes_request_meaning(
    command: DeleteProjectCommand,
) -> None:
    service = ProjectDeletionFingerprintService(
        RequestFingerprintService(RequestFingerprintKey(b"K" * 32))
    )
    assert service.for_delete(command) != service.for_delete(COMMAND)


@pytest.mark.parametrize("revision", [-1, RevisionValidation.MAX_VALUE + 1])
def test_invalid_reviewed_revision_is_rejected(revision: int) -> None:
    with pytest.raises(ValueError):
        DeleteProjectCommand(COMMAND.project_id, revision)


def test_boolean_revision_is_not_an_integer_review() -> None:
    with pytest.raises(TypeError):
        DeleteProjectCommand(COMMAND.project_id, True)


def test_obligation_identity_does_not_equal_the_project_with_the_same_uuid() -> None:
    assert ProjectDeletionObligationId(COMMAND.project_id.value) != COMMAND.project_id
