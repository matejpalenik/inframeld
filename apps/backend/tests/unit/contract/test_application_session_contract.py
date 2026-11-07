"""Keep application identity and ordinary bearer dispatch distinct on the real HTTP app."""

from fastapi.testclient import TestClient

from inframeld_backend.bootstrap.application_factory import create_app

KEY = "ifm_app_00000000-0000-4000-8000-000000000003_" + "A" * 43


def test_native_application_identity_has_exact_safe_shape_and_exclusive_security() -> None:
    schema = create_app().openapi()
    operation = schema["paths"].get("/v1/application-session", {}).get("get")
    assert operation is not None
    assert operation["operationId"] == "getCurrentApplicationSession"
    assert operation["security"] == [{"ApplicationKeyBearer": []}]
    model = schema["components"]["schemas"]["CurrentApplicationSessionResponse"]
    assert set(model["properties"]) == {"principalId", "projectId"}
    assert set(model["required"]) == {"principalId", "projectId"}
    for field in model["properties"].values():
        assert field["format"] == "uuid"
    for status in ("400", "401", "403", "503"):
        assert "application/problem+json" in operation["responses"][status]["content"]


def test_identity_family_selection_and_missing_application_profile_fail_before_io() -> None:
    client = TestClient(create_app())
    human = client.get(
        "/v1/application-session", headers={"Authorization": "Bearer unsupported-human"}
    )
    assert human.status_code == 401
    assert human.headers["cache-control"] == "no-store"
    application = client.get("/v1/session", headers={"Authorization": "Bearer " + KEY})
    assert application.status_code == 401
    unavailable = client.get("/v1/application-session", headers={"Authorization": "Bearer " + KEY})
    assert unavailable.status_code == 503
    assert unavailable.json()["code"] == "dependency_unavailable"
