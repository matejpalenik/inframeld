"""Qualify controlled safe receipts and independent wire evidence without SQL or providers."""

from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from tests.support.sdk_conformance_app import create_sdk_conformance_app

_PROJECT = "00000000-0000-4000-8000-000000000003"
_APPLICATION = "00000000-0000-4000-8000-000000000008"
_KEY = "00000000-0000-4000-8000-000000000010"
_ROUTE = f"/v1/projects/{_PROJECT}/application-accounts/{_APPLICATION}/keys/{_KEY}/revoke"


@pytest.mark.parametrize("cookie", [False, True])
@pytest.mark.parametrize("intent", ["first", "replay", "noop"])
def test_revocation_fixture_exposes_safe_receipt_and_exact_independent_wire_evidence(
    cookie: bool, intent: str
) -> None:
    key = f"sdk-revoke-{intent}"
    headers = {"Idempotency-Key": key, "X-SDK-Test": "revocation-call"}
    if cookie:
        headers |= {
            "Cookie": "ory_kratos_session=sdk-cookie",
            "Origin": "https://account.test",
            "X-Inframeld-CSRF": "1",
        }
    else:
        headers["Authorization"] = "Bearer sdk-human"
    body = {"expectedAccessRevision": 8 if intent == "noop" else 7}
    with TestClient(create_sdk_conformance_app()) as client:
        client.post(
            "/sdk-control/cases/revocation-fixture",
            json={"calls": {"revocation-call": {"kind": "none"}}},
        )
        before = client.get("/sdk-control/counts").json()["_total"]
        response = client.post(_ROUTE, json=body, headers=headers)
        seen = client.get("/sdk-control/cases/revocation-fixture").json()
        after = client.get("/sdk-control/counts").json()["_total"]
    assert response.status_code == 200
    value = response.json()
    assert set(value) == {"operationId", "accessRevision", "idempotencyExpiresAt", "metadata"}
    assert value["accessRevision"] == 8
    assert value["operationId"] == (
        "sdk-application-key-revoke-noop" if intent == "noop" else "sdk-application-key-revoke"
    )
    assert value["metadata"] == {
        "keyId": _KEY,
        "applicationPrincipalId": _APPLICATION,
        "projectId": _PROJECT,
        "prefix": "ifm_app_",
        "allowedAdapters": ["http", "mcp"],
        "createdAt": "2029-12-31T00:00:00Z",
        "expiresAt": "2030-03-31T00:00:00Z",
        "revokedAt": "2030-01-01T00:00:00Z",
    }
    assert response.headers["cache-control"] == "no-store"
    assert UUID(response.headers["x-request-id"])
    assert seen["counts"] == {"revocation-call": 1} and after - before == 1
    witness = seen["observations"]["revocation-call"]
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
    "authorization,status,code",
    [
        (None, 401, "http_error"),
        ("Bearer wrong-human", 401, "http_error"),
        ("Bearer sdk-denied", 403, "access_denied"),
        ("Bearer sdk-unavailable", 503, "dependency_unavailable"),
        ("Bearer ifm_app_00000000-0000-4000-8000-000000000003_" + "A" * 43, 403, "access_denied"),
    ],
)
def test_revocation_fixture_preserves_family_errors_without_receipt_disclosure(
    authorization: str | None, status: int, code: str
) -> None:
    headers = {"Idempotency-Key": "sdk-revoke-first"}
    if authorization is not None:
        headers["Authorization"] = authorization
    with TestClient(create_sdk_conformance_app()) as client:
        response = client.post(_ROUTE, json={"expectedAccessRevision": 7}, headers=headers)
    assert response.status_code == status
    assert response.json()["status"] == status and response.json()["code"] == code
    assert "metadata" not in response.json() and "key" not in response.json()
    assert response.headers["cache-control"] == "no-store"
    if status == 401:
        assert response.headers["www-authenticate"] == (
            'Bearer realm="inframeld", error="invalid_token"'
            if authorization
            else 'Bearer realm="inframeld"'
        )


@pytest.mark.parametrize("wrong", ["revision", "project", "application", "key"])
def test_revocation_fixture_preserves_stale_or_hidden_target_errors(wrong: str) -> None:
    route = _ROUTE
    if wrong != "revision":
        route = route.replace(
            {"project": _PROJECT, "application": _APPLICATION, "key": _KEY}[wrong],
            str(UUID(int=999)),
        )
    with TestClient(create_sdk_conformance_app()) as client:
        response = client.post(
            route,
            json={"expectedAccessRevision": 6 if wrong == "revision" else 7},
            headers={"Authorization": "Bearer sdk-human", "Idempotency-Key": "sdk-revoke-first"},
        )
    assert response.status_code == (409 if wrong == "revision" else 404)
    assert response.json()["code"] == (
        "stale_revision" if wrong == "revision" else "resource_not_found"
    )
    assert "metadata" not in response.json()


def test_revocation_fixture_cookie_csrf_denial_precedes_the_controlled_revoker() -> None:
    with TestClient(create_sdk_conformance_app()) as client:
        response = client.post(
            _ROUTE,
            json={"expectedAccessRevision": 7},
            headers={
                "Cookie": "ory_kratos_session=sdk-cookie",
                "Idempotency-Key": "sdk-revoke-first",
            },
        )
    assert response.status_code == 403 and response.json()["code"] == "access_denied"
    assert "metadata" not in response.json()
