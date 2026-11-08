"""Preserve the original adapter order and omitted lifetime without lossy coercion."""

from dataclasses import replace
from uuid import UUID

import pytest

from inframeld_backend.access.application.commands.issue_application_key_command import (
    IssueApplicationKeyCommand,
)
from inframeld_backend.access.domain.enums.application_key_adapter import ApplicationKeyAdapter
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId

COMMAND = IssueApplicationKeyCommand(
    project_id=ProjectId(UUID(int=3)),
    application_principal_id=PrincipalId(UUID(int=8)),
    allowed_adapters=(ApplicationKeyAdapter.MCP, ApplicationKeyAdapter.HTTP),
    expected_access_revision=7,
)


def test_order_and_omitted_lifetime_retain_the_original_request_meaning() -> None:
    assert COMMAND.allowed_adapters == (ApplicationKeyAdapter.MCP, ApplicationKeyAdapter.HTTP)
    assert COMMAND.expires_in_seconds is None
    assert replace(COMMAND, expires_in_seconds=1).expires_in_seconds == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"allowed_adapters": ()},
        {"allowed_adapters": []},
        {"allowed_adapters": (ApplicationKeyAdapter.HTTP, ApplicationKeyAdapter.HTTP)},
        {"allowed_adapters": ("http",)},
        {
            "allowed_adapters": (
                ApplicationKeyAdapter.HTTP,
                ApplicationKeyAdapter.MCP,
                ApplicationKeyAdapter.HTTP,
            )
        },
        *({"expires_in_seconds": value} for value in [0, -1, True, False, 1.0, 1.5, "1", 2**53]),
        *({"expected_access_revision": value} for value in [-1, True, 1.5, "7", 2**53]),
    ],
)
def test_invalid_or_mutable_input_cannot_change_retained_issuance_meaning(
    changes: dict[str, object],
) -> None:
    with pytest.raises((TypeError, ValueError)):
        replace(COMMAND, **changes)
