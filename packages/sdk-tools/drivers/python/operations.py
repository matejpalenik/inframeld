"""Direct native operation calls, with one explicit sync/async binding inventory."""

import base64
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from uuid import UUID

import inframeld_sdk
import inframeld_sdk_fixtures
from inframeld_sdk.api.access_api import AccessApi
from inframeld_sdk.api.health_api import HealthApi
from inframeld_sdk.models.human_o_auth_consent_request import HumanOAuthConsentRequest
from inframeld_sdk.models.project_use_only_grant_request import ProjectUseOnlyGrantRequest
from inframeld_sdk_fixtures.api.default_api import DefaultApi
from inframeld_sdk_fixtures.models.contract_fixture_payload import ContractFixturePayload
from observations import NativeResponse
from protocol import Call, Operation


@dataclass(frozen=True)
class Clients:
    production: inframeld_sdk.ApiClient
    fixtures: inframeld_sdk_fixtures.ApiClient


def string(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("Expected a string in the driver call")
    return value


def integer(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("Expected an integer in the driver call")
    return value


def grant_body(call: Call) -> ProjectUseOnlyGrantRequest:
    if not call.unchecked_model:
        return ProjectUseOnlyGrantRequest.model_validate(call.body)
    if call.body is None:
        raise ValueError("Missing body for unchecked server-validation case")
    return ProjectUseOnlyGrantRequest.model_construct(
        action_id=string(call.body["actionId"]),
        recipient_principal_id=UUID(string(call.body["recipientPrincipalId"])),
        expected_access_revision=integer(call.body["expectedAccessRevision"]),
    )


def payload_body(call: Call) -> ContractFixturePayload:
    value = ContractFixturePayload.from_dict(call.body)
    if value is None:
        raise ValueError("Payload requires a body")
    return value


def health_sync(clients: Clients, call: Call) -> NativeResponse:
    return HealthApi(clients.production).get_health_sync_with_http_info(
        _request_timeout=call.timeout / 1000,
        _headers=call.headers,
    )


async def health_async(clients: Clients, call: Call) -> NativeResponse:
    return await HealthApi(clients.production).get_health_with_http_info(
        _request_timeout=call.timeout / 1000,
        _headers=call.headers,
    )


def session_sync(clients: Clients, call: Call) -> NativeResponse:
    return AccessApi(clients.production).get_current_session_sync_with_http_info(
        _request_timeout=call.timeout / 1000,
        _headers=call.headers,
    )


async def session_async(clients: Clients, call: Call) -> NativeResponse:
    return await AccessApi(clients.production).get_current_session_with_http_info(
        _request_timeout=call.timeout / 1000,
        _headers=call.headers,
    )


def inspect_consent_sync(clients: Clients, call: Call) -> NativeResponse:
    return AccessApi(clients.production).inspect_human_o_auth_consent_sync_with_http_info(
        consent_challenge=string(call.query["consent_challenge"]),
        _request_timeout=call.timeout / 1000,
        _headers=call.headers,
    )


async def inspect_consent_async(clients: Clients, call: Call) -> NativeResponse:
    return await AccessApi(clients.production).inspect_human_o_auth_consent_with_http_info(
        consent_challenge=string(call.query["consent_challenge"]),
        _request_timeout=call.timeout / 1000,
        _headers=call.headers,
    )


def decide_consent_sync(clients: Clients, call: Call) -> NativeResponse:
    return AccessApi(clients.production).decide_human_o_auth_consent_sync_with_http_info(
        human_o_auth_consent_request=HumanOAuthConsentRequest.model_validate(call.body),
        _request_timeout=call.timeout / 1000,
        _headers=call.headers,
    )


async def decide_consent_async(clients: Clients, call: Call) -> NativeResponse:
    return await AccessApi(clients.production).decide_human_o_auth_consent_with_http_info(
        human_o_auth_consent_request=HumanOAuthConsentRequest.model_validate(call.body),
        _request_timeout=call.timeout / 1000,
        _headers=call.headers,
    )


def assign_grant_sync(clients: Clients, call: Call) -> NativeResponse:
    return AccessApi(clients.production).assign_project_use_only_grant_sync_with_http_info(
        project_id=UUID(call.path["project_id"]),
        idempotency_key=call.headers["Idempotency-Key"],
        project_use_only_grant_request=grant_body(call),
        _request_timeout=call.timeout / 1000,
        _headers=call.headers,
    )


async def assign_grant_async(clients: Clients, call: Call) -> NativeResponse:
    return await AccessApi(clients.production).assign_project_use_only_grant_with_http_info(
        project_id=UUID(call.path["project_id"]),
        idempotency_key=call.headers["Idempotency-Key"],
        project_use_only_grant_request=grant_body(call),
        _request_timeout=call.timeout / 1000,
        _headers=call.headers,
    )


def payload_sync(clients: Clients, call: Call) -> NativeResponse:
    return DefaultApi(clients.fixtures).contract_fixture_payload_sync_with_http_info(
        contract_fixture_payload=payload_body(call),
        _request_timeout=call.timeout / 1000,
        _headers=call.headers,
    )


async def payload_async(clients: Clients, call: Call) -> NativeResponse:
    return await DefaultApi(clients.fixtures).contract_fixture_payload_with_http_info(
        contract_fixture_payload=payload_body(call),
        _request_timeout=call.timeout / 1000,
        _headers=call.headers,
    )


def page_sync(clients: Clients, call: Call) -> NativeResponse:
    return DefaultApi(clients.fixtures).contract_fixture_page_sync_with_http_info(
        limit=integer(call.query["limit"]) if "limit" in call.query else None,
        cursor=string(call.query["cursor"]) if "cursor" in call.query else None,
        _request_timeout=call.timeout / 1000,
        _headers=call.headers,
    )


async def page_async(clients: Clients, call: Call) -> NativeResponse:
    return await DefaultApi(clients.fixtures).contract_fixture_page_with_http_info(
        limit=integer(call.query["limit"]) if "limit" in call.query else None,
        cursor=string(call.query["cursor"]) if "cursor" in call.query else None,
        _request_timeout=call.timeout / 1000,
        _headers=call.headers,
    )


def upload_sync(clients: Clients, call: Call) -> NativeResponse:
    source = call.body
    if source is None:
        raise ValueError("Upload requires a body")
    return DefaultApi(clients.fixtures).contract_fixture_upload_sync_with_http_info(
        file=(
            string(source["fileName"]),
            base64.b64decode(string(source["fileBase64"]), validate=True),
        ),
        label=string(source["label"]),
        _request_timeout=call.timeout / 1000,
        _headers=call.headers,
    )


async def upload_async(clients: Clients, call: Call) -> NativeResponse:
    source = call.body
    if source is None:
        raise ValueError("Upload requires a body")
    return await DefaultApi(clients.fixtures).contract_fixture_upload_with_http_info(
        file=(
            string(source["fileName"]),
            base64.b64decode(string(source["fileBase64"]), validate=True),
        ),
        label=string(source["label"]),
        _request_timeout=call.timeout / 1000,
        _headers=call.headers,
    )


def nullable_sync(clients: Clients, call: Call) -> NativeResponse:
    return DefaultApi(clients.fixtures).contract_fixture_nullable_sync_with_http_info(
        _request_timeout=call.timeout / 1000,
        _headers=call.headers,
    )


async def nullable_async(clients: Clients, call: Call) -> NativeResponse:
    return await DefaultApi(clients.fixtures).contract_fixture_nullable_with_http_info(
        _request_timeout=call.timeout / 1000,
        _headers=call.headers,
    )


def empty_sync(clients: Clients, call: Call) -> NativeResponse:
    return DefaultApi(clients.fixtures).contract_fixture_empty_sync_with_http_info(
        _request_timeout=call.timeout / 1000,
        _headers=call.headers,
    )


async def empty_async(clients: Clients, call: Call) -> NativeResponse:
    return await DefaultApi(clients.fixtures).contract_fixture_empty_with_http_info(
        _request_timeout=call.timeout / 1000,
        _headers=call.headers,
    )


@dataclass(frozen=True)
class Binding:
    sync: Callable[[Clients, Call], NativeResponse]
    asynchronous: Callable[[Clients, Call], Awaitable[NativeResponse]]
    has_body: bool = True


def variants_sync(clients: Clients, call: Call) -> NativeResponse:
    return DefaultApi(clients.fixtures).contract_fixture_variants_sync_with_http_info(
        mode=string(call.query["mode"]) if "mode" in call.query else None,
        _request_timeout=call.timeout / 1000,
        _headers=call.headers,
    )


async def variants_async(clients: Clients, call: Call) -> NativeResponse:
    return await DefaultApi(clients.fixtures).contract_fixture_variants_with_http_info(
        mode=string(call.query["mode"]) if "mode" in call.query else None,
        _request_timeout=call.timeout / 1000,
        _headers=call.headers,
    )


def media_sync(clients: Clients, call: Call) -> NativeResponse:
    return DefaultApi(clients.fixtures).contract_fixture_media_sync_with_http_info(
        _request_timeout=call.timeout / 1000,
        _headers=call.headers,
    )


async def media_async(clients: Clients, call: Call) -> NativeResponse:
    return await DefaultApi(clients.fixtures).contract_fixture_media_with_http_info(
        _request_timeout=call.timeout / 1000,
        _headers=call.headers,
    )


def fallback_sync(clients: Clients, call: Call) -> NativeResponse:
    return DefaultApi(clients.fixtures).contract_fixture_fallback_sync_with_http_info(
        mode=string(call.query["mode"]) if "mode" in call.query else None,
        _request_timeout=call.timeout / 1000,
        _headers=call.headers,
    )


async def fallback_async(clients: Clients, call: Call) -> NativeResponse:
    return await DefaultApi(clients.fixtures).contract_fixture_fallback_with_http_info(
        mode=string(call.query["mode"]) if "mode" in call.query else None,
        _request_timeout=call.timeout / 1000,
        _headers=call.headers,
    )


BINDINGS: dict[Operation, Binding] = {
    "contractFixtureVariants": Binding(variants_sync, variants_async),
    "contractFixtureFallback": Binding(fallback_sync, fallback_async),
    "contractFixtureMedia": Binding(media_sync, media_async),
    "getHealth": Binding(health_sync, health_async),
    "getCurrentSession": Binding(session_sync, session_async),
    "inspectHumanOAuthConsent": Binding(inspect_consent_sync, inspect_consent_async),
    "decideHumanOAuthConsent": Binding(decide_consent_sync, decide_consent_async),
    "assignProjectUseOnlyGrant": Binding(assign_grant_sync, assign_grant_async),
    "contractFixturePayload": Binding(payload_sync, payload_async),
    "contractFixturePage": Binding(page_sync, page_async),
    "contractFixtureUpload": Binding(upload_sync, upload_async),
    "contractFixtureNullable": Binding(nullable_sync, nullable_async),
    "contractFixtureEmpty": Binding(empty_sync, empty_async, has_body=False),
}
