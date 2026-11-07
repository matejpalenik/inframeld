from uuid import UUID

import pytest
from starlette.types import Scope
from tests.support.authentication_evidence import MockAuthenticationEvidence

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.http.mappers.mcp_access_context_mapper import MCPAccessContextMapper


def test_safe_application_evidence_reaches_the_use_case() -> None:
    access = AccessContextDTO(
        PrincipalId(UUID(int=1)), MockAuthenticationEvidence.application_key()
    )
    scope: Scope = {"type": "http", "state": {"inframeld_mcp_access": access}}
    assert MCPAccessContextMapper.from_scope(scope) is access


@pytest.mark.parametrize(
    "state",
    [
        {},
        {"inframeld_mcp_access": "client claim"},
        {
            "inframeld_mcp_access": AccessContextDTO(
                PrincipalId(UUID(int=1)), MockAuthenticationEvidence.browser()
            )
        },
    ],
)
def test_absent_or_wrong_evidence_is_an_internal_assembly_error(state: dict[str, object]) -> None:
    scope: Scope = {"type": "http", "state": state}
    with pytest.raises(RuntimeError):
        MCPAccessContextMapper.from_scope(scope)
