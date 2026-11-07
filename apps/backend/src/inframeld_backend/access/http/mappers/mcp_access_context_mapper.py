from collections.abc import Mapping

from starlette.types import Scope

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.application_key_authentication_dto import (
    ApplicationKeyAuthenticationDTO,
)


class MCPAccessContextMapper:
    """Read only middleware-produced application evidence at the ASGI boundary."""

    @staticmethod
    def from_scope(scope: Scope) -> AccessContextDTO:
        state: Mapping[str, object] = scope.get("state", {})
        access = state.get("inframeld_mcp_access")
        if not isinstance(access, AccessContextDTO) or not isinstance(
            access.authentication_evidence, ApplicationKeyAuthenticationDTO
        ):
            raise RuntimeError("The MCP operation requires verified application evidence.")
        return access
