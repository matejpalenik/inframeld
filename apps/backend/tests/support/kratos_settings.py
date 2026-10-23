"""Follow a real recovery redirect and submit its password-settings form."""

from typing import Literal
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

import httpx2
from pydantic import SecretStr

from tests.support.integration_services import KRATOS_PUBLIC_URL
from tests.support.kratos_browser import BrowserFlow, IdentityResponse


class SettingsFlowResponse(BrowserFlow):
    id: UUID
    identity: IdentityResponse
    state: Literal["show_form", "success"]


async def read_recovery_settings(
    browser: httpx2.AsyncClient, recovery_response: httpx2.Response
) -> SettingsFlowResponse:
    """Read the settings flow selected by Kratos after verified recovery."""
    assert recovery_response.status_code in {302, 303}, "Recovery did not redirect to settings."
    location = recovery_response.headers.get("location")
    assert location is not None, "Recovery did not select a settings URL."
    selected = urlsplit(location)
    expected = urlsplit(KRATOS_PUBLIC_URL)
    assert (selected.scheme, selected.netloc, selected.path) == (
        expected.scheme,
        expected.netloc,
        "/settings",
    ), "Recovery selected an unexpected settings destination."
    flow_ids = parse_qs(selected.query).get("flow", [])
    assert len(flow_ids) == 1, "Recovery did not select exactly one settings flow."
    flow_id = UUID(flow_ids[0])
    response = await browser.get(
        "/self-service/settings/flows",
        params={"id": str(flow_id)},
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 200, "Could not read the recovery's settings flow."
    settings = SettingsFlowResponse.model_validate_json(response.text)
    assert settings.id == flow_id, "Kratos returned a different settings flow."
    return settings


async def submit_password_settings(
    browser: httpx2.AsyncClient, flow: SettingsFlowResponse, password: SecretStr
) -> httpx2.Response:
    """Return the provider response without assuming failure means no password change."""
    action = urlsplit(flow.ui.action)
    expected = urlsplit(KRATOS_PUBLIC_URL)
    assert (action.scheme, action.netloc, action.path) == (
        expected.scheme,
        expected.netloc,
        "/self-service/settings",
    ), "Settings selected an unexpected form destination."
    assert parse_qs(action.query).get("flow") == [str(flow.id)], "Settings action changed flow."
    tokens = [
        node.attributes.value for node in flow.ui.nodes if node.attributes.name == "csrf_token"
    ]
    assert len(tokens) == 1 and isinstance(tokens[0], str), "Expected one settings CSRF token."
    return await browser.post(
        flow.ui.action,
        data={
            "csrf_token": tokens[0],
            "password": password.get_secret_value(),
            "method": "password",
        },
        headers={"Accept": "application/json"},
    )
