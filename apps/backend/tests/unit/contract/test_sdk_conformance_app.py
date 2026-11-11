"""Qualify the isolated HTTP fixture before SDKs consume it."""

import base64
from urllib.parse import parse_qs
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from tests.support.project_creation_scenarios import INITIAL_ACTIONS
from tests.support.sdk_conformance_app import create_sdk_conformance_app


def _application_key(suffix: str) -> str:
    return "ifm_app_00000000-0000-4000-8000-" + suffix + "_" + "A" * 43


def test_application_session_fixture_has_exact_identity_and_independent_header_only_witness() -> (
    None
):
    key = _application_key("000000000003")
    with TestClient(create_sdk_conformance_app()) as client:
        client.post(
            "/sdk-control/cases/application-session",
            json={"calls": {"app-identity": {"kind": "none"}}},
        )
        response = client.get(
            "/v1/application-session",
            headers={"Authorization": "Bearer " + key, "X-SDK-Test": "app-identity"},
        )
        witness = client.get("/sdk-control/cases/application-session").json()
        totals = client.get("/sdk-control/counts").json()
    assert response.status_code == 200
    assert response.json() == {
        "principalId": "00000000-0000-4000-8000-000000000008",
        "projectId": "00000000-0000-4000-8000-000000000003",
    }
    assert response.headers["cache-control"] == "no-store"
    assert UUID(response.headers["x-request-id"])
    assert witness["counts"] == {"app-identity": 1} and totals == {"_total": 1}
    seen = witness["observations"]["app-identity"]
    assert (
        seen["method"],
        seen["path"],
        seen["query"],
        seen["rawBodyBase64"],
        seen["authorization"],
    ) == ("GET", "/v1/application-session", "", "", "Bearer " + key)
    assert "idempotency-key" not in seen["headers"] and "jsonBody" not in seen


@pytest.mark.parametrize(
    ("headers", "status", "code"),
    [
        ({}, 401, "http_error"),
        ({"Authorization": "Bearer sdk-human"}, 401, "http_error"),
        ({"Cookie": "ory_kratos_session=sdk-cookie"}, 401, "http_error"),
        ({"Authorization": "Bearer " + _application_key("000000000099")}, 401, "http_error"),
        ({"Authorization": "Bearer " + _application_key("000000000004")}, 403, "access_denied"),
        (
            {"Authorization": "Bearer " + _application_key("000000000005")},
            503,
            "dependency_unavailable",
        ),
        ({"Authorization": "Bearer " + _application_key("000000000007")}, 401, "http_error"),
        ({"Authorization": "Bearer " + _application_key("000000000009")}, 403, "access_denied"),
        (
            {
                "Authorization": "Bearer " + _application_key("000000000003"),
                "Cookie": "ory_kratos_session=sdk-cookie",
            },
            400,
            "invalid_authentication_request",
        ),
    ],
)
def test_application_session_fixture_keeps_safe_authentication_outcomes(
    headers: dict[str, str], status: int, code: str
) -> None:
    with TestClient(create_sdk_conformance_app()) as client:
        response = client.get("/v1/application-session", headers=headers)
    assert response.status_code == status and response.json()["code"] == code
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-request-id"] == response.json()["requestId"]
    assert "ifm_app_" not in response.text
    if status == 401:
        assert response.headers["www-authenticate"].startswith('Bearer realm="inframeld"')


def test_application_session_fixture_reuses_no_prior_credential_and_keeps_human_identity_exclusive() -> (
    None
):
    with TestClient(create_sdk_conformance_app()) as client:
        first = client.get(
            "/v1/application-session",
            headers={"Authorization": "Bearer " + _application_key("000000000003")},
        )
        replacement = client.get(
            "/v1/application-session",
            headers={"Authorization": "Bearer " + _application_key("000000000006")},
        )
        anonymous = client.get("/v1/application-session")
        human = client.get(
            "/v1/session", headers={"Authorization": "Bearer " + _application_key("000000000003")}
        )
    assert first.status_code == replacement.status_code == 200
    assert replacement.json() == first.json()
    assert anonymous.status_code == human.status_code == 401


@pytest.mark.parametrize(
    "credential",
    [
        {"Authorization": "Bearer sdk-human"},
        {"Cookie": "ory_kratos_session=sdk-cookie"},
    ],
)
def test_own_project_access_fixture_exposes_real_target_shapes_and_reviewed_revision(
    credential: dict[str, str],
) -> None:
    project = "00000000-0000-4000-8000-000000000003"
    with TestClient(create_sdk_conformance_app()) as client:
        response = client.get(f"/v1/projects/{project}/my-access", headers=credential)
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    body = response.json()
    assert (
        body["projectId"] == project
        and body["principalId"] == "00000000-0000-4000-8000-000000000001"
    )
    assert body["accessRevision"] == 7 and body["nextCursor"] is None
    assert [grant["target"]["kind"] for grant in body["grants"]] == [
        "project",
        "access-group",
        "application-account",
    ]
    assert [grant["canGrant"] for grant in body["grants"]] == [True, False, True]
    assert (
        body["groupMemberships"]
        == body["groupManagements"]
        == [{"accessGroupId": "00000000-0000-4000-8000-000000000007"}]
    )


def test_own_project_access_fixture_uses_one_combined_page_and_independent_get_witnesses() -> None:
    path = "/v1/projects/00000000-0000-4000-8000-000000000003/my-access"
    headers = {"Authorization": "Bearer sdk-human"}
    with TestClient(create_sdk_conformance_app()) as client:
        client.post(
            "/sdk-control/cases/own-access-wire",
            json={"calls": {"own-first": {"kind": "none"}, "own-next": {"kind": "none"}}},
        )
        first = client.get(path, params={"limit": 1}, headers=headers | {"X-SDK-Test": "own-first"})
        assert first.status_code == 200
        body = first.json()
        assert (
            len(body["grants"]) == 1 and body["groupMemberships"] == body["groupManagements"] == []
        )
        cursor = body["nextCursor"]
        assert isinstance(cursor, str)
        second = client.get(
            path,
            params={"limit": 4, "cursor": cursor},
            headers=headers | {"X-SDK-Test": "own-next"},
        )
        evidence = client.get("/sdk-control/cases/own-access-wire").json()
        denied = client.get(
            path, params={"cursor": cursor}, headers={"Authorization": "Bearer sdk-denied"}
        )
    assert second.status_code == 200 and second.json()["nextCursor"] is None
    assert (
        len(second.json()["grants"]) == 2
        and len(second.json()["groupMemberships"]) == len(second.json()["groupManagements"]) == 1
    )
    assert denied.status_code == 403 and denied.json()["code"] == "access_denied"
    assert evidence["counts"] == {"own-first": 1, "own-next": 1}
    for witness in evidence["observations"].values():
        assert (
            witness["method"] == "GET"
            and witness["path"] == path
            and witness["rawBodyBase64"] == ""
        )
        assert "idempotency-key" not in witness["headers"] and not witness["csrf"]
    assert parse_qs(evidence["observations"]["own-next"]["query"]) == {
        "limit": ["4"],
        "cursor": [cursor],
    }


@pytest.mark.parametrize(
    "suffix,query,status,code",
    [
        ("000000000099", {}, 404, "resource_not_found"),
        ("000000000003", {"cursor": "malformed_cursor"}, 422, "invalid_input"),
        ("000000000003", {"actionId": "inspect-budget"}, 422, "invalid_input"),
    ],
)
def test_own_project_access_fixture_preserves_scoped_and_query_problems(
    suffix: str, query: dict[str, str], status: int, code: str
) -> None:
    with TestClient(create_sdk_conformance_app()) as client:
        response = client.get(
            f"/v1/projects/00000000-0000-4000-8000-{suffix}/my-access",
            params=query,
            headers={"Authorization": "Bearer sdk-human"},
        )
    assert response.status_code == status and response.json()["code"] == code
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "method,recipient,level,status,changed",
    [
        ("PUT", "000000000004", False, 201, True),
        ("PUT", "000000000004", True, 201, True),
        ("PUT", "000000000005", False, 200, False),
        ("PUT", "000000000006", False, 200, True),
        ("DELETE", "000000000004", None, 200, True),
        ("DELETE", "000000000005", None, 200, False),
    ],
)
def test_full_project_grant_fixture_preserves_original_outcome_and_wire_inputs(
    method: str, recipient: str, level: bool | None, status: int, changed: bool
) -> None:
    project = "00000000-0000-4000-8000-000000000003"
    principal = f"00000000-0000-4000-8000-{recipient}"
    path = f"/v1/projects/{project}/grants/{principal}/inspect-budget"
    headers = {
        "Authorization": "Bearer sdk-human",
        "Idempotency-Key": "sdk-project-grant-key",
        "X-SDK-Test": "grant-change-wire",
    }
    with TestClient(create_sdk_conformance_app()) as client:
        client.post(
            "/sdk-control/cases/grant-change-wire",
            json={"calls": {"grant-change-wire": {"kind": "none"}}},
        )
        response = client.request(
            method,
            path,
            json={"canGrant": level, "expectedAccessRevision": 7} if method == "PUT" else None,
            params={"expectedAccessRevision": 7} if method == "DELETE" else None,
            headers=headers,
        )
        witness = client.get("/sdk-control/cases/grant-change-wire").json()["observations"][
            "grant-change-wire"
        ]
    assert response.status_code == status and response.headers["cache-control"] == "no-store"
    body = response.json()
    assert (
        body["projectId"],
        body["recipientPrincipalId"],
        body["actionId"],
        body["accessRevision"],
        body["changed"],
    ) == (project, principal, "inspect-budget", 7 + int(changed), changed)
    assert body["idempotencyExpiresAt"] == "2030-01-01T00:00:00Z"
    assert witness["method"] == method and witness["path"] == path
    assert witness["headers"]["idempotency-key"] == "sdk-project-grant-key"
    if method == "PUT":
        assert body["canGrant"] is level
        assert (
            witness["jsonBody"] == {"canGrant": level, "expectedAccessRevision": 7}
            and witness["query"] == ""
        )
    else:
        assert body["removed"] is True and "canGrant" not in body
        assert parse_qs(witness["query"]) == {"expectedAccessRevision": ["7"]}
        assert witness["rawBodyBase64"] == "" and "jsonBody" not in witness


@pytest.mark.parametrize(
    "action,recipient,revision,status,code",
    [
        ("inspect-feedback", "000000000004", 7, 403, "access_denied"),
        ("inspect-budget", "000000000007", 7, 409, "conflict"),
        ("inspect-budget", "000000000008", 7, 422, "invalid_input"),
        ("inspect-budget", "000000000004", 6, 409, "stale_revision"),
        ("inspect-budget", "000000000099", 7, 404, "resource_not_found"),
    ],
)
def test_full_project_grant_fixture_preserves_actor_input_recipient_and_revision_problems(
    action: str, recipient: str, revision: int, status: int, code: str
) -> None:
    with TestClient(create_sdk_conformance_app()) as client:
        response = client.put(
            f"/v1/projects/00000000-0000-4000-8000-000000000003/grants/00000000-0000-4000-8000-{recipient}/{action}",
            json={"canGrant": False, "expectedAccessRevision": revision},
            headers={
                "Authorization": "Bearer sdk-human",
                "Idempotency-Key": "sdk-project-grant-key",
            },
        )
    assert response.status_code == status and response.json()["code"] == code
    assert (
        response.headers["content-type"] == "application/problem+json"
        and response.headers["cache-control"] == "no-store"
    )


@pytest.mark.parametrize(
    "query", ["", "expectedAccessRevision=01", "expectedAccessRevision=7&expectedAccessRevision=7"]
)
def test_full_project_grant_fixture_keeps_canonical_delete_query_validation(query: str) -> None:
    with TestClient(create_sdk_conformance_app()) as client:
        response = client.delete(
            "/v1/projects/00000000-0000-4000-8000-000000000003/grants/00000000-0000-4000-8000-000000000004/inspect-budget?"
            + query,
            headers={
                "Authorization": "Bearer sdk-human",
                "Idempotency-Key": "sdk-project-grant-key",
            },
        )
    assert response.status_code == 422 and response.headers["cache-control"] == "no-store"


def test_full_project_grant_fixture_uses_cookie_csrf_and_strict_boolean_validation() -> None:
    path = "/v1/projects/00000000-0000-4000-8000-000000000003/grants/00000000-0000-4000-8000-000000000004/inspect-budget"
    cookie = {"Cookie": "ory_kratos_session=sdk-cookie", "Idempotency-Key": "sdk-project-grant-key"}
    with TestClient(create_sdk_conformance_app()) as client:
        denied = client.put(
            path, json={"canGrant": False, "expectedAccessRevision": 7}, headers=cookie
        )
        allowed = client.put(
            path,
            json={"canGrant": False, "expectedAccessRevision": 7},
            headers=cookie | {"Origin": "https://account.test", "X-Inframeld-CSRF": "1"},
        )
        invalid = client.put(
            path,
            json={"canGrant": "false", "expectedAccessRevision": 7},
            headers={
                "Authorization": "Bearer sdk-human",
                "Idempotency-Key": "sdk-project-grant-key",
            },
        )
    assert denied.status_code == 403 and denied.json()["code"] == "access_denied"
    assert allowed.status_code == 201 and invalid.status_code == 422


@pytest.mark.parametrize(
    "method,principal,status,changed",
    [
        ("PUT", "00000000-0000-4000-8000-000000000004", 201, True),
        ("PUT", "00000000-0000-4000-8000-000000000005", 200, False),
        ("DELETE", "00000000-0000-4000-8000-000000000004", 200, True),
        ("DELETE", "00000000-0000-4000-8000-000000000005", 200, False),
    ],
)
def test_project_membership_fixture_preserves_bodyless_delete_query_and_original_receipt(
    method: str, principal: str, status: int, changed: bool
) -> None:
    project = "00000000-0000-4000-8000-000000000003"
    route = f"/v1/projects/{project}/members/{principal}"
    headers = {
        "Authorization": "Bearer sdk-human",
        "Idempotency-Key": "sdk-membership-key",
        "X-SDK-Test": "membership-wire",
    }
    with TestClient(create_sdk_conformance_app()) as client:
        client.post(
            "/sdk-control/cases/membership-wire",
            json={"calls": {"membership-wire": {"kind": "none"}}},
        )
        response = client.request(
            method,
            route,
            headers=headers,
            json={"expectedAccessRevision": 7} if method == "PUT" else None,
            params={"expectedAccessRevision": 7} if method == "DELETE" else None,
        )
        assert response.status_code == status
        body = response.json()
        assert body["projectId"] == project and body["principalId"] == principal
        assert body["changed"] is changed and body["accessRevision"] == 7 + int(changed)
        assert body["member" if method == "PUT" else "removed"] is True
        assert body["idempotencyExpiresAt"] == "2030-01-01T00:00:00Z"
        witness = client.get("/sdk-control/cases/membership-wire").json()["observations"][
            "membership-wire"
        ]
    assert response.headers["cache-control"] == "no-store"
    assert witness["method"] == method and witness["path"] == route
    assert witness["headers"]["idempotency-key"] == "sdk-membership-key"
    if method == "DELETE":
        assert parse_qs(witness["query"]) == {"expectedAccessRevision": ["7"]}
        assert witness["rawBodyBase64"] == "" and "jsonBody" not in witness
    else:
        assert witness["jsonBody"] == {"expectedAccessRevision": 7} and witness["query"] == ""


@pytest.mark.parametrize("query", ["", "expectedAccessRevision=7&expectedAccessRevision=8"])
def test_project_membership_fixture_rejects_missing_or_duplicate_delete_revision(
    query: str,
) -> None:
    with TestClient(create_sdk_conformance_app()) as client:
        response = client.delete(
            "/v1/projects/00000000-0000-4000-8000-000000000003/members/00000000-0000-4000-8000-000000000004?"
            + query,
            headers={"Authorization": "Bearer sdk-human", "Idempotency-Key": "sdk-membership-key"},
        )
    assert response.status_code == 422


@pytest.mark.parametrize(
    "identity,status,changed,revision",
    [
        ("00000000-0000-4000-8000-000000000004", 201, True, 8),
        ("00000000-0000-4000-8000-000000000005", 200, False, 7),
    ],
)
def test_human_admission_fixture_returns_typed_original_receipts_and_witnesses(
    identity: str, status: int, changed: bool, revision: int
) -> None:
    route = "/v1/organizations/00000000-0000-4000-8000-000000000002/human-admissions"
    body = {"identityId": identity, "expectedAccessRevision": 7}
    headers = {
        "Authorization": "Bearer sdk-human",
        "Idempotency-Key": "sdk-admit-key",
        "X-SDK-Test": "admission-wire",
    }
    with TestClient(create_sdk_conformance_app()) as client:
        client.post(
            "/sdk-control/cases/admission-wire",
            json={"calls": {"admission-wire": {"kind": "none"}}},
        )
        first = client.post(route, json=body, headers=headers)
        replay = client.post(route, json=body, headers=headers)
        assert first.status_code == replay.status_code == status
        assert (
            first.json()
            == replay.json()
            == {
                "operationId": "sdk-human-admission",
                "idempotencyExpiresAt": "2030-01-01T00:00:00Z",
                "organizationId": "00000000-0000-4000-8000-000000000002",
                "principalId": identity,
                "accessRevision": revision,
                "changed": changed,
            }
        )
        witness = client.get("/sdk-control/cases/admission-wire").json()["observations"][
            "admission-wire"
        ]
    assert first.headers["cache-control"] == replay.headers["cache-control"] == "no-store"
    assert witness["method"] == "POST" and witness["path"] == route
    assert witness["jsonBody"] == body
    assert witness["headers"]["idempotency-key"] == "sdk-admit-key"
    assert not witness["csrf"]


@pytest.mark.parametrize(
    "case,status,code",
    [
        ("csrf", 403, "access_denied"),
        ("missing", 401, "http_error"),
        ("application-key", 401, "http_error"),
        ("forbidden", 403, "access_denied"),
        ("foreign-org", 404, "resource_not_found"),
        ("stale", 409, "stale_revision"),
        ("unavailable", 503, "dependency_unavailable"),
    ],
)
def test_human_admission_fixture_preserves_native_problem_responses(
    case: str, status: int, code: str
) -> None:
    organization = (
        "00000000-0000-4000-8000-000000000099"
        if case == "foreign-org"
        else "00000000-0000-4000-8000-000000000002"
    )
    body = {
        "identityId": "00000000-0000-4000-8000-000000000004",
        "expectedAccessRevision": 0 if case == "stale" else 7,
    }
    headers = {"Authorization": "Bearer sdk-human", "Idempotency-Key": "sdk-admit-key"}
    if case == "csrf":
        headers = {"Cookie": "ory_kratos_session=sdk-cookie", "Idempotency-Key": "sdk-admit-key"}
    elif case == "missing":
        del headers["Authorization"]
    elif case in {"application-key", "forbidden", "unavailable"}:
        token = {
            "application-key": "ifm_app_unsupported",
            "forbidden": "sdk-denied",
            "unavailable": "sdk-unavailable",
        }[case]
        headers["Authorization"] = f"Bearer {token}"
    with TestClient(create_sdk_conformance_app()) as client:
        response = client.post(
            f"/v1/organizations/{organization}/human-admissions", json=body, headers=headers
        )
    assert response.status_code == status
    assert response.json()["code"] == code
    assert response.headers["content-type"] == "application/problem+json"
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "credential",
    [{"Authorization": "Bearer sdk-human"}, {"Cookie": "ory_kratos_session=sdk-cookie"}],
)
def test_project_action_grant_fixture_returns_flat_stored_assignments(
    credential: dict[str, str],
) -> None:
    project = "00000000-0000-4000-8000-000000000003"
    with TestClient(create_sdk_conformance_app()) as client:
        response = client.get(
            f"/v1/projects/{project}/grants",
            params={"actionId": "inspect-budget"},
            headers=credential,
        )
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "items": [
            {
                "projectId": project,
                "recipientPrincipalId": "00000000-0000-4000-8000-000000000001",
                "actionId": "inspect-budget",
                "canGrant": True,
            },
            {
                "projectId": project,
                "recipientPrincipalId": "00000000-0000-4000-8000-000000000006",
                "actionId": "inspect-budget",
                "canGrant": False,
            },
        ],
        "nextCursor": None,
    }


def test_project_action_grant_fixture_pages_with_independent_bodyless_get_witnesses() -> None:
    project = "00000000-0000-4000-8000-000000000003"
    path = f"/v1/projects/{project}/grants"
    with TestClient(create_sdk_conformance_app()) as client:
        client.post(
            "/sdk-control/cases/grants-wire",
            json={"calls": {"grants-first": {"kind": "none"}, "grants-next": {"kind": "none"}}},
        )
        first = client.get(
            path,
            params={"actionId": "inspect-budget", "limit": 1},
            headers={"Authorization": "Bearer sdk-human", "X-SDK-Test": "grants-first"},
        )
        assert first.status_code == 200
        token = first.json()["nextCursor"]
        assert isinstance(token, str) and len(first.json()["items"]) == 1
        second = client.get(
            path,
            params={"actionId": "inspect-budget", "limit": 1, "cursor": token},
            headers={"Authorization": "Bearer sdk-human", "X-SDK-Test": "grants-next"},
        )
        witnesses = client.get("/sdk-control/cases/grants-wire").json()["observations"]
        mismatched = client.get(
            path,
            params={"actionId": "manage-budget", "cursor": token},
            headers={"Authorization": "Bearer sdk-human"},
        )
    assert second.status_code == 200 and second.json()["nextCursor"] is None
    assert (
        second.json()["items"][0]["recipientPrincipalId"] == "00000000-0000-4000-8000-000000000006"
    )
    assert mismatched.status_code == 422 and mismatched.json()["code"] == "invalid_input"
    for name in ("grants-first", "grants-next"):
        witness = witnesses[name]
        assert witness["method"] == "GET" and witness["path"] == path
        assert witness["rawBodyBase64"] == "" and witness["csrf"] == ""
        assert "idempotency-key" not in witness["headers"]
    assert parse_qs(witnesses["grants-next"]["query"]) == {
        "actionId": ["inspect-budget"],
        "limit": ["1"],
        "cursor": [token],
    }


@pytest.mark.parametrize(
    "action,project,cursor,status,code",
    [
        ("inspect-feedback", "000000000003", None, 403, "access_denied"),
        ("query", "000000000003", None, 422, "invalid_input"),
        ("inspect-budget", "000000000099", None, 404, "resource_not_found"),
        ("inspect-budget", "000000000003", "malformed_cursor", 422, "invalid_input"),
    ],
)
def test_project_action_grant_fixture_rejects_non_delegation_and_wrong_scope(
    action: str,
    project: str,
    cursor: str | None,
    status: int,
    code: str,
) -> None:
    query = {"actionId": action}
    if cursor is not None:
        query["cursor"] = cursor
    with TestClient(create_sdk_conformance_app()) as client:
        response = client.get(
            f"/v1/projects/00000000-0000-4000-8000-{project}/grants",
            params=query,
            headers={"Authorization": "Bearer sdk-human"},
        )
    assert response.status_code == status and response.json()["code"] == code
    assert response.headers["cache-control"] == "no-store"


def test_project_members_fixture_uses_real_router_service_and_one_explicit_page_per_request() -> (
    None
):
    project = "00000000-0000-4000-8000-000000000003"
    headers = {"Authorization": "Bearer sdk-human", "X-SDK-Test": "members-wire"}
    with TestClient(create_sdk_conformance_app()) as client:
        client.post(
            "/sdk-control/cases/members-wire", json={"calls": {"members-wire": {"kind": "none"}}}
        )
        first = client.get(f"/v1/projects/{project}/members?limit=1", headers=headers)
        assert first.status_code == 200
        first_body = first.json()
        assert first_body["projectId"] == project and first_body["accessRevision"] == 12
        assert len(first_body["items"]) == 1
        assert first_body["items"][0] == {
            "principalId": "00000000-0000-4000-8000-000000000001",
            "displayName": "SDK Human",
            "kind": "human",
        }
        assert isinstance(first_body["nextCursor"], str)
        second = client.get(
            f"/v1/projects/{project}/members",
            params={"limit": 2, "cursor": first_body["nextCursor"]},
            headers=headers,
        )
        witness = client.get("/sdk-control/cases/members-wire").json()["observations"][
            "members-wire"
        ]
    assert second.status_code == 200
    assert second.json()["items"] == [
        {
            "principalId": "00000000-0000-4000-8000-000000000005",
            "displayName": "Stored application",
            "kind": "application",
        },
        {
            "principalId": "00000000-0000-4000-8000-000000000006",
            "displayName": "Legacy\nmember 🧭",
            "kind": "human",
        },
    ]
    assert second.json()["nextCursor"] is None
    assert first.headers["cache-control"] == second.headers["cache-control"] == "no-store"
    assert witness["method"] == "GET" and witness["path"] == f"/v1/projects/{project}/members"
    assert parse_qs(witness["query"]) == {"limit": ["2"], "cursor": [first_body["nextCursor"]]}
    assert "idempotency-key" not in witness["headers"] and not witness["csrf"]


def test_project_members_fixture_cookie_read_needs_no_write_headers_and_rejects_bad_cursor() -> (
    None
):
    path = "/v1/projects/00000000-0000-4000-8000-000000000003/members"
    headers = {"Cookie": "ory_kratos_session=sdk-cookie"}
    with TestClient(create_sdk_conformance_app()) as client:
        response = client.get(path, headers=headers)
        assert response.status_code == 200 and len(response.json()["items"]) == 3
        assert response.json()["nextCursor"] is None
        invalid = client.get(path, params={"cursor": "malformed_cursor"}, headers=headers)
        missing = client.get(path.replace("000000000003", "000000000099"), headers=headers)
    assert invalid.status_code == 422 and invalid.json()["code"] == "invalid_input"
    assert missing.status_code == 404 and missing.json()["code"] == "resource_not_found"
    assert invalid.headers["cache-control"] == missing.headers["cache-control"] == "no-store"


def test_response_variants_preserve_status_and_representation_pairs() -> None:
    with TestClient(create_sdk_conformance_app()) as client:
        ready = client.get("/contract-fixture/variants")
        accepted = client.get("/contract-fixture/variants", params={"mode": "accepted"})
        ordinary = client.get("/contract-fixture/media")
        vendor = client.get(
            "/contract-fixture/media", headers={"Accept": "application/vnd.inframeld.job+json"}
        )

    assert ready.status_code == 200
    assert ready.json() == {"value": "ready"}
    assert accepted.status_code == 202
    assert accepted.json() == {"jobId": "job-123"}
    assert ordinary.json() == {"value": "ready"}
    assert vendor.headers["content-type"] == "application/vnd.inframeld.job+json"
    assert vendor.json() == {"jobId": "job-123"}


def test_mixed_bodyless_default_and_nullable_representations() -> None:
    with TestClient(create_sdk_conformance_app()) as client:
        fallback = client.get("/contract-fixture/variants", params={"mode": "fallback"})
        empty = client.get("/contract-fixture/variants", params={"mode": "empty"})

    assert fallback.status_code == 201
    assert fallback.json() == {"jobId": "job-123"}
    assert empty.status_code == 204
    assert empty.content == b""


def test_bodyless_primary_keeps_default_media_alternatives() -> None:
    with TestClient(create_sdk_conformance_app()) as client:
        ready = client.get("/contract-fixture/fallback")
        vendor = client.get(
            "/contract-fixture/fallback", headers={"Accept": "application/vnd.inframeld.job+json"}
        )
        empty = client.get("/contract-fixture/fallback", params={"mode": "empty"})

    assert ready.status_code == 201 and ready.json() == {"value": "ready"}
    assert vendor.status_code == 202 and vendor.json() == {"jobId": "job-123"}
    assert empty.status_code == 204 and empty.content == b""


def test_json_fault_honors_its_declared_content_type() -> None:
    with TestClient(create_sdk_conformance_app()) as client:
        client.post(
            "/sdk-control/cases/problem",
            json={
                "calls": {
                    "problem": {
                        "kind": "json",
                        "status": 422,
                        "body": {"title": "reviewed"},
                        "contentType": "application/problem+json",
                    }
                }
            },
        )
        response = client.get("/health", headers={"X-SDK-Test": "problem"})

    assert response.headers["content-type"] == "application/problem+json"
    assert response.json() == {"title": "reviewed"}


def test_raw_fault_preserves_bytes_representation_and_repeated_headers() -> None:
    with TestClient(create_sdk_conformance_app()) as client:
        client.post(
            "/sdk-control/cases/raw",
            json={
                "calls": {
                    "raw": {
                        "kind": "raw",
                        "status": 200,
                        "bodyBase64": "/w==",
                        "contentType": "application/octet-stream",
                        "headers": [["Set-Cookie", "a=1"], ["Set-Cookie", "b=2"]],
                    }
                }
            },
        )
        response = client.get("/health", headers={"X-SDK-Test": "raw"})

    assert response.content == b"\xff"
    assert response.headers["content-type"] == "application/octet-stream"
    assert response.headers.get_list("set-cookie") == ["a=1", "b=2"]


def test_nullable_and_bodyless_fixture_operations_have_distinct_wire_results() -> None:
    with TestClient(create_sdk_conformance_app()) as client:
        nullable = client.get("/contract-fixture/nullable")
        empty = client.get("/contract-fixture/empty")

    assert nullable.status_code == 200
    assert nullable.content == b"null"
    assert empty.status_code == 204
    assert empty.content == b""


def test_dispatch_totals_include_requests_that_lose_the_sdk_witness_header() -> None:
    with TestClient(create_sdk_conformance_app()) as client:
        client.post("/sdk-control/cases/tagged", json={"calls": {"tagged": {"kind": "none"}}})
        client.get("/health", headers={"X-SDK-Test": "tagged"})
        client.get("/health")
        counts = client.get("/sdk-control/counts").json()

    assert counts == {"_total": 2}
    assert counts.get("_total") == 2


def test_witness_retains_consent_fields_independently_of_the_fixed_handler_result() -> None:
    body = {"consentChallenge": "a+b&/", "decision": "deny", "remember": False}
    with TestClient(create_sdk_conformance_app()) as client:
        client.post(
            "/sdk-control/cases/consent-wire", json={"calls": {"consent-wire": {"kind": "none"}}}
        )
        response = client.post(
            "/v1/oauth/consent",
            json=body,
            headers={
                "Cookie": "ory_kratos_session=sdk-cookie",
                "Origin": "https://account.test",
                "X-Inframeld-CSRF": "1",
                "X-SDK-Test": "consent-wire",
            },
        )
        witness = client.get("/sdk-control/cases/consent-wire").json()["observations"][
            "consent-wire"
        ]

    assert response.status_code == 200
    assert witness.get("jsonBody") == body
    assert witness.get("status") == 200
    assert witness.get("headers", {}).get("x-inframeld-csrf") == "1"


def test_faults_are_explicit_and_isolated_from_case_names_and_other_requests() -> None:
    with TestClient(create_sdk_conformance_app()) as client:
        client.post("/sdk-control/cases/malformed", json={"calls": {"malformed": {"kind": "none"}}})
        configured = client.post(
            "/sdk-control/cases/arbitrary-name",
            json={"calls": {"arbitrary-name": {"kind": "json", "body": {"wrong": True}}}},
        )
        fault = client.get("/health", headers={"X-SDK-Test": "arbitrary-name"})
        healthy = client.get("/health", headers={"X-SDK-Test": "malformed"})

    assert configured.status_code == 200
    assert fault.json() == {"wrong": True}
    assert healthy.json() == {"status": "ok"}


def test_upload_witness_records_fastapi_file_bytes_without_transfer_decoding() -> None:
    encoded = b"AHNkay1iaW5hcnn/"
    with TestClient(create_sdk_conformance_app()) as client:
        client.post(
            "/sdk-control/cases/encoded-upload",
            json={"calls": {"encoded-upload": {"kind": "none"}}},
        )
        result = client.post(
            "/contract-fixture/upload",
            files={
                "file": (
                    "encoded.bin",
                    encoded,
                    "application/octet-stream",
                    {"Content-Transfer-Encoding": "base64"},
                )
            },
            data={"label": "sdk-label"},
            headers={"X-SDK-Test": "encoded-upload"},
        )
        witness = client.get("/sdk-control/cases/encoded-upload").json()["observations"][
            "encoded-upload"
        ]

    assert result.status_code == 200
    assert witness["fileBase64"] == base64.b64encode(encoded).decode()


def test_witness_records_exact_upload_and_dispatch_identity() -> None:
    with TestClient(create_sdk_conformance_app()) as client:
        client.post(
            "/sdk-control/cases/exact-upload", json={"calls": {"exact-upload": {"kind": "none"}}}
        )
        result = client.post(
            "/contract-fixture/upload",
            files={"file": ("sdk-upload.bin", b"\0sdk-binary\xff")},
            data={"label": "sdk-label"},
            headers={"X-SDK-Test": "exact-upload"},
        )
        witness = client.get("/sdk-control/cases/exact-upload").json()["observations"][
            "exact-upload"
        ]

    assert result.status_code == 200
    assert witness["fileBase64"] == "AHNkay1iaW5hcnn/"
    assert witness["fileName"] == "sdk-upload.bin"
    assert witness["method"] == "POST"
    assert witness["path"] == "/contract-fixture/upload"


def test_session_uses_real_dispatch_for_bearer_cookie_and_competing_credentials() -> None:
    with TestClient(create_sdk_conformance_app()) as client:
        bearer = client.get("/v1/session", headers={"Authorization": "Bearer sdk-human"})
        cookie = client.get("/v1/session", headers={"Cookie": "ory_kratos_session=sdk-cookie"})
        competing = client.get(
            "/v1/session",
            headers={
                "Authorization": "Bearer sdk-human",
                "Cookie": "ory_kratos_session=sdk-cookie",
            },
        )

    assert bearer.status_code == cookie.status_code == 200
    assert bearer.json() == cookie.json() == {"principalId": "00000000-0000-4000-8000-000000000001"}
    assert competing.status_code == 400
    assert competing.json()["code"] == "invalid_authentication_request"


def test_real_consent_and_current_grant_routes_preserve_csrf_and_request_validation() -> None:
    cookie = {"Cookie": "ory_kratos_session=sdk-cookie"}
    write = cookie | {"Origin": "https://account.test", "X-Inframeld-CSRF": "1"}
    consent = {"consentChallenge": "a+b&/", "decision": "allow", "remember": True}
    grant = {"canGrant": True, "expectedAccessRevision": 7}
    with TestClient(create_sdk_conformance_app()) as client:
        assert client.get("/health").json() == {"status": "ok"}
        assert (
            client.get(
                "/v1/oauth/consent", params={"consent_challenge": "a+b&/"}, headers=cookie
            ).status_code
            == 200
        )
        assert client.post("/v1/oauth/consent", json=consent, headers=cookie).status_code == 403
        assert client.post("/v1/oauth/consent", json=consent, headers=write).status_code == 200
        url = "/v1/projects/00000000-0000-4000-8000-000000000003/grants"
        retired = client.post(
            url,
            json={
                "recipientPrincipalId": "00000000-0000-4000-8000-000000000004",
                "actionId": "create-access-groups",
                "expectedAccessRevision": 0,
            },
            headers=write | {"Idempotency-Key": "old-original"},
        )
        assert retired.status_code == 405
        target = url + "/00000000-0000-4000-8000-000000000004/create-access-groups"
        result = client.put(
            target, json=grant, headers=write | {"Idempotency-Key": "sdk-project-grant-key"}
        )
        assert result.status_code == 201 and result.json()["canGrant"] is True
        assert result.json()["accessRevision"] == 8
        invalid = client.put(
            url + "/invalid/create-access-groups",
            json=grant,
            headers=write | {"Idempotency-Key": "sdk-project-grant-key"},
        )
        assert invalid.status_code == 422
        assert invalid.headers["content-type"] == "application/problem+json"


def test_fault_injection_counts_effects_without_changing_the_public_schema() -> None:
    application = create_sdk_conformance_app()
    with TestClient(application) as client:
        client.post("/sdk-control/cases/decode", json={"calls": {"decode": {"kind": "malformed"}}})
        response = client.get("/v1/session", headers={"X-SDK-Test": "decode"})
        assert response.status_code == 200
        assert response.content == b"{"
        assert response.headers["x-request-id"] == "00000000-0000-4000-8000-000000000099"
        assert client.get("/sdk-control/cases/decode").json()["counts"]["decode"] == 1

    assert not any(path.startswith("/sdk-control") for path in application.openapi()["paths"])


def test_upload_observer_preserves_the_actual_file_bytes_and_filename() -> None:
    with TestClient(create_sdk_conformance_app()) as client:
        client.post("/sdk-control/cases/upload", json={"calls": {"upload": {"kind": "none"}}})
        response = client.post(
            "/contract-fixture/upload",
            headers={"X-SDK-Test": "upload"},
            files={"file": ("sdk-upload.bin", b"\0sdk-binary\xff", "application/octet-stream")},
            data={"label": "sdk-label"},
        )
        assert response.status_code == 200
        observed = client.get("/sdk-control/cases/upload").json()["observations"]["upload"]
        assert observed["fileBase64"] == "AHNkay1iaW5hcnn/"
        assert observed["fileName"] == "sdk-upload.bin"


def test_payload_observer_distinguishes_omitted_values_from_explicit_null() -> None:
    body = {"required_name": "valid", "required_nullable": None, "score": 0.5, "choice": 7}
    with TestClient(create_sdk_conformance_app()) as client:
        client.post(
            "/sdk-control/cases/optional-absent",
            json={"calls": {"optional-absent": {"kind": "none"}}},
        )
        client.post(
            "/sdk-control/cases/optional-null", json={"calls": {"optional-null": {"kind": "none"}}}
        )
        assert (
            client.post(
                "/contract-fixture/payload", json=body, headers={"X-SDK-Test": "optional-absent"}
            ).status_code
            == 200
        )
        assert (
            client.post(
                "/contract-fixture/payload",
                json=body | {"optional_nullable": None},
                headers={"X-SDK-Test": "optional-null"},
            ).status_code
            == 200
        )
        observed = {
            **client.get("/sdk-control/cases/optional-absent").json()["observations"],
            **client.get("/sdk-control/cases/optional-null").json()["observations"],
        }

    assert observed["optional-absent"]["optionalAbsent"] is True
    assert observed["optional-absent"]["requiredNull"] is True
    assert observed["optional-null"]["optionalNull"] is True


def test_payload_observation_does_not_replace_backend_validation_of_malformed_json() -> None:
    with TestClient(create_sdk_conformance_app()) as client:
        client.post(
            "/sdk-control/cases/bad-payload", json={"calls": {"bad-payload": {"kind": "none"}}}
        )
        response = client.post(
            "/contract-fixture/payload",
            content="{",
            headers={"Content-Type": "application/json", "X-SDK-Test": "bad-payload"},
        )
    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"


def test_faults_exercise_invalid_typed_shapes_without_changing_the_contract() -> None:
    with TestClient(create_sdk_conformance_app()) as client:
        client.post(
            "/sdk-control/cases/wrong-type",
            json={"calls": {"wrong-type": {"kind": "json", "body": {"principalId": 123}}}},
        )
        client.post(
            "/sdk-control/cases/missing", json={"calls": {"missing": {"kind": "json", "body": {}}}}
        )
        wrong_type = client.get("/v1/session", headers={"X-SDK-Test": "wrong-type"})
        missing = client.get("/v1/session", headers={"X-SDK-Test": "missing"})

    assert wrong_type.status_code == missing.status_code == 200
    assert wrong_type.json() == {"principalId": 123}
    assert missing.json() == {}
    assert "x-request-id" in wrong_type.headers


def test_scalar_fault_uses_a_model_without_uuid_conversion_to_expose_unchecked_casts() -> None:
    with TestClient(create_sdk_conformance_app()) as client:
        client.post(
            "/sdk-control/cases/scalar",
            json={
                "calls": {
                    "scalar": {
                        "kind": "json",
                        "body": {
                            "required_name": 123,
                            "required_nullable": None,
                            "score": "wrong",
                            "choice": [],
                        },
                    }
                }
            },
        )
        response = client.post("/contract-fixture/payload", headers={"X-SDK-Test": "scalar"})
    assert response.status_code == 200
    assert response.json() == {
        "required_name": 123,
        "required_nullable": None,
        "score": "wrong",
        "choice": [],
    }


def test_browser_fixture_enforces_its_configured_origin_and_exposes_metadata() -> None:
    origin = "http://127.0.0.1:43210"
    with TestClient(create_sdk_conformance_app(browser_origin=origin)) as client:
        response = client.post(
            "/v1/oauth/consent",
            headers={
                "Origin": origin,
                "Cookie": "ory_kratos_session=sdk-cookie",
                "X-Inframeld-CSRF": "1",
            },
            json={"consentChallenge": "a+b&/", "decision": "allow"},
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert "x-request-id" in response.headers["access-control-expose-headers"].lower()


def test_case_evidence_is_scoped_and_deleted_without_resetting_total_dispatches() -> None:
    with TestClient(create_sdk_conformance_app()) as client:
        client.post("/sdk-control/cases/first", json={"calls": {"one": {"kind": "none"}}})
        client.post("/sdk-control/cases/second", json={"calls": {"two": {"kind": "none"}}})
        client.get("/health", headers={"X-SDK-Test": "one"})
        client.get("/health", headers={"X-SDK-Test": "two"})
        first = client.get("/sdk-control/cases/first")
        client.delete("/sdk-control/cases/first")
        removed = client.get("/sdk-control/cases/first")
        second = client.get("/sdk-control/cases/second")
        counts = client.get("/sdk-control/counts").json()

    assert first.status_code == 200
    assert set(first.json()["observations"]) == {"one"}
    assert removed.status_code == 404
    assert set(second.json()["observations"]) == {"two"}
    assert counts == {"_total": 2}


def test_path_witness_retains_wire_escaping() -> None:
    with TestClient(create_sdk_conformance_app()) as client:
        client.post("/sdk-control/cases/escaped", json={"calls": {"escaped": {"kind": "none"}}})
        client.get(
            "/.well-known/oauth-protected-resource/api%2Fv1", headers={"X-SDK-Test": "escaped"}
        )
        observed = client.get("/sdk-control/cases/escaped").json()["observations"]["escaped"]
        assert observed["path"] == "/.well-known/oauth-protected-resource/api%2Fv1"


def test_expanded_unicode_discovery_preserves_identity_and_wire_path() -> None:
    path = "/.well-known/oauth-protected-resource/" + "%C3%A9" * 1500
    with TestClient(create_sdk_conformance_app()) as client:
        client.post("/sdk-control/cases/unicode", json={"calls": {"unicode": {"kind": "none"}}})
        response = client.get(path, headers={"X-SDK-Test": "unicode"})
        evidence = client.get("/sdk-control/cases/unicode").json()

    assert response.status_code == 200
    assert response.json()["resource"] == "https://api.test/" + "é" * 1500
    assert evidence["observations"]["unicode"]["path"] == path
    assert evidence["counts"] == {"unicode": 1}


def test_original_lookup_fixture_preserves_null_scope_guard_and_unknown_reference() -> None:
    body = {
        "installationId": "00000000-0000-4000-8000-000000000001",
        "organizationId": "00000000-0000-4000-8000-000000000002",
        "projectId": None,
        "method": "POST",
        "requestedRoute": "/v1/original-organization-operation",
        "key": "accepted",
        "expectedAuthority": {"family": "organization_action_use", "actionId": "create-projects"},
    }
    with TestClient(create_sdk_conformance_app()) as client:
        client.post(
            "/sdk-control/cases/lookup-wire", json={"calls": {"lookup-wire": {"kind": "none"}}}
        )
        response = client.post(
            "/v1/operations/lookup",
            json=body,
            headers={"Authorization": "Bearer sdk-human", "X-SDK-Test": "lookup-wire"},
        )
        witness = client.get("/sdk-control/cases/lookup-wire").json()["observations"]["lookup-wire"]
    assert response.status_code == 200
    assert response.json() == {
        "outcome": "accepted_asynchronous",
        "operationId": "sdk-original-operation",
        "admission": "confirmed",
        "jobReference": "unknown",
        "dispatch": "not_established",
        "idempotencyExpiresAt": None,
    }
    assert witness["jsonBody"] == body
    assert response.headers["cache-control"] == "no-store"


def test_deletion_status_fixture_uses_the_production_read_and_exact_query() -> None:
    operation = "settled +/&é"
    with TestClient(create_sdk_conformance_app()) as client:
        client.post(
            "/sdk-control/cases/deletion-wire",
            json={"calls": {"deletion-wire": {"kind": "none"}}},
        )
        response = client.get(
            "/v1/deletions/status",
            params={"operationId": operation},
            headers={"Authorization": "Bearer sdk-human", "X-SDK-Test": "deletion-wire"},
        )
        evidence = client.get("/sdk-control/cases/deletion-wire").json()

    assert response.status_code == 200
    assert response.json() == {
        "outcome": "retained",
        "operationId": operation,
        "jobState": "succeeded",
        "admissionConfirmed": True,
        "accessBlocked": True,
        "applicationShutdownComplete": True,
        "physicalCleanupComplete": True,
        "retentionExpiresAt": "2030-01-01T00:00:00Z",
    }
    assert response.headers["cache-control"] == "no-store"
    assert evidence["observations"]["deletion-wire"]["query"] == (
        "operationId=settled+%2B%2F%26%C3%A9"
    )
    assert evidence["counts"] == {"deletion-wire": 1}


def test_metadata_fixture_uses_real_read_resolve_and_change_routes_with_exact_input() -> None:
    project_id = "00000000-0000-4000-8000-000000000003"
    headers = {"Authorization": "Bearer sdk-human", "Idempotency-Key": "sdk-metadata-key"}
    body = {"expectedMetadataRevision": 0, "name": "support", "displayName": "Support 🧭"}
    with TestClient(create_sdk_conformance_app()) as client:
        original = client.get(f"/v1/projects/{project_id}/metadata", headers=headers)
        resolved = client.get("/v1/projects/by-name/support", headers=headers)
        changed = client.patch(f"/v1/projects/{project_id}/metadata", headers=headers, json=body)
        empty = client.patch(
            f"/v1/projects/{project_id}/metadata",
            headers=headers,
            json={"expectedMetadataRevision": 0},
        )
        null = client.patch(
            f"/v1/projects/{project_id}/metadata",
            headers=headers,
            json={"expectedMetadataRevision": 0, "displayName": None},
        )
    assert original.status_code == resolved.status_code == changed.status_code == 200
    assert original.json()["name"] is None
    assert original.json()["displayName"] == "legacy\u0001\n" + "x" * 150
    assert resolved.json()["name"] == "support"
    assert resolved.json()["projectId"] == changed.json()["projectId"] == project_id
    assert changed.json()["name"] == "support" and changed.json()["displayName"] == "Support 🧭"
    assert changed.json()["metadataRevision"] == 1
    assert changed.json()["operationId"] == "sdk-metadata-operation"
    assert changed.headers["cache-control"] == "no-store"
    assert empty.status_code == null.status_code == 422


def test_metadata_fixture_enforces_cookie_csrf_and_exact_name_validation() -> None:
    project_id = "00000000-0000-4000-8000-000000000003"
    body = {"expectedMetadataRevision": 0, "name": "production"}
    cookie = {"Cookie": "ory_kratos_session=sdk-cookie", "Idempotency-Key": "sdk-metadata-key"}
    with TestClient(create_sdk_conformance_app()) as client:
        denied = client.patch(f"/v1/projects/{project_id}/metadata", headers=cookie, json=body)
        permitted = client.patch(
            f"/v1/projects/{project_id}/metadata",
            headers=cookie | {"Origin": "https://account.test", "X-Inframeld-CSRF": "1"},
            json=body,
        )
        uppercase = client.get("/v1/projects/by-name/Support", headers=cookie)
    assert denied.status_code == 403
    assert permitted.status_code == 200 and permitted.json()["name"] == "production"
    assert uppercase.status_code == 422


def test_project_creation_fixture_serializes_own_access_and_original_receipt_with_exact_wire_input() -> (
    None
):
    organization = "00000000-0000-4000-8000-000000000002"
    project = "00000000-0000-4000-8000-000000000004"
    headers = {"Authorization": "Bearer sdk-human", "Idempotency-Key": "sdk-project-key"}
    body = {
        "organizationId": organization,
        "expectedAccessRevision": 7,
        "name": "new-support",
        "displayName": "Support 🧭",
    }
    with TestClient(create_sdk_conformance_app()) as client:
        client.post(
            "/sdk-control/cases/creation-wire", json={"calls": {"creation-wire": {"kind": "none"}}}
        )
        own = client.get("/v1/my-organization-access", headers=headers)
        created = client.post(
            "/v1/projects", headers=headers | {"X-SDK-Test": "creation-wire"}, json=body
        )
        repeated = client.post("/v1/projects", headers=headers, json=body)
        witness = client.get("/sdk-control/cases/creation-wire").json()["observations"][
            "creation-wire"
        ]

    assert own.status_code == 200
    assert own.json() == {
        "organizationId": organization,
        "principalId": "00000000-0000-4000-8000-000000000001",
        "accessRevision": 7,
        "grants": [{"actionId": "create-projects", "canGrant": False}],
    }
    assert created.status_code == repeated.status_code == 201
    assert (
        created.json()
        == repeated.json()
        == {
            "operationId": "sdk-project-creation",
            "idempotencyExpiresAt": "2030-01-01T00:00:00Z",
            "organizationId": organization,
            "projectId": project,
            "name": "new-support",
            "displayName": "Support 🧭",
            "accessRevision": 1,
            "metadataRevision": 0,
            "initialGrants": [
                {
                    "target": {"kind": "project", "projectId": project},
                    "actionId": action,
                    "canGrant": True,
                }
                for action in INITIAL_ACTIONS
            ],
        }
    )
    assert own.headers["cache-control"] == created.headers["cache-control"] == "no-store"
    assert witness["jsonBody"] == body and witness["method"] == "POST"
    assert witness["headers"]["idempotency-key"] == "sdk-project-key"


def test_project_creation_fixture_keeps_cookie_csrf_and_strict_body_validation() -> None:
    body = {
        "organizationId": "00000000-0000-4000-8000-000000000002",
        "expectedAccessRevision": 7,
        "name": "new-support",
        "displayName": "Support",
    }
    cookie = {"Cookie": "ory_kratos_session=sdk-cookie", "Idempotency-Key": "sdk-project-key"}
    with TestClient(create_sdk_conformance_app()) as client:
        denied = client.post("/v1/projects", headers=cookie, json=body)
        allowed = client.post(
            "/v1/projects",
            headers=cookie | {"Origin": "https://account.test", "X-Inframeld-CSRF": "1"},
            json=body,
        )
        unknown = client.post(
            "/v1/projects",
            headers={"Authorization": "Bearer sdk-human", "Idempotency-Key": "sdk-project-key"},
            json=body | {"canGrant": True},
        )
        boolean = client.post(
            "/v1/projects",
            headers={"Authorization": "Bearer sdk-human", "Idempotency-Key": "sdk-project-key"},
            json=body | {"expectedAccessRevision": True},
        )
    assert denied.status_code == 403
    assert allowed.status_code == 201
    assert unknown.status_code == boolean.status_code == 422


@pytest.mark.parametrize("kind", ["organization", "access-group", "application-account"])
@pytest.mark.parametrize("method", ["GET", "PUT", "DELETE"])
def test_access_grant_fixtures_keep_concrete_targets_levels_and_original_receipts(
    kind: str, method: str
) -> None:
    organization = "00000000-0000-4000-8000-000000000002"
    project = "00000000-0000-4000-8000-000000000003"
    recipient = "00000000-0000-4000-8000-000000000004"
    if kind == "organization":
        base, action = f"/v1/organizations/{organization}", "create-projects"
        scope = {"organizationId": organization}
    elif kind == "access-group":
        target = "00000000-0000-4000-8000-000000000007"
        base, action = f"/v1/projects/{project}/access-groups/{target}", "add-documents"
        scope = {"projectId": project, "accessGroupId": target}
    else:
        target = "00000000-0000-4000-8000-000000000008"
        base, action = (
            f"/v1/projects/{project}/application-accounts/{target}",
            "issue-application-keys",
        )
        scope = {"projectId": project, "applicationPrincipalId": target}
    path = base + "/grants" + ("" if method == "GET" else f"/{recipient}/{action}")
    headers = {"Authorization": "Bearer sdk-human", "Idempotency-Key": f"sdk-{kind}-grant-key"}
    with TestClient(create_sdk_conformance_app()) as client:
        response = client.request(
            method,
            path,
            headers=headers,
            params={"actionId": action, "limit": 2}
            if method == "GET"
            else {"expectedAccessRevision": 7}
            if method == "DELETE"
            else None,
            json={"canGrant": True, "expectedAccessRevision": 7} if method == "PUT" else None,
        )
    assert response.status_code == (201 if method == "PUT" else 200)
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    if method == "GET":
        assert body == {
            "items": [
                {**scope, "recipientPrincipalId": recipient, "actionId": action, "canGrant": True}
            ],
            "nextCursor": None,
        }
    else:
        assert scope.items() <= body.items()
        assert body["recipientPrincipalId"] == recipient and body["actionId"] == action
        assert body["accessRevision"] == 8 and body["changed"] is True
        assert body["idempotencyExpiresAt"] == "2030-01-01T00:00:00Z"
        assert body["canGrant"] is True if method == "PUT" else body["removed"] is True


@pytest.mark.parametrize(
    "kind,target,action",
    [
        ("project", "00000000-0000-4000-8000-000000000003", "inspect-budget"),
        ("access-group", "00000000-0000-4000-8000-000000000007", "add-documents"),
        ("application-account", "00000000-0000-4000-8000-000000000008", "issue-application-keys"),
    ],
)
def test_recipient_fixture_uses_actual_scalar_query_and_safe_choices(
    kind: str, target: str, action: str
) -> None:
    with TestClient(create_sdk_conformance_app()) as client:
        response = client.get(
            "/v1/projects/00000000-0000-4000-8000-000000000003/grant-recipients",
            params={"targetKind": kind, "targetId": target, "actionId": action},
            headers={"Authorization": "Bearer sdk-human"},
        )
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "items": [
            {
                "principalId": "00000000-0000-4000-8000-000000000004",
                "displayName": "Bob",
                "kind": "human",
            }
        ],
        "nextCursor": None,
    }


@pytest.mark.parametrize("method", ["PUT", "DELETE"])
@pytest.mark.parametrize("kind", ["organization", "access-group", "application-account"])
def test_new_grant_lookup_fixture_preserves_original_scope_guard_and_operation(
    kind: str, method: str
) -> None:
    organization = "00000000-0000-4000-8000-000000000002"
    project = "00000000-0000-4000-8000-000000000003"
    recipient = "00000000-0000-4000-8000-000000000004"
    if kind == "organization":
        base, action, family = (
            f"/v1/organizations/{organization}",
            "create-projects",
            "organization_grant_read",
        )
    elif kind == "access-group":
        base, action, family = (
            f"/v1/projects/{project}/access-groups/00000000-0000-4000-8000-000000000007",
            "add-documents",
            "access_group_grant_read",
        )
    else:
        base, action, family = (
            f"/v1/projects/{project}/application-accounts/00000000-0000-4000-8000-000000000008",
            "issue-application-keys",
            "application_account_grant_read",
        )
    body = {
        "installationId": "00000000-0000-4000-8000-000000000001",
        "organizationId": organization,
        "projectId": None if kind == "organization" else project,
        "method": method,
        "requestedRoute": f"{base}/grants/{recipient}/{action}",
        "key": f"sdk-{kind}-grant-key",
        "expectedAuthority": {"family": family, "actionId": action},
    }
    with TestClient(create_sdk_conformance_app()) as client:
        response = client.post(
            "/v1/operations/lookup", json=body, headers={"Authorization": "Bearer sdk-human"}
        )
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "outcome": "completed_synchronous",
        "operationId": f"sdk-{kind}-grant-{method.lower()}",
        "classification": "safe_result",
        "idempotencyExpiresAt": "2030-01-01T00:00:00Z",
    }


@pytest.mark.parametrize(
    "route,body,key,status,secret",
    [
        (
            "/v1/invitations",
            {
                "organizationId": "00000000-0000-4000-8000-000000000002",
                "assignments": [{"kind": "admission-only"}],
                "expectedAccessRevision": 7,
                "expectedProjectAccessRevisions": [],
            },
            "sdk-invitation-first",
            201,
            True,
        ),
        (
            "/v1/invitations",
            {
                "organizationId": "00000000-0000-4000-8000-000000000002",
                "assignments": [{"kind": "admission-only"}],
                "expectedAccessRevision": 7,
                "expectedProjectAccessRevisions": [],
            },
            "sdk-invitation-replay",
            201,
            False,
        ),
        (
            "/v1/invitations/00000000-0000-4000-8000-000000000006/revoke",
            {"expectedAccessRevision": 7},
            "sdk-revoke",
            200,
            None,
        ),
        ("/v1/invitations/preview", {"invitationToken": "A" * 43}, None, 200, None),
        ("/v1/invitations/activate", {"invitationToken": "A" * 43}, "sdk-activate", 200, None),
    ],
)
def test_invitation_fixture_presents_registered_outcomes_and_independent_wire_evidence(
    route: str, body: dict[str, object], key: str | None, status: int, secret: bool | None
) -> None:
    headers = {
        "Cookie": "ory_kratos_session=sdk-cookie",
        "Origin": "https://account.test",
        "X-Inframeld-CSRF": "1",
        "X-SDK-Test": "invitation-call",
    }
    if key is not None:
        headers["Idempotency-Key"] = key
    with TestClient(create_sdk_conformance_app(), raise_server_exceptions=False) as client:
        client.post(
            "/sdk-control/cases/invitation-fixture",
            json={"calls": {"invitation-call": {"kind": "none"}}},
        )
        response = client.post(route, json=body, headers=headers)
        seen = client.get("/sdk-control/cases/invitation-fixture").json()
    assert response.status_code == status
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["invitationId"] == "00000000-0000-4000-8000-000000000006"
    if secret is not None:
        assert response.json()["secretAvailable"] is secret
        assert ("invitationToken" in response.json()) is secret
    witness = seen["observations"]["invitation-call"]
    assert seen["counts"] == {"invitation-call": 1}
    assert (witness["method"], witness["path"], witness["query"], witness["jsonBody"]) == (
        "POST",
        route,
        "",
        body,
    )
    assert witness["headers"].get("idempotency-key") == key


@pytest.mark.parametrize("unset", [False, True])
def test_upload_default_fixture_uses_production_read_and_independent_dispatch_witness(
    unset: bool,
) -> None:
    project = (
        "00000000-0000-4000-8000-000000000005" if unset else "00000000-0000-4000-8000-000000000003"
    )
    route = f"/v1/projects/{project}/upload-defaults"
    with TestClient(create_sdk_conformance_app(), raise_server_exceptions=False) as client:
        client.post("/sdk-control/cases/upload-read", json={"calls": {"read": {"kind": "none"}}})
        response = client.get(
            route, headers={"Authorization": "Bearer sdk-human", "X-SDK-Test": "read"}
        )
        seen = client.get("/sdk-control/cases/upload-read").json()
    assert response.status_code == 200
    assert response.json() == {
        "projectId": project,
        "accessRevision": 7 if unset else 9,
        "groupIds": None if unset else ["00000000-0000-4000-8000-000000000030"],
    }
    assert response.headers["cache-control"] == "no-store"
    assert seen["counts"] == {"read": 1}
    witness = seen["observations"]["read"]
    assert (witness["method"], witness["path"], witness["query"], witness["rawBodyBase64"]) == (
        "GET",
        route,
        "",
        "",
    )
    assert witness["authorization"] == "Bearer sdk-human"


@pytest.mark.parametrize(
    "intent,revision,groups,after",
    [
        ("first", 7, ["00000000-0000-4000-8000-000000000020"], 8),
        ("replay", 7, ["00000000-0000-4000-8000-000000000020"], 8),
        ("noop", 9, ["00000000-0000-4000-8000-000000000030"], 9),
        ("first", 9007199254740990, ["00000000-0000-4000-8000-000000000020"], 9007199254740991),
    ],
)
def test_upload_default_fixture_preserves_exact_original_request_and_after_only_receipt(
    intent: str, revision: int, groups: list[str], after: int
) -> None:
    project = "00000000-0000-4000-8000-000000000003"
    route = f"/v1/projects/{project}/upload-defaults"
    body = {"groupIds": groups, "expectedAccessRevision": revision}
    headers = {
        "Authorization": "Bearer sdk-human",
        "Idempotency-Key": "sdk-upload-" + intent,
        "X-SDK-Test": "set",
    }
    with TestClient(create_sdk_conformance_app(), raise_server_exceptions=False) as client:
        client.post("/sdk-control/cases/upload-set", json={"calls": {"set": {"kind": "none"}}})
        response = client.put(route, json=body, headers=headers)
        seen = client.get("/sdk-control/cases/upload-set").json()
    assert response.status_code == 200
    assert response.json() == {
        "projectId": project,
        "accessRevision": after,
        "groupIds": groups,
        "operationId": "sdk-upload-noop" if intent == "noop" else "sdk-upload-original",
        "idempotencyExpiresAt": "2030-01-02T00:00:00Z",
    }
    assert response.headers["cache-control"] == "no-store"
    assert "beforeGroupIds" not in response.json()
    assert seen["counts"] == {"set": 1}
    witness = seen["observations"]["set"]
    assert witness["method"] == "PUT" and witness["path"] == route and witness["query"] == ""
    assert (
        witness["jsonBody"] == body
        and witness["headers"]["idempotency-key"] == "sdk-upload-" + intent
    )


@pytest.mark.parametrize(
    "key,revision,status,code",
    [
        ("first", 6, 409, "stale_revision"),
        ("noop", 8, 409, "stale_revision"),
        ("expired", 7, 409, "conflict"),
        ("unknown", 7, 503, "dependency_unavailable"),
        ("denied-old", 7, 403, "access_denied"),
        ("denied-new", 7, 403, "access_denied"),
        ("denied-retained", 7, 403, "access_denied"),
    ],
)
def test_upload_default_fixture_retains_controlled_currentness_and_recovery_errors(
    key: str, revision: int, status: int, code: str
) -> None:
    with TestClient(create_sdk_conformance_app(), raise_server_exceptions=False) as client:
        response = client.put(
            "/v1/projects/00000000-0000-4000-8000-000000000003/upload-defaults",
            json={
                "groupIds": ["00000000-0000-4000-8000-000000000020"],
                "expectedAccessRevision": revision,
            },
            headers={"Authorization": "Bearer sdk-human", "Idempotency-Key": "sdk-upload-" + key},
        )
    assert (
        response.status_code == response.json()["status"] == status
        and response.json()["code"] == code
    )
    assert response.headers["cache-control"] == "no-store"


def test_upload_default_fixture_cookie_csrf_and_duplicate_groups_use_production_guards() -> None:
    route = "/v1/projects/00000000-0000-4000-8000-000000000003/upload-defaults"
    group = "00000000-0000-4000-8000-000000000020"
    body = {"groupIds": [group], "expectedAccessRevision": 7}
    cookie = {"Cookie": "ory_kratos_session=sdk-cookie", "Idempotency-Key": "sdk-upload-first"}
    with TestClient(create_sdk_conformance_app(), raise_server_exceptions=False) as client:
        denied = client.put(route, json=body, headers=cookie)
        allowed = client.put(
            route,
            json=body,
            headers=cookie | {"Origin": "https://account.test", "X-Inframeld-CSRF": "1"},
        )
        duplicate = client.put(
            route,
            json=body | {"groupIds": [group, group]},
            headers={"Authorization": "Bearer sdk-human", "Idempotency-Key": "sdk-upload-first"},
        )
    assert denied.status_code == 403 and allowed.status_code == 200 and duplicate.status_code == 422


@pytest.mark.parametrize("cookie", [False, True])
def test_project_deletion_fixture_preserves_original_202_and_bodyless_wire(cookie: bool) -> None:
    """Expose an unchanged original acceptance on an explicitly requested replay."""
    project = "00000000-0000-4000-8000-000000000003"
    route = f"/v1/projects/{project}"
    headers = {"Idempotency-Key": "sdk-project-delete", "X-SDK-Test": "project-delete"}
    if cookie:
        headers |= {
            "Cookie": "ory_kratos_session=sdk-cookie",
            "Origin": "https://account.test",
            "X-Inframeld-CSRF": "1",
        }
    else:
        headers["Authorization"] = "Bearer sdk-human"

    with TestClient(create_sdk_conformance_app()) as client:
        client.post(
            "/sdk-control/cases/project-delete",
            json={"calls": {"project-delete": {"kind": "none"}}},
        )
        before = client.get("/sdk-control/counts").json()["_total"]
        first = client.delete(route, params={"expectedAccessRevision": 7}, headers=headers)
        replay = client.delete(route, params={"expectedAccessRevision": 7}, headers=headers)
        evidence = client.get("/sdk-control/cases/project-delete").json()
        after = client.get("/sdk-control/counts").json()["_total"]

    expected = {
        "operationId": "sdk-project-delete",
        "idempotencyExpiresAt": None,
        "projectId": project,
        "accessRevision": 8,
        "admissionConfirmed": True,
        "accessBlocked": True,
    }
    assert first.status_code == replay.status_code == 202
    assert first.json() == replay.json() == expected
    assert first.headers["cache-control"] == replay.headers["cache-control"] == "no-store"
    assert evidence["counts"] == {"project-delete": 2} and after - before == 2
    witness = evidence["observations"]["project-delete"]
    assert (witness["method"], witness["path"], witness["query"], witness["rawBodyBase64"]) == (
        "DELETE",
        route,
        "expectedAccessRevision=7",
        "",
    )
    assert witness["headers"]["idempotency-key"] == "sdk-project-delete"
    assert witness["authorization"] == ("" if cookie else "Bearer sdk-human")
    if cookie:
        assert witness["origin"] == "https://account.test"
        assert witness["csrf"] == "1"


@pytest.mark.parametrize(
    "credential,key,revision,project,status,code",
    [
        ({}, "sdk-project-delete", 7, 3, 401, "http_error"),
        ({"Authorization": "Bearer sdk-denied"}, "sdk-project-delete", 7, 3, 403, "access_denied"),
        (
            {"Authorization": "Bearer sdk-human"},
            "sdk-project-delete",
            7,
            99,
            404,
            "resource_not_found",
        ),
        ({"Authorization": "Bearer sdk-human"}, "sdk-project-delete", 6, 3, 409, "stale_revision"),
        ({"Authorization": "Bearer sdk-human"}, "sdk-project-delete-fresh", 7, 3, 409, "conflict"),
        (
            {"Authorization": "Bearer sdk-human"},
            "sdk-project-delete-unavailable",
            7,
            3,
            503,
            "dependency_unavailable",
        ),
        (
            {"Authorization": "Bearer sdk-other-human"},
            "sdk-project-delete",
            7,
            3,
            403,
            "access_denied",
        ),
    ],
)
def test_project_deletion_fixture_preserves_safe_failure_classifications(
    credential: dict[str, str], key: str, revision: int, project: int, status: int, code: str
) -> None:
    route = f"/v1/projects/{UUID(int=project)}"
    if project == 3:
        route = "/v1/projects/00000000-0000-4000-8000-000000000003"
    with TestClient(create_sdk_conformance_app()) as client:
        response = client.delete(
            route,
            params={"expectedAccessRevision": revision},
            headers=credential | {"Idempotency-Key": key},
        )

    assert response.status_code == status
    assert response.json()["status"] == status and response.json()["code"] == code
    assert "operationId" not in response.json()
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "query",
    [
        "",
        "expectedAccessRevision=07",
        "expectedAccessRevision=7&expectedAccessRevision=7",
        "expectedAccessRevision=7&extra=1",
    ],
)
def test_project_deletion_fixture_keeps_strict_bodyless_query(query: str) -> None:
    with TestClient(create_sdk_conformance_app()) as client:
        response = client.delete(
            "/v1/projects/00000000-0000-4000-8000-000000000003?" + query,
            headers={"Authorization": "Bearer sdk-human", "Idempotency-Key": "sdk-project-delete"},
        )
    assert response.status_code == 422
    assert response.json()["status"] == 422


def test_project_deletion_fixture_preserves_cookie_guard_and_rejects_body() -> None:
    route = "/v1/projects/00000000-0000-4000-8000-000000000003?expectedAccessRevision=7"
    with TestClient(create_sdk_conformance_app()) as client:
        denied = client.delete(
            route,
            headers={
                "Cookie": "ory_kratos_session=sdk-cookie",
                "Idempotency-Key": "sdk-project-delete",
            },
        )
        body = client.request(
            "DELETE",
            route,
            json={},
            headers={"Authorization": "Bearer sdk-human", "Idempotency-Key": "sdk-project-delete"},
        )
    assert denied.status_code == 403 and denied.json()["code"] == "access_denied"
    assert body.status_code == 422


@pytest.mark.parametrize(
    "mismatch", [None, "installation", "organization", "project", "key", "actor"]
)
def test_project_deletion_fixture_lookup_retains_only_exact_original_scope(
    mismatch: str | None,
) -> None:
    project = "00000000-0000-4000-8000-000000000003"
    body: dict[str, object] = {
        "installationId": "00000000-0000-4000-8000-000000000001",
        "organizationId": "00000000-0000-4000-8000-000000000002",
        "projectId": project,
        "method": "DELETE",
        "requestedRoute": f"/v1/projects/{project}",
        "key": "sdk-project-delete",
        "expectedAuthority": {"family": "project_deletion", "actionId": "delete-project"},
    }
    if mismatch in {"installation", "organization", "project"}:
        body[mismatch + "Id"] = str(UUID(int=999))
        if mismatch == "project":
            body["requestedRoute"] = f"/v1/projects/{UUID(int=999)}"
    elif mismatch == "key":
        body["key"] = "different-original"
    token = "sdk-other-human" if mismatch == "actor" else "sdk-human"
    with TestClient(create_sdk_conformance_app()) as client:
        client.post(
            "/sdk-control/cases/project-lookup",
            json={"calls": {"project-lookup": {"kind": "none"}}},
        )
        response = client.post(
            "/v1/operations/lookup",
            json=body,
            headers={"Authorization": f"Bearer {token}", "X-SDK-Test": "project-lookup"},
        )
        evidence = client.get("/sdk-control/cases/project-lookup").json()

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert evidence["counts"] == {"project-lookup": 1}
    assert evidence["observations"]["project-lookup"]["jsonBody"] == body
    if mismatch is not None:
        assert response.json() == {"outcome": "unresolved"}
    else:
        assert response.json() == {
            "outcome": "retained",
            "operationId": "sdk-project-delete",
            "jobState": "succeeded",
            "admissionConfirmed": True,
            "accessBlocked": True,
            "applicationShutdownComplete": True,
            "physicalCleanupComplete": False,
            "retentionExpiresAt": None,
        }


@pytest.mark.parametrize(
    "field,value",
    [
        ("method", "POST"),
        ("requestedRoute", "/v1/projects/wrong"),
        ("expectedAuthority", {"family": "project_deletion", "actionId": "read-documents"}),
    ],
)
def test_project_deletion_fixture_rejects_invalid_lookup_capsules(
    field: str, value: object
) -> None:
    body: dict[str, object] = {
        "installationId": "00000000-0000-4000-8000-000000000001",
        "organizationId": "00000000-0000-4000-8000-000000000002",
        "projectId": "00000000-0000-4000-8000-000000000003",
        "method": "DELETE",
        "requestedRoute": "/v1/projects/00000000-0000-4000-8000-000000000003",
        "key": "sdk-project-delete",
        "expectedAuthority": {"family": "project_deletion", "actionId": "delete-project"},
    }
    body[field] = value
    with TestClient(create_sdk_conformance_app()) as client:
        response = client.post(
            "/v1/operations/lookup", json=body, headers={"Authorization": "Bearer sdk-human"}
        )
    assert response.status_code == 422


@pytest.mark.parametrize("complete", [False, True])
def test_project_deletion_fixture_status_keeps_physical_work_pending(complete: bool) -> None:
    operation = "sdk-project-delete" if complete else "sdk-project-delete-pending"
    with TestClient(create_sdk_conformance_app()) as client:
        response = client.get(
            "/v1/deletions/status",
            params={"operationId": operation},
            headers={"Authorization": "Bearer sdk-human"},
        )
    assert response.status_code == 200
    assert response.json() == {
        "outcome": "retained",
        "operationId": operation,
        "jobState": "succeeded" if complete else "queued",
        "admissionConfirmed": True,
        "accessBlocked": True,
        "applicationShutdownComplete": complete,
        "physicalCleanupComplete": False,
        "retentionExpiresAt": None,
    }
