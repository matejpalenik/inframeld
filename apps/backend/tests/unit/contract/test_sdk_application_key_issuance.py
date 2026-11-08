"""Qualify registered issuance wire alternatives without SQL or provider simulation."""

from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from tests.support.sdk_conformance_app import create_sdk_conformance_app

_PROJECT = "00000000-0000-4000-8000-000000000003"
_APPLICATION = "00000000-0000-4000-8000-000000000008"
_ROUTE = f"/v1/projects/{_PROJECT}/application-accounts/{_APPLICATION}/keys"


@pytest.mark.parametrize("cookie", [False, True])
@pytest.mark.parametrize("replay", [False, True])
def test_issuance_fixture_exposes_first_or_safe_original_and_independent_wire_evidence(
    cookie: bool, replay: bool
) -> None:
    key = "sdk-key-replay" if replay else "sdk-key-first"
    headers = {"Idempotency-Key": key, "X-SDK-Test": "issuance-call"}
    if cookie:
        headers |= {
            "Cookie": "ory_kratos_session=sdk-cookie",
            "Origin": "https://account.test",
            "X-Inframeld-CSRF": "1",
        }
    else:
        headers["Authorization"] = "Bearer sdk-human"
    body = {"allowedAdapters": ["mcp", "http"], "expectedAccessRevision": 7}
    with TestClient(create_sdk_conformance_app()) as client:
        client.post(
            "/sdk-control/cases/issuance-fixture",
            json={"calls": {"issuance-call": {"kind": "none"}}},
        )
        response = client.post(_ROUTE, json=body, headers=headers)
        seen = client.get("/sdk-control/cases/issuance-fixture").json()
    assert response.status_code == 201
    value = response.json()
    assert value["secretAvailable"] is (not replay)
    assert ("key" in value) is (not replay)
    assert value["metadata"]["allowedAdapters"] == ["mcp", "http"]
    assert value["metadata"]["applicationPrincipalId"] == _APPLICATION
    assert value["accessRevision"] == 8
    assert response.headers["cache-control"] == "no-store"
    assert UUID(response.headers["x-request-id"])
    assert seen["counts"] == {"issuance-call": 1}
    witness = seen["observations"]["issuance-call"]
    assert (witness["method"], witness["path"], witness["query"], witness["jsonBody"]) == (
        "POST",
        _ROUTE,
        "",
        body,
    )
    assert witness["headers"]["idempotency-key"] == key
    assert witness["authorization"] == ("" if cookie else "Bearer sdk-human")
    assert witness["headers"].get("cookie", "") == (
        "ory_kratos_session=sdk-cookie" if cookie else ""
    )


@pytest.mark.parametrize(
    ("authorization", "status"),
    [
        (None, 401),
        ("Bearer wrong-human", 401),
        ("Bearer sdk-denied", 403),
        ("Bearer sdk-unavailable", 503),
        ("Bearer ifm_app_00000000-0000-4000-8000-000000000003_" + "A" * 43, 403),
    ],
)
def test_issuance_fixture_uses_ordinary_family_dispatch_and_safe_errors(
    authorization: str | None, status: int
) -> None:
    headers = {"Idempotency-Key": "sdk-key-first"}
    if authorization is not None:
        headers["Authorization"] = authorization
    with TestClient(create_sdk_conformance_app()) as client:
        response = client.post(
            _ROUTE,
            json={"allowedAdapters": ["http"], "expectedAccessRevision": 7},
            headers=headers,
        )
    assert response.status_code == status
    assert "key" not in response.json() and "metadata" not in response.json()
    assert response.headers["cache-control"] == "no-store"
