"""Prepare ordinary admission and Project creation before real membership operations."""

from dataclasses import dataclass, replace
from uuid import UUID

from inframeld_backend.access.application.commands.add_project_member_command import (
    AddProjectMemberCommand,
)
from inframeld_backend.access.application.commands.admit_human_command import AdmitHumanCommand
from inframeld_backend.access.application.commands.remove_project_member_command import (
    RemoveProjectMemberCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.created_project_dto import (
    CreatedProjectDTO,
)
from inframeld_backend.access.application.dtos.project_membership_change_result_dto import (
    ProjectMembershipChangeResultDTO,
)
from inframeld_backend.access.application.services.human_admission_fingerprint_service import (
    HumanAdmissionFingerprintService,
)
from inframeld_backend.access.application.services.project_membership_change_fingerprint_service import (
    ProjectMembershipChangeFingerprintService,
)
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.bootstrap.human_admission_composition import open_human_admission
from inframeld_backend.bootstrap.postgres_project_membership_change_service_factory import (
    PostgresProjectMembershipChangeServiceFactory,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import (
    IdempotencyContextDTO,
)
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.request_fingerprint_key import (
    RequestFingerprintKey,
)
from inframeld_backend.shared.infrastructure.resources.database import Database
from tests.support.first_administrator_bootstrap_scenarios import MockBootstrapIdentityVerifier
from tests.support.project_creation_scenarios import (
    ProjectCreationSeedDTO,
    create_project,
    seed_project_creator,
)


@dataclass(frozen=True, slots=True)
class MembershipProjectSeedDTO:
    actor: ProjectCreationSeedDTO
    project: CreatedProjectDTO
    bob_id: PrincipalId


def membership_fingerprints() -> ProjectMembershipChangeFingerprintService:
    return ProjectMembershipChangeFingerprintService(
        RequestFingerprintService(RequestFingerprintKey(b"m" * 32))
    )


async def seed_membership_project(database: Database) -> MembershipProjectSeedDTO:
    """Use delivered services with controlled provider proof, without implicit Bob grants."""
    actor = await seed_project_creator(database)
    fingerprints = HumanAdmissionFingerprintService(
        RequestFingerprintService(RequestFingerprintKey(b"a" * 32))
    )
    async with open_human_admission(
        database, fingerprints, MockBootstrapIdentityVerifier(), actor.binding.identity.authority, 5
    ) as service:
        admitted = await service.admit(
            access=actor.access,
            command=AdmitHumanCommand(actor.organization_id, UUID(int=200), actor.access_revision),
            context=IdempotencyContextDTO(
                HttpMethod.POST,
                f"/v1/organizations/{actor.organization_id.value}/human-admissions",
                IdempotencyKey("admit-bob"),
            ),
        )
    actor = replace(actor, access_revision=admitted.access_revision)
    return MembershipProjectSeedDTO(
        actor, (await create_project(database, actor)).project, admitted.principal_id
    )


async def change_membership(
    database: Database,
    seed: MembershipProjectSeedDTO,
    *,
    project_id: ProjectId | None = None,
    principal_id: PrincipalId | None = None,
    revision: int,
    key: str,
    remove: bool = False,
    access: AccessContextDTO | None = None,
) -> ProjectMembershipChangeResultDTO:
    project = project_id or seed.project.project_id
    principal = principal_id or seed.bob_id
    method = HttpMethod.DELETE if remove else HttpMethod.PUT
    context = IdempotencyContextDTO(
        method, f"/v1/projects/{project.value}/members/{principal.value}", IdempotencyKey(key)
    )
    factory = PostgresProjectMembershipChangeServiceFactory(database, membership_fingerprints())
    async with factory.open() as service:
        if remove:
            return await service.remove_member(
                access=access or seed.actor.access,
                command=RemoveProjectMemberCommand(project, principal, revision),
                context=context,
            )
        return await service.add_member(
            access=access or seed.actor.access,
            command=AddProjectMemberCommand(project, principal, revision),
            context=context,
        )
