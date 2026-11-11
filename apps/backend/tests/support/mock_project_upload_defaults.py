from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import override
from uuid import UUID

from inframeld_backend.access.application.commands.set_project_upload_default_command import (
    SetProjectUploadDefaultCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.human_credential_facts_dto import (
    HumanCredentialFactsDTO,
)
from inframeld_backend.access.application.dtos.project_action_facts_dto import ProjectActionFactsDTO
from inframeld_backend.access.application.dtos.project_upload_default_facts_dto import (
    ProjectUploadDefaultFactsDTO,
)
from inframeld_backend.access.application.dtos.project_upload_default_record_dto import (
    ProjectUploadDefaultRecordDTO,
)
from inframeld_backend.access.application.dtos.upload_default_group_facts_dto import (
    UploadDefaultGroupFactsDTO,
)
from inframeld_backend.access.application.protocols.project_upload_default_facts_reader import (
    ProjectUploadDefaultFactsReader,
)
from inframeld_backend.access.application.protocols.project_upload_default_repository import (
    ProjectUploadDefaultRepository,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.entities.project_upload_default import ProjectUploadDefault
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.domain.value_objects.upload_audience import UploadAudience
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.protocols.transaction_manager import TransactionManager
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)
from tests.support.mock_project_metadata import ACCESS, ORGANIZATION_ID, PROJECT_ID, SAVED_RESULT

A = AccessGroupId(UUID(int=10))
B = AccessGroupId(UUID(int=20))
C = AccessGroupId(UUID(int=30))
OLD = UploadAudience((A,))
NEW = UploadAudience((B,))
COMMAND = SetProjectUploadDefaultCommand(PROJECT_ID, NEW, 7)
ACTOR = Principal(
    ACCESS.actor_principal_id, ORGANIZATION_ID, PrincipalKind.HUMAN, PrincipalStatus.ACTIVE
)
FACTS = ProjectUploadDefaultFactsDTO(
    ORGANIZATION_ID,
    PROJECT_ID,
    7,
    ProjectActionFactsDTO(
        ACTOR,
        False,
        HumanCredentialFactsDTO(True, HumanCredentialVersion(1)),
        ProjectStatus.ACTIVE,
        True,
        True,
    ),
    OLD,
    (
        UploadDefaultGroupFactsDTO(A, PROJECT_ID, True, True, False),
        UploadDefaultGroupFactsDTO(B, PROJECT_ID, True, True, False),
    ),
)
ORIGINAL = ProjectUploadDefaultRecordDTO(
    SAVED_RESULT.operation_id,
    ORGANIZATION_ID,
    PROJECT_ID,
    ACCESS.actor_principal_id,
    7,
    8,
    OLD,
    NEW,
)


class MockUploadDefaultTransactions(TransactionManager):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.commit_ack_error: Exception | None = None

    @override
    @asynccontextmanager
    async def begin(self) -> AsyncGenerator[None]:
        self.events.append("begin")
        try:
            yield
        except BaseException:
            self.events.append("rollback-requested")
            raise
        else:
            self.events.append("commit-attempt")
            if self.commit_ack_error is not None:
                self.events.append("commit-outcome-unknown")
                raise self.commit_ack_error
            self.events.append("commit-confirmed")


class MockUploadDefaultFactsReader(ProjectUploadDefaultFactsReader):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.facts: ProjectUploadDefaultFactsDTO | None = FACTS
        self.error: Exception | None = None

    @override
    async def read(
        self, *, access: AccessContextDTO, project_id: ProjectId
    ) -> ProjectUploadDefaultFactsDTO | None:
        self.events.append("read-current")
        if self.error is not None:
            raise self.error
        return self.facts

    @override
    async def lock_for_change(
        self, *, access: AccessContextDTO, command: SetProjectUploadDefaultCommand
    ) -> ProjectUploadDefaultFactsDTO | None:
        self.events.append("lock-current")
        if self.error is not None:
            raise self.error
        return self.facts


class MockUploadDefaultRepository(ProjectUploadDefaultRepository):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.default = ProjectUploadDefault(
            organization_id=ORGANIZATION_ID, project_id=PROJECT_ID, audience=OLD, access_revision=7
        )
        self.saved: list[ProjectUploadDefaultRecordDTO] = []
        self.saved_original: ProjectUploadDefaultRecordDTO | None = ORIGINAL
        self.error: Exception | None = None

    @override
    async def get(
        self, *, organization_id: OrganizationId, project_id: ProjectId
    ) -> ProjectUploadDefault:
        self.events.append("load")
        return self.default

    @override
    async def save(
        self,
        default: ProjectUploadDefault,
        *,
        original: ProjectUploadDefaultRecordDTO,
        fingerprint: RequestFingerprint,
    ) -> None:
        self.events.append("save")
        if self.error is not None:
            raise self.error
        self.saved.append(original)

    @override
    async def original(
        self,
        *,
        organization_id: OrganizationId,
        project_id: ProjectId,
        actor_principal_id: PrincipalId,
        operation: CompletedSynchronousOperationDTO,
    ) -> ProjectUploadDefaultRecordDTO | None:
        self.events.append("original")
        return self.saved_original
