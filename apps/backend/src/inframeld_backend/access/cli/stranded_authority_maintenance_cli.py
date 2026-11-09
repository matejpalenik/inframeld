"""Verify recipient proof before opening the protected operation's SQL session."""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from uuid import UUID

from inframeld_backend.access.application.commands.repair_stranded_authority_command import (
    RepairStrandedAuthorityCommand,
)
from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
    HumanOAuthCredentialBindingDTO,
)
from inframeld_backend.access.application.enums.stranded_authority_maintenance_error_code import (
    StrandedAuthorityMaintenanceErrorCode,
)
from inframeld_backend.access.application.errors.stranded_authority_maintenance_error import (
    StrandedAuthorityMaintenanceError,
)
from inframeld_backend.access.application.protocols.human_access_token_authenticator import (
    HumanAccessTokenAuthenticator,
)
from inframeld_backend.access.application.protocols.stranded_authority_repairer import (
    StrandedAuthorityRepairer,
)
from inframeld_backend.access.cli.mappers.stranded_authority_maintenance_mapper import (
    StrandedAuthorityMaintenanceMapper,
)
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    AuthenticationRequiredError,
)


class StrandedAuthorityMaintenanceCli:
    def __init__(
        self,
        authenticator: HumanAccessTokenAuthenticator,
        open_repair: Callable[[], AbstractAsyncContextManager[StrandedAuthorityRepairer]],
    ) -> None:
        self._authenticator = authenticator
        self._open_repair = open_repair

    async def execute(self, command: RepairStrandedAuthorityCommand) -> dict[str, object]:
        code = StrandedAuthorityMaintenanceErrorCode
        try:
            access = await self._authenticator.authenticate(command.identity_proof)
        except AuthenticationRequiredError:
            raise StrandedAuthorityMaintenanceError(code.INVALID_IDENTITY_PROOF) from None
        except AccessDeniedError:
            raise StrandedAuthorityMaintenanceError(code.IDENTITY_INELIGIBLE) from None
        evidence = access.authentication_evidence
        if not isinstance(evidence, HumanOAuthCredentialBindingDTO):
            raise StrandedAuthorityMaintenanceError(code.INVALID_IDENTITY_PROOF)
        try:
            identity_id = UUID(evidence.identity.subject.value)
        except ValueError:
            raise StrandedAuthorityMaintenanceError(code.INVALID_IDENTITY_PROOF) from None
        if identity_id != command.expected_identity_id:
            raise StrandedAuthorityMaintenanceError(code.INVALID_IDENTITY_PROOF)
        if evidence.installation_id != command.expected_installation_id:
            raise StrandedAuthorityMaintenanceError(code.INSTALLATION_MISMATCH)

        async with self._open_repair() as service:
            result = await service.repair(access=access, command=command)
        return StrandedAuthorityMaintenanceMapper.result(result)
