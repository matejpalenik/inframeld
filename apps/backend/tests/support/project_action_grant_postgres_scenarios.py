"""Exercise full grants after delivered admission, Project creation and membership."""

from inframeld_backend.access.application.commands.remove_project_action_grant_command import (
    RemoveProjectActionGrantCommand,
)
from inframeld_backend.access.application.commands.set_project_action_grant_command import (
    SetProjectActionGrantCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_action_grant_change_result_dto import (
    ProjectActionGrantChangeResultDTO,
)
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.shared.application.dtos.idempotency_context_dto import (
    IdempotencyContextDTO,
)
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.infrastructure.resources.database import Database
from tests.support.project_grant_changes import create_project_grant_change_service
from tests.support.project_membership_postgres_scenarios import (
    MembershipProjectSeedDTO,
    change_membership,
    seed_membership_project,
)

_DEFAULT_ACTION = ActionId("inspect-budget")


async def seed_project_grant_recipients(database: Database) -> MembershipProjectSeedDTO:
    seed = await seed_membership_project(database)
    await change_membership(database, seed, revision=1, key="join-grant-recipient")
    return seed


async def change_project_grant(
    database: Database,
    seed: MembershipProjectSeedDTO,
    *,
    revision: int,
    key: str,
    can_grant: bool = False,
    removing: bool = False,
    action_id: ActionId = _DEFAULT_ACTION,
    recipient: PrincipalId | None = None,
    access: AccessContextDTO | None = None,
) -> ProjectActionGrantChangeResultDTO:
    project = seed.project.project_id
    principal = recipient or seed.bob_id
    context = IdempotencyContextDTO(
        HttpMethod.DELETE if removing else HttpMethod.PUT,
        f"/v1/projects/{project.value}/grants/{principal.value}/{action_id.value}",
        IdempotencyKey(key),
    )
    async with database.session() as session:
        service = create_project_grant_change_service(session)
        if removing:
            return await service.remove_action_grant(
                access=access or seed.actor.access,
                command=RemoveProjectActionGrantCommand(project, principal, action_id, revision),
                context=context,
            )
        return await service.set_action_grant(
            access=access or seed.actor.access,
            command=SetProjectActionGrantCommand(
                project, principal, action_id, can_grant, revision
            ),
            context=context,
        )
