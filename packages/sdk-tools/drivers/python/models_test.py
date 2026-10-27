"""Challenge the selected generated models, separately from HTTP scenarios."""

import unittest
from typing import assert_type

import httpx
import inframeld_sdk
import inframeld_sdk_fixtures
from observations import NativeModel
from pydantic import JsonValue, TypeAdapter

Model = inframeld_sdk_fixtures.ContractFixturePayload | inframeld_sdk.ProjectUseOnlyGrantResponse
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
grant_type = inframeld_sdk.ProjectUseOnlyGrantResponse
payload: dict[str, JsonValue] = {
    "required_name": "valid",
    "required_nullable": None,
    "choice": 7,
    "score": 0.5,
}
grant: dict[str, JsonValue] = {
    "accessRevision": 1,
    "actionId": "create-access-groups",
    "canGrant": False,
    "idempotencyExpiresAt": "2030-01-01T00:00:00Z",
    "operationId": "sdk-operation",
    "projectId": "00000000-0000-4000-8000-000000000003",
    "recipientPrincipalId": "00000000-0000-4000-8000-000000000002",
}


def parse(
    cls: type[inframeld_sdk_fixtures.ContractFixturePayload]
    | type[inframeld_sdk.ProjectUseOnlyGrantResponse],
    data: dict[str, JsonValue],
) -> Model:
    value = cls.from_dict(data)
    if value is None:
        raise ValueError("Expected a native model")
    return value


def rejects(
    cls: type[inframeld_sdk_fixtures.ContractFixturePayload]
    | type[inframeld_sdk.ProjectUseOnlyGrantResponse],
    data: dict[str, JsonValue],
) -> bool:
    try:
        parse(cls, data)
    except (ValueError, KeyError, TypeError):
        return True
    return False


def _rejects_native_null() -> bool:
    try:
        grant_type.model_validate(grant | {"canGrant": None})
    except ValueError:
        return True
    return False


class GeneratedModelTests(unittest.TestCase):
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

    def test_boolean_constant_accepts_false(self) -> None:
        self.assertTrue(body_value(parse(grant_type, grant))["canGrant"] is False)

    def test_boolean_constant_rejects_true(self) -> None:
        self.assertTrue(rejects(grant_type, grant | {"canGrant": True}))

    def test_nonnullable_rejects_null_from_dict(self) -> None:
        with self.assertRaises(ValueError):
            grant_type.from_dict(grant | {"canGrant": None})

    def test_nonnullable_rejects_null_native_model(self) -> None:
        self.assertTrue(_rejects_native_null())

    def test_scalar_union_rejects_boolean(self) -> None:
        self.assertTrue(rejects(payload_type, payload | {"choice": True}))

    def test_scalar_union_rejects_array(self) -> None:
        self.assertTrue(rejects(payload_type, payload | {"choice": []}))

    def test_required_string_rejects_integer(self) -> None:
        self.assertTrue(rejects(payload_type, payload | {"required_name": 123}))


class ResponseIntegrityTests(unittest.IsolatedAsyncioTestCase):
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
