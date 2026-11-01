from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from uuid import UUID

from inframeld_backend.access.application.commands.repair_project_metadata_authority_command import (
    RepairProjectMetadataAuthorityCommand,
)
from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
    HumanOAuthCredentialBindingDTO,
)
from inframeld_backend.access.application.enums.project_metadata_maintenance_error_code import (
    ProjectMetadataMaintenanceErrorCode,
)
from inframeld_backend.access.application.errors.project_metadata_maintenance_error import (
    ProjectMetadataMaintenanceError,
)
from inframeld_backend.access.application.protocols.human_access_token_authenticator import (
    HumanAccessTokenAuthenticator,
)
from inframeld_backend.access.application.protocols.project_metadata_repairer import (
    ProjectMetadataRepairer,
)
from inframeld_backend.access.cli.mappers.project_metadata_maintenance_mapper import (
    ProjectMetadataMaintenanceMapper,
)
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    AuthenticationRequiredError,
)


class ProjectMetadataMaintenanceCli:
    """Verify recipient proof before opening the protected operation's SQL session."""

    def __init__(
        self,
        authenticator: HumanAccessTokenAuthenticator,
        open_repair: Callable[[], AbstractAsyncContextManager[ProjectMetadataRepairer]],
    ) -> None:
        self._authenticator = authenticator
        self._open_repair = open_repair

    async def execute(self, command: RepairProjectMetadataAuthorityCommand) -> dict[str, object]:
        code = ProjectMetadataMaintenanceErrorCode
        try:
            access = await self._authenticator.authenticate(command.identity_proof)
        except AuthenticationRequiredError:
            raise ProjectMetadataMaintenanceError(code.INVALID_IDENTITY_PROOF) from None
        except AccessDeniedError:
            raise ProjectMetadataMaintenanceError(code.IDENTITY_INELIGIBLE) from None
        evidence = access.authentication_evidence
        if not isinstance(evidence, HumanOAuthCredentialBindingDTO):
            raise ProjectMetadataMaintenanceError(code.INVALID_IDENTITY_PROOF)
        try:
            identity_id = UUID(evidence.identity.subject.value)
        except ValueError:
            raise ProjectMetadataMaintenanceError(code.INVALID_IDENTITY_PROOF) from None
        if identity_id != command.expected_identity_id:
            raise ProjectMetadataMaintenanceError(code.INVALID_IDENTITY_PROOF)
        if evidence.installation_id != command.expected_installation_id:
            raise ProjectMetadataMaintenanceError(code.INSTALLATION_MISMATCH)

        async with self._open_repair() as service:
            result = await service.repair(access=access, command=command)
        return ProjectMetadataMaintenanceMapper.result(result)
