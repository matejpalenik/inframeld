"""Challenge the selected generated models, separately from HTTP scenarios."""

import unittest
from typing import assert_type, cast
from uuid import UUID

import httpx
import inframeld_sdk
import inframeld_sdk_fixtures
from observations import NativeModel
from pydantic import BaseModel, JsonValue, TypeAdapter, ValidationError

Model = (
    inframeld_sdk_fixtures.ContractFixturePayload | inframeld_sdk.ProjectActionGrantRemovalResponse
)
_JSON_OBJECT = TypeAdapter(dict[str, JsonValue])


async def check_response_variant_signatures(
    api: inframeld_sdk_fixtures.DefaultApi,
) -> None:
    variants = await api.contract_fixture_variants_with_http_info()
    media = await api.contract_fixture_media_with_http_info()
    fallback = await api.contract_fixture_fallback_with_http_info()
    assert_type(
        fallback.data,
        inframeld_sdk_fixtures.ContractFixtureReadyResponseDTO
        | inframeld_sdk_fixtures.ContractFixtureAcceptedResponseDTO
        | None,
    )
    assert_type(
        variants.data,
        inframeld_sdk_fixtures.ContractFixtureReadyResponseDTO
        | inframeld_sdk_fixtures.ContractFixtureAcceptedResponseDTO
        | None,
    )
    assert_type(
        media.data,
        inframeld_sdk_fixtures.ContractFixtureReadyResponseDTO
        | inframeld_sdk_fixtures.ContractFixtureAcceptedResponseDTO
        | None,
    )


def body_value(value: NativeModel) -> dict[str, JsonValue]:
    return _JSON_OBJECT.validate_json(value.to_json())


payload_type = inframeld_sdk_fixtures.ContractFixturePayload
grant_type = inframeld_sdk.ProjectActionGrantRemovalResponse
payload: dict[str, JsonValue] = {
    "required_name": "valid",
    "required_nullable": None,
    "choice": 7,
    "score": 0.5,
}
grant: dict[str, JsonValue] = {
    "accessRevision": 1,
    "actionId": "create-access-groups",
    "removed": True,
    "changed": True,
    "idempotencyExpiresAt": "2030-01-01T00:00:00Z",
    "operationId": "sdk-operation",
    "projectId": "00000000-0000-4000-8000-000000000003",
    "recipientPrincipalId": "00000000-0000-4000-8000-000000000002",
}


def parse(
    cls: type[inframeld_sdk_fixtures.ContractFixturePayload]
    | type[inframeld_sdk.ProjectActionGrantRemovalResponse],
    data: dict[str, JsonValue],
) -> Model:
    value = cls.from_dict(data)
    if value is None:
        raise ValueError("Expected a native model")
    return value


def rejects(
    cls: type[inframeld_sdk_fixtures.ContractFixturePayload]
    | type[inframeld_sdk.ProjectActionGrantRemovalResponse],
    data: dict[str, JsonValue],
) -> bool:
    try:
        parse(cls, data)
    except (ValueError, KeyError, TypeError):
        return True
    return False


def _rejects_native_null() -> bool:
    try:
        grant_type.model_validate(grant | {"removed": None})
    except ValueError:
        return True
    return False


class GeneratedModelTests(unittest.TestCase):
    def test_password_requests_hide_diagnostics_and_keep_wire_values(self) -> None:
        value = "synthetic-secret-marker-75"
        for model, public_field, wire_field, body in (
            (
                inframeld_sdk.ModelConnectionCredentialRequest,
                "value",
                "value",
                {"expectedCredentialRevision": 0},
            ),
            (
                inframeld_sdk.HumanOAuthConsentRequest,
                "consent_challenge",
                "consentChallenge",
                {"decision": "allow"},
            ),
        ):
            with self.subTest(model=model.__name__):
                request = model.model_validate({**body, wire_field: value})
                self.assertTrue(
                    getattr(request, public_field) == value,
                    "The public request field changed.",
                )
                self.assertTrue(
                    _JSON_OBJECT.validate_json(request.to_json()).get(wire_field) == value,
                    "Explicit wire serialization changed the password field.",
                )
                with self.subTest(surface="model_formatting"):
                    for description in (repr(request), str(request), request.to_str()):
                        self.assertTrue(
                            value not in description, "Model diagnostics exposed a password field."
                        )
                with self.subTest(surface="validation"):
                    with self.assertRaises(ValidationError) as failure:
                        model.model_validate({**body, wire_field: value.encode()})
                    for description in (str(failure.exception), repr(failure.exception)):
                        self.assertFalse(
                            value in description, "Validation diagnostics exposed raw input."
                        )

    def test_application_key_issue_preserves_order_omission_and_exact_integers(self) -> None:
        source: dict[str, JsonValue] = {
            "allowedAdapters": ["mcp", "http"],
            "expectedAccessRevision": 2**53 - 1,
        }
        model = inframeld_sdk.ApplicationKeyIssueRequest.from_dict(source)
        self.assertIsNotNone(model)
        assert model is not None
        self.assertEqual(body_value(model), source)
        for invalid in (None, True, 1.5, 0, 2**53):
            with self.subTest(lifetime=invalid), self.assertRaises(ValueError):
                inframeld_sdk.ApplicationKeyIssueRequest.from_dict(
                    source | {"expiresInSeconds": invalid}
                )
        for invalid in (True, 2**53):
            with self.subTest(revision=invalid), self.assertRaises(ValueError):
                inframeld_sdk.ApplicationKeyIssueRequest.from_dict(
                    source | {"expectedAccessRevision": invalid}
                )

    def test_application_key_union_keeps_secret_on_first_delivery_only(self) -> None:
        source: dict[str, JsonValue] = {
            "operationId": "key-issue-original",
            "accessRevision": 8,
            "idempotencyExpiresAt": "2030-01-01T00:00:00Z",
            "metadata": {
                "keyId": "00000000-0000-4000-8000-000000000010",
                "applicationPrincipalId": "00000000-0000-4000-8000-000000000008",
                "projectId": "00000000-0000-4000-8000-000000000003",
                "prefix": "ifm_app_",
                "allowedAdapters": ["mcp", "http"],
                "createdAt": "2030-01-01T00:00:00Z",
                "expiresAt": "2030-04-01T00:00:00Z",
                "revokedAt": None,
            },
        }
        for secret in (True, False):
            value = source | {"secretAvailable": secret}
            if secret:
                value["key"] = "ifm_app_00000000-0000-4000-8000-000000000010_" + "A" * 43
            model = inframeld_sdk.ApplicationKeyIssueResponse.from_dict(value)
            self.assertIsInstance(
                model.actual_instance,
                inframeld_sdk.ApplicationKeyFirstDeliveryResponse
                if secret
                else inframeld_sdk.ApplicationKeyIssuanceReplayResponse,
            )
            self.assertEqual(body_value(model), value)
        for invalid in (None, 1, "true"):
            with self.subTest(secret=invalid), self.assertRaises(ValueError):
                inframeld_sdk.ApplicationKeyIssueResponse.from_dict(
                    source | {"secretAvailable": invalid}
                )
        with self.assertRaises(ValueError):
            inframeld_sdk.ApplicationKeyIssueResponse.from_dict(source | {"secretAvailable": True})

    def test_invitation_issue_preserves_lifetime_omission_and_strict_revision(self) -> None:
        source: dict[str, JsonValue] = {
            "organizationId": "00000000-0000-4000-8000-000000000002",
            "assignments": [{"kind": "admission-only"}],
            "expectedAccessRevision": 2**53 - 1,
            "expectedProjectAccessRevisions": [],
        }
        model = inframeld_sdk.InvitationIssueRequest.from_dict(source)
        self.assertIsNotNone(model)
        assert model is not None
        self.assertEqual(body_value(model), source)
        for invalid in (None, True, 1.5, 0, 2592001):
            with self.subTest(lifetime=invalid), self.assertRaises(ValueError):
                inframeld_sdk.InvitationIssueRequest.from_dict(
                    source | {"expiresInSeconds": invalid}
                )
        for invalid in (True, 2**53):
            with self.subTest(revision=invalid), self.assertRaises(ValueError):
                inframeld_sdk.InvitationIssueRequest.from_dict(
                    source | {"expectedAccessRevision": invalid}
                )

    def test_invitation_secret_union_keeps_first_delivery_and_replay_distinct(self) -> None:
        source: dict[str, JsonValue] = {
            "invitationId": "00000000-0000-4000-8000-000000000006",
            "organizationId": "00000000-0000-4000-8000-000000000002",
            "assignments": [{"kind": "admission-only"}],
            "accessRevision": 8,
            "expiresAt": "2030-01-01T00:00:00Z",
            "idempotencyExpiresAt": "2030-01-01T00:00:00Z",
            "operationId": "original-issue",
        }
        for secret in (True, False):
            value = source | {"secretAvailable": secret}
            if secret:
                value["invitationToken"] = "A" * 43
            model = inframeld_sdk.InvitationIssueResponse.from_dict(value)
            self.assertIsInstance(
                model.actual_instance,
                inframeld_sdk.InvitationFirstDeliveryResponse
                if secret
                else inframeld_sdk.InvitationIssuanceReplayResponse,
            )
            self.assertEqual(body_value(model), value)
        for invalid in (None, 1, "true"):
            with self.subTest(secret=invalid), self.assertRaises(ValueError):
                inframeld_sdk.InvitationIssueResponse.from_dict(
                    source | {"secretAvailable": invalid}
                )
        with self.assertRaises(ValueError):
            inframeld_sdk.InvitationIssueResponse.from_dict(source | {"secretAvailable": True})

    def test_invitation_closed_assignment_rejects_unknown_tag_and_nonboolean_level(self) -> None:
        for invalid in (
            {"kind": "unknown"},
            {"kind": "group-membership"},
            {
                "kind": "action-grant",
                "target": {"kind": "unknown"},
                "actionId": "query",
                "canGrant": True,
            },
            {
                "kind": "action-grant",
                "target": {
                    "kind": "organization",
                    "organizationId": "00000000-0000-4000-8000-000000000002",
                },
                "actionId": "create-projects",
                "canGrant": 1,
            },
        ):
            with self.subTest(value=invalid), self.assertRaises(ValueError):
                inframeld_sdk.InvitationAssignmentRequest.from_dict(invalid)

    def test_configuration_keeps_standard_credentials_and_auth_metadata(self) -> None:
        configuration = inframeld_sdk.Configuration(
            access_token="test-only-token",
            api_key={"KratosSession": "test-only-session"},
        )
        self.assertEqual(
            configuration.auth_settings(),
            {
                "ApplicationKeyBearer": {
                    "type": "bearer",
                    "in": "header",
                    "key": "Authorization",
                    "value": "Bearer test-only-token",
                },
                "HumanBearer": {
                    "type": "bearer",
                    "in": "header",
                    "key": "Authorization",
                    "value": "Bearer test-only-token",
                },
                "KratosSession": {
                    "type": "api_key",
                    "in": "cookie",
                    "key": "ory_kratos_session",
                    "value": "test-only-session",
                },
                "ProductBearer": {
                    "type": "bearer",
                    "in": "header",
                    "key": "Authorization",
                    "value": "Bearer test-only-token",
                },
            },
        )
        fixtures = inframeld_sdk_fixtures.Configuration(access_token="test-only-token")
        self.assertEqual(fixtures.auth_settings(), {})

    def test_revision_models_preserve_the_exact_json_safe_integer_bound(self) -> None:
        identifier = "00000000-0000-4000-8000-000000000001"
        cases: tuple[tuple[type[BaseModel], str, dict[str, JsonValue]], ...] = (
            (
                inframeld_sdk.HumanAdmissionRequest,
                "expectedAccessRevision",
                {"identityId": identifier},
            ),
            (
                inframeld_sdk.ProjectCreationRequest,
                "expectedAccessRevision",
                {"organizationId": identifier, "name": "support", "displayName": "Support"},
            ),
            (inframeld_sdk.ProjectMembershipRequest, "expectedAccessRevision", {}),
            (
                inframeld_sdk.ProjectMetadataUpdateRequest,
                "expectedMetadataRevision",
                {"name": "support"},
            ),
            (
                inframeld_sdk.MyOrganizationAccessResponse,
                "accessRevision",
                {"organizationId": identifier, "principalId": identifier, "grants": []},
            ),
        )
        for model, field, other_fields in cases:
            with self.subTest(model=model.__name__):
                for revision in (0, 2**53 - 1):
                    value = model.model_validate({**other_fields, field: revision})
                    self.assertEqual(
                        _JSON_OBJECT.validate_json(value.model_dump_json(by_alias=True))[field],
                        revision,
                    )
                with self.assertRaises(ValidationError):
                    model.model_validate({**other_fields, field: 2**53})

    def test_metadata_change_preserves_omission_and_counts_unicode_code_points(self) -> None:
        source: dict[str, JsonValue] = {"expectedMetadataRevision": 0, "name": "production"}
        model = inframeld_sdk.ProjectMetadataUpdateRequest.model_validate(source)
        self.assertEqual(body_value(model), source)
        for field in ["name", "displayName"]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                inframeld_sdk.ProjectMetadataUpdateRequest.model_validate(source | {field: None})
        for label in ["🧭" * 128, "e\u0301" * 64]:
            value: dict[str, JsonValue] = {"expectedMetadataRevision": 0, "displayName": label}
            self.assertEqual(
                body_value(inframeld_sdk.ProjectMetadataUpdateRequest.model_validate(value)), value
            )
        for replacements in [{"name": "A"}, {"name": "a" * 64}, {"displayName": "🧭" * 129}]:
            with self.subTest(replacements=replacements), self.assertRaises(ValueError):
                inframeld_sdk.ProjectMetadataUpdateRequest.model_validate(
                    {"expectedMetadataRevision": 0} | replacements
                )

    def test_metadata_read_requires_nullable_selector_and_preserves_legacy_label(self) -> None:
        source: dict[str, JsonValue] = {
            "projectId": "00000000-0000-4000-8000-000000000003",
            "organizationId": "00000000-0000-4000-8000-000000000002",
            "name": None,
            "displayName": "legacy\x01\n" + "x" * 150,
            "metadataRevision": 0,
        }
        self.assertEqual(
            body_value(inframeld_sdk.ProjectMetadataResponse.model_validate(source)), source
        )
        source.pop("name")
        with self.assertRaises(ValueError):
            inframeld_sdk.ProjectMetadataResponse.model_validate(source)

    def test_original_lookup_preserves_null_scope_and_requires_the_guard(self) -> None:
        source: dict[str, JsonValue] = {
            "installationId": "00000000-0000-4000-8000-000000000001",
            "organizationId": "00000000-0000-4000-8000-000000000002",
            "projectId": None,
            "method": "POST",
            "requestedRoute": "/v1/original-organization-operation",
            "key": "original +/&é",
            "expectedAuthority": {
                "family": "organization_action_use",
                "actionId": "create-projects",
            },
        }
        model = inframeld_sdk.OriginalOperationLookupRequest.model_validate(source)
        self.assertEqual(body_value(model), source)
        for guard in [None, "absent"]:
            invalid = dict(source)
            if guard is None:
                invalid["expectedAuthority"] = None
            else:
                invalid.pop("expectedAuthority")
            with self.assertRaises(ValueError):
                inframeld_sdk.OriginalOperationLookupRequest.model_validate(invalid)

    def test_accepted_lookup_requires_its_discriminator_and_uncertainty(self) -> None:
        source: dict[str, JsonValue] = {
            "outcome": "accepted_asynchronous",
            "operationId": "original",
            "admission": "confirmed",
            "jobReference": "unknown",
            "dispatch": "not_established",
            "idempotencyExpiresAt": None,
        }
        model = inframeld_sdk.AcceptedOperationLookupResponse.from_dict(source)
        self.assertIsNotNone(model)
        assert model is not None
        self.assertEqual(body_value(model), source)
        known = source | {"jobReference": {"jobId": "00000000-0000-4000-8000-000000000008"}}
        model = inframeld_sdk.AcceptedOperationLookupResponse.from_dict(known)
        self.assertIsNotNone(model)
        assert model is not None
        self.assertEqual(body_value(model), known)
        for reference in [
            {},
            {"jobId": None},
            {"jobId": "guessed-job"},
        ]:
            with self.subTest(reference=reference), self.assertRaises(ValueError):
                inframeld_sdk.AcceptedOperationLookupResponse.from_dict(
                    source | {"jobReference": reference}
                )
        projected = inframeld_sdk.AcceptedOperationLookupResponse.from_dict(
            source
            | {
                "jobReference": {
                    "jobId": "00000000-0000-4000-8000-000000000008",
                    "state": "running",
                }
            }
        )
        assert projected is not None
        self.assertEqual(body_value(projected), known)
        for field in ["outcome", "admission", "jobReference", "dispatch", "idempotencyExpiresAt"]:
            invalid = dict(source)
            invalid.pop(field)
            with self.subTest(field=field), self.assertRaises(ValueError):
                inframeld_sdk.AcceptedOperationLookupResponse.from_dict(invalid)
        with self.assertRaises(ValueError):
            inframeld_sdk.AcceptedOperationLookupResponse.from_dict(
                source | {"jobReference": "known"}
            )

    def test_malformed_problem_array_is_not_repaired(self) -> None:
        with self.assertRaises((ValueError, TypeError)):
            inframeld_sdk.ProblemDetails.from_dict(
                {
                    "type": "about:blank",
                    "title": "Bad request",
                    "status": 400,
                    "detail": "invalid",
                    "code": "invalid_request",
                    "requestId": "00000000-0000-4000-8000-000000000099",
                    "errors": {},
                }
            )

    def test_declared_json_requires_json_and_native_container_shapes(self) -> None:
        client = inframeld_sdk.ApiClient()
        for text, kind, content_type in [
            ("", "str", "application/json"),
            ("not-json", "str", None),
            ('{"key":"value"}', "List[str]", "application/json"),
            ('"abc"', "List[str]", "application/json"),
        ]:
            with self.subTest(text=text, kind=kind), self.assertRaises(ValueError):
                client.deserialize(text, kind, content_type)
        self.assertEqual(client.deserialize('""', "str", "application/json"), "")
        self.assertEqual(client.deserialize("[]", "List[str]", "application/json"), [])

    def test_omitted_default_is_not_inserted_into_the_request(self) -> None:
        source = {"consentChallenge": "a+b&/", "decision": "allow"}
        value = inframeld_sdk.HumanOAuthConsentRequest.from_dict(source)
        assert value is not None
        self.assertNotIn("remember", value.to_dict())

    def test_an_explicit_false_default_is_retained(self) -> None:
        source = {"consentChallenge": "a+b&/", "decision": "allow", "remember": False}
        value = inframeld_sdk.HumanOAuthConsentRequest.from_dict(source)
        assert value is not None
        self.assertIs(value.to_dict()["remember"], False)

    def test_required_nullable_is_required(self) -> None:
        self.assertTrue(
            rejects(
                payload_type,
                {key: value for key, value in payload.items() if key != "required_nullable"},
            )
        )

    def test_omission_stays_omitted(self) -> None:
        self.assertTrue("optional_nullable" not in body_value(parse(payload_type, payload)))

    def test_explicit_null_is_retained(self) -> None:
        self.assertTrue(
            body_value(parse(payload_type, payload | {"optional_nullable": None}))[
                "optional_nullable"
            ]
            is None
        )

    def test_removal_acknowledgement_accepts_true(self) -> None:
        self.assertTrue(body_value(parse(grant_type, grant))["removed"] is True)

    def test_removal_acknowledgement_rejects_false(self) -> None:
        self.assertTrue(rejects(grant_type, grant | {"removed": False}))

    def test_nonnullable_rejects_null_from_dict(self) -> None:
        with self.assertRaises(ValueError):
            grant_type.from_dict(grant | {"removed": None})

    def test_nonnullable_rejects_null_native_model(self) -> None:
        self.assertTrue(_rejects_native_null())

    def test_scalar_union_rejects_boolean(self) -> None:
        self.assertTrue(rejects(payload_type, payload | {"choice": True}))

    def test_scalar_union_rejects_array(self) -> None:
        self.assertTrue(rejects(payload_type, payload | {"choice": []}))

    def test_required_string_rejects_integer(self) -> None:
        self.assertTrue(rejects(payload_type, payload | {"required_name": 123}))


class ResponseIntegrityTests(unittest.IsolatedAsyncioTestCase):
    async def test_credential_call_rejects_raw_input_without_exposing_it(self) -> None:
        from inframeld_sdk.api.access_api import AccessApi

        secret = "synthetic-provider-marker-32"
        client = inframeld_sdk.ApiClient(inframeld_sdk.Configuration(host="http://sdk.test"))

        def reject_request(request: httpx.Request) -> httpx.Response:
            self.fail("Invalid credential input reached HTTP dispatch.")

        client.rest_client.pool_manager = httpx.AsyncClient(
            transport=httpx.MockTransport(reject_request)
        )
        api = AccessApi(client)
        project = UUID("00000000-0000-4000-0000-000000000003")
        connection = UUID("00000000-0000-4000-0000-000000000004")
        try:
            for body, classification in (
                ({"expectedCredentialRevision": 0, "value": secret.encode()}, "string_type"),
                ({"value": secret}, "missing"),
            ):
                with self.subTest(classification=classification):
                    # Exercise a malformed raw mapping explicitly across the typed boundary.
                    request = cast(inframeld_sdk.ModelConnectionCredentialRequest, body)
                    with self.assertRaises(ValidationError) as async_failure:
                        await api.put_model_connection_credential(
                            project, connection, "synthetic", request
                        )
                    with self.assertRaises(ValidationError) as sync_failure:
                        api.put_model_connection_credential_sync(
                            project, connection, "synthetic", request
                        )
                    for failure in (async_failure.exception, sync_failure.exception):
                        self.assertEqual(
                            failure.errors(include_input=False)[0]["type"], classification
                        )
                        self.assertFalse(
                            secret in str(failure) or secret in repr(failure),
                            "Credential call diagnostics exposed raw input.",
                        )
        finally:
            await client.close()

    async def test_required_response_cannot_be_null_or_an_undeclared_success(self) -> None:
        from inframeld_sdk.api.access_api import AccessApi
        from inframeld_sdk.exceptions import ApiException

        for status, content in [(200, b"null"), (204, b""), (200, b"\xff")]:
            with self.subTest(status=status):
                client = inframeld_sdk.ApiClient(
                    inframeld_sdk.Configuration(host="http://sdk.test")
                )
                client.rest_client.pool_manager = httpx.AsyncClient(
                    transport=httpx.MockTransport(
                        lambda request, status=status, content=content: httpx.Response(
                            status, content=content, headers={"Content-Type": "application/json"}
                        )
                    )
                )
                try:
                    with self.assertRaises(ApiException) as raised:
                        await AccessApi(client).get_current_session_with_http_info(
                            _request_timeout=1.0
                        )
                    self.assertEqual(raised.exception.status, status)
                    self.assertEqual(raised.exception.raw_data, content)
                    self.assertIsNotNone(raised.exception.__cause__)
                finally:
                    await client.close()

    async def test_nullable_response_preserves_explicit_null(self) -> None:
        from inframeld_sdk_fixtures.api.default_api import DefaultApi

        client = inframeld_sdk_fixtures.ApiClient(
            inframeld_sdk_fixtures.Configuration(host="http://sdk.test")
        )
        client.rest_client.pool_manager = httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200, content=b"null", headers={"Content-Type": "application/json"}
                )
            )
        )
        try:
            result = await DefaultApi(client).contract_fixture_nullable_with_http_info(
                _request_timeout=1.0
            )
            self.assertIsNone(result.data)
        finally:
            await client.close()

    async def test_exact_bodyless_response_precedes_status_class(self) -> None:
        from inframeld_sdk.rest import RESTResponse

        client = inframeld_sdk.ApiClient()
        response = RESTResponse(
            httpx.Response(204, content=b"", headers={"Content-Type": "application/json"})
        )
        response.data = b""
        try:
            result = client.response_deserialize(response, {"204": None, "2XX": "Dict[str, str]"})
            self.assertEqual(result.status_code, 204)
            self.assertIsNone(result.data)
        finally:
            await client.close()

    async def test_success_retains_repeated_headers(self) -> None:
        from inframeld_sdk.rest import RESTResponse

        client = inframeld_sdk.ApiClient()
        response = RESTResponse(
            httpx.Response(
                200,
                content=b'{"principalId":"00000000-0000-4000-8000-000000000001"}',
                headers=[
                    ("Content-Type", "application/json"),
                    ("Set-Cookie", "a=1"),
                    ("Set-Cookie", "b=2"),
                ],
            )
        )
        response.data = response.response.content
        try:
            result = client.response_deserialize(response, {"200": "CurrentSessionResponse"})
            self.assertIsInstance(result.headers, httpx.Headers)
            assert result.headers is not None
            self.assertEqual(result.headers.get_list("set-cookie"), ["a=1", "b=2"])
            serialized = _JSON_OBJECT.validate_json(result.model_dump_json())
            pairs = serialized["headers"]
            assert isinstance(pairs, list)
            self.assertEqual(
                [
                    entry[1]
                    for entry in pairs
                    if isinstance(entry, list) and len(entry) == 2 and entry[0] == "set-cookie"
                ],
                ["a=1", "b=2"],
            )
        finally:
            await client.close()


if __name__ == "__main__":
    unittest.main()
