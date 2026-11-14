from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.project_action import ProjectAction
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.indexing.application.commands.create_processing_profile_command import (
    CreateProcessingProfileCommand,
)
from inframeld_backend.indexing.domain.value_objects.docling_processing_definition import (
    DoclingProcessingDefinition,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName
from inframeld_backend.shared.domain.value_objects.submitted_display_name import (
    SubmittedDisplayName,
)
from inframeld_backend.shared.infrastructure.resources.database import Database


async def grant_profile_creation(
    database: Database, access: AccessContextDTO, project: ProjectId
) -> None:
    """Give a seeded legacy Project member the explicit creation action for a test."""
    async with database.session() as session, session.begin():
        session.add(
            ProjectActionGrantRow(
                project_id=project.value,
                recipient_principal_id=access.actor_principal_id.value,
                recipient_kind=PrincipalKind.HUMAN,
                action=ProjectAction.CREATE_PROCESSING_PROFILES.value,
                can_grant=True,
                assigned_by_principal_id=access.actor_principal_id.value,
            )
        )


def profile_command(project_id: ProjectId) -> CreateProcessingProfileCommand:
    return CreateProcessingProfileCommand(
        project_id=project_id,
        name=ResourceName("handbook"),
        display_name=SubmittedDisplayName("Support handbook"),
        definition=DoclingProcessingDefinition(
            docling_slim_version="2.148.0",
            docling_core_version="2.106.0",
            asset_manifest_sha256="7ea9f3c967a7bc66d2501e466334e7aef46a639e01a11376888321e0f0a51d0e",
            max_content_tokens=640,
            merge_peers=True,
            repeat_table_header=False,
            ocr_enabled=False,
        ),
    )


def profile_context(project_id: ProjectId, key: str) -> IdempotencyContextDTO:
    return IdempotencyContextDTO(
        HttpMethod.POST,
        f"/v1/projects/{project_id.value}/processing-profiles",
        IdempotencyKey(key),
    )
