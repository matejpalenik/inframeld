"""Exercise real Kratos browser flows through validated, minimal response DTOs."""

from dataclasses import dataclass, field
from uuid import UUID, uuid4

import httpx2
from pydantic import BaseModel

from inframeld_backend.access.application.value_objects.browser_session_credential import (
    BrowserSessionCredential,
)
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject

KRATOS_PUBLIC_URL = "http://127.0.0.1:14433"


class InputAttributes(BaseModel):
    """Read only the form fields needed to obtain Kratos's browser CSRF token."""

    name: str | None = None
    value: object = None


class UiNode(BaseModel):
    """Normalize a Kratos UI node without copying unneeded provider metadata."""

    attributes: InputAttributes


class FlowUi(BaseModel):
    """Carry the server-selected form action and its input nodes."""

    action: str
    nodes: list[UiNode]


class BrowserFlow(BaseModel):
    """Validate the browser-flow response before reading its UI fields."""

    ui: FlowUi


class IdentityResponse(BaseModel):
    """Parse the provider identity identifier as a UUID at the HTTP boundary."""

    id: UUID


class WhoamiResponse(BaseModel):
    """Read the identity portion of a successful Kratos whoami response."""

    identity: IdentityResponse


class LogoutFlow(BaseModel):
    """Read the server-selected logout URL returned by a browser flow."""

    logout_url: str


@dataclass(frozen=True, slots=True)
class RegisteredHumanDTO:
    """Group the test account identity and credentials without exposing its secrets."""

    subject: IdentitySubject
    email: str
    password: str = field(repr=False)
    credential: BrowserSessionCredential


def create_browser() -> httpx2.AsyncClient:
    """Create an independent cookie jar for one browser session."""
    return httpx2.AsyncClient(
        base_url=KRATOS_PUBLIC_URL, follow_redirects=False, timeout=15.0, trust_env=False
    )


def _csrf_token(flow: BrowserFlow) -> str:
    """Require a textual CSRF input before submitting a browser form."""
    for node in flow.ui.nodes:
        if node.attributes.name == "csrf_token" and isinstance(node.attributes.value, str):
            return node.attributes.value
    raise AssertionError("Kratos did not return a browser CSRF input")


def _credential(browser: httpx2.AsyncClient) -> BrowserSessionCredential:
    """Require a session cookie after a successful browser authentication flow."""
    cookie = browser.cookies.get("ory_kratos_session")
    assert cookie is not None
    return BrowserSessionCredential(cookie)


async def register_human(browser: httpx2.AsyncClient) -> RegisteredHumanDTO:
    """Register a unique test human and capture its verified subject and session."""
    email, password = f"test-{uuid4().hex}@example.test", f"TestPassphrase-{uuid4().hex}!"
    started = await browser.get(
        "/self-service/registration/browser", headers={"Accept": "application/json"}
    )
    assert started.status_code == 200, started.text
    flow = BrowserFlow.model_validate_json(started.text)
    completed = await browser.post(
        flow.ui.action,
        data={
            "csrf_token": _csrf_token(flow),
            "traits.email": email,
            "password": password,
            "method": "password",
        },
        headers={"Accept": "application/json"},
    )
    assert completed.status_code in {200, 303}, completed.text
    whoami = await browser.get("/sessions/whoami")
    assert whoami.status_code == 200, whoami.text
    subject = IdentitySubject(str(WhoamiResponse.model_validate_json(whoami.text).identity.id))
    return RegisteredHumanDTO(subject, email, password, _credential(browser))


async def login_human(
    browser: httpx2.AsyncClient, human: RegisteredHumanDTO
) -> BrowserSessionCredential:
    """Authenticate an existing test human in an independent browser session."""
    started = await browser.get(
        "/self-service/login/browser", headers={"Accept": "application/json"}
    )
    assert started.status_code == 200, started.text
    flow = BrowserFlow.model_validate_json(started.text)
    completed = await browser.post(
        flow.ui.action,
        data={
            "csrf_token": _csrf_token(flow),
            "identifier": human.email,
            "password": human.password,
            "method": "password",
        },
        headers={"Accept": "application/json"},
    )
    assert completed.status_code in {200, 303}, completed.text
    return _credential(browser)


async def logout_human(browser: httpx2.AsyncClient) -> None:
    """Complete the real browser logout flow and verify the session is revoked."""
    started = await browser.get(
        "/self-service/logout/browser", headers={"Accept": "application/json"}
    )
    assert started.status_code == 200, started.text
    flow = LogoutFlow.model_validate_json(started.text)
    completed = await browser.get(flow.logout_url, headers={"Accept": "application/json"})
    assert completed.status_code == 204, completed.text
    assert (await browser.get("/sessions/whoami")).status_code == 401
