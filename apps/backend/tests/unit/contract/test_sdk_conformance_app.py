"""Qualify the isolated HTTP fixture before SDKs consume it."""

import base64
from urllib.parse import parse_qs

import pytest
from fastapi.testclient import TestClient
from tests.support.project_creation_scenarios import INITIAL_ACTIONS
from tests.support.sdk_conformance_app import create_sdk_conformance_app


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


def test_real_consent_and_grant_routes_preserve_csrf_and_request_validation() -> None:
    cookie = {"Cookie": "ory_kratos_session=sdk-cookie"}
    write = cookie | {"Origin": "https://account.test", "X-Inframeld-CSRF": "1"}
    consent = {"consentChallenge": "a+b&/", "decision": "allow", "remember": True}
    grant = {
        "recipientPrincipalId": "00000000-0000-4000-8000-000000000002",
        "actionId": "create-access-groups",
        "expectedAccessRevision": 0,
    }
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
        result = client.post(url, json=grant, headers=write | {"Idempotency-Key": "sdk-key"})
        assert result.status_code == 201
        assert result.json()["accessRevision"] == 1
        invalid = client.post(
            url,
            json=grant | {"recipientPrincipalId": "invalid"},
            headers=write | {"Idempotency-Key": "sdk-key"},
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
