import pytest
from tests.support.mock_project_metadata import (
    ACCESS,
    NEW_RESERVATION,
    PROJECT_ID,
    SAVED_RESULT,
    MockMetadataAuthorizer,
    MockMetadataRepository,
    MockOperationIdempotency,
    MockTransactions,
)

from inframeld_backend.access.application.commands.update_project_metadata_command import (
    UpdateProjectMetadataCommand,
)
from inframeld_backend.access.application.services.project_metadata_fingerprint_service import (
    ProjectMetadataFingerprintService,
)
from inframeld_backend.access.application.services.project_metadata_service import (
    ProjectMetadataService,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import (
    IdempotencyContextDTO,
)
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.errors.application_errors import AccessDeniedError
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.request_fingerprint_key import (
    RequestFingerprintKey,
)
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName


class Scenario:
    def __init__(self) -> None:
        self.events: list[str] = []
        self.authorizer = MockMetadataAuthorizer(self.events)
        self.repository = MockMetadataRepository(self.events)
        self.idempotency = MockOperationIdempotency(self.events)
        self.service = ProjectMetadataService(
            transaction_manager=MockTransactions(self.events),
            metadata_authorizer=self.authorizer,
            metadata_repository=self.repository,
            operation_idempotency=self.idempotency,
            metadata_fingerprint_service=ProjectMetadataFingerprintService(
                RequestFingerprintService(RequestFingerprintKey(b"K" * 32))
            ),
        )

    async def update(self, *, revision: int = 0):
        return await self.service.update(
            access=ACCESS,
            command=UpdateProjectMetadataCommand(PROJECT_ID, revision, ResourceName("support")),
            context=IdempotencyContextDTO(
                HttpMethod.PATCH,
                "/v1/projects/{project_id}/metadata",
                IdempotencyKey("same-request"),
            ),
        )


@pytest.mark.asyncio
async def test_replay_recovers_original_metadata_after_current_authorization() -> None:
    scenario = Scenario()
    result = await scenario.update(revision=900)
    assert result.metadata == scenario.repository.saved
    assert result.operation == SAVED_RESULT
    assert scenario.events == ["begin", "authorize", "reserve", "original", "commit"]
    scenario.authorizer.error = AccessDeniedError()
    with pytest.raises(AccessDeniedError):
        await scenario.update()
    assert scenario.events[-3:] == ["begin", "authorize", "rollback"]


@pytest.mark.asyncio
async def test_first_allocation_keeps_legacy_label_and_completes_in_same_transaction() -> None:
    scenario = Scenario()
    scenario.idempotency.result = NEW_RESERVATION
    result = await scenario.update()
    assert result.metadata.display_name == " legacy\nlabel "
    assert result.metadata.name == ResourceName("support")
    assert scenario.events == [
        "begin",
        "authorize",
        "reserve",
        "load",
        "save",
        "complete",
        "commit",
    ]


@pytest.mark.asyncio
async def test_save_failure_cannot_complete_the_reservation() -> None:
    scenario = Scenario()
    scenario.idempotency.result = NEW_RESERVATION
    scenario.repository.error = RuntimeError("audit write failed")
    with pytest.raises(RuntimeError):
        await scenario.update()
    assert "complete" not in scenario.events
    assert scenario.events[-1] == "rollback"
