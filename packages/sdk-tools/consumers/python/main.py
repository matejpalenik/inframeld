"""Use an installed wheel through both native public lifecycles."""

import asyncio
import importlib.util
import json
import sys
from importlib.metadata import version

import httpx
import inframeld_sdk
from inframeld_sdk.api.access_api import AccessApi
from inframeld_sdk.api.health_api import HealthApi
from inframeld_sdk.exceptions import ApiException
from inframeld_sdk.sync_helper import run_sync


def synchronous(base_url: str) -> None:
    client = inframeld_sdk.ApiClient(inframeld_sdk.Configuration(host=base_url))
    try:
        health = HealthApi(client).get_health_sync_with_http_info(_request_timeout=2.0)
        assert health.status_code == 200 and health.data["status"] == "ok"
        session = AccessApi(client).get_current_session_sync_with_http_info(
            _headers={"Authorization": "Bearer sdk-human"}, _request_timeout=2.0
        )
        assert str(session.data.principal_id) == "00000000-0000-4000-8000-000000000001"
        assert isinstance(session.headers, httpx.Headers)
        try:
            AccessApi(client).get_current_session_sync_with_http_info(_request_timeout=2.0)
        except ApiException as error:
            assert (
                error.status == 401 and error.headers is not None and error.body and error.raw_data
            )
        else:
            raise AssertionError("Missing authentication must fail")
        # A used client remains reusable after an SDK error.
        assert (
            HealthApi(client).get_health_sync_with_http_info(_request_timeout=2.0).status_code
            == 200
        )
    finally:
        run_sync(client.close())
    assert client.rest_client.pool_manager is not None
    assert client.rest_client.pool_manager.is_closed


async def asynchronous(base_url: str) -> None:
    client = inframeld_sdk.ApiClient(inframeld_sdk.Configuration(host=base_url))
    try:
        health = await HealthApi(client).get_health_with_http_info(_request_timeout=2.0)
        assert health.status_code == 200 and health.data["status"] == "ok"
        session = await AccessApi(client).get_current_session_with_http_info(
            _headers={"Authorization": "Bearer sdk-human"}, _request_timeout=2.0
        )
        assert str(session.data.principal_id) == "00000000-0000-4000-8000-000000000001"
        assert isinstance(session.headers, httpx.Headers)
        try:
            await AccessApi(client).get_current_session_with_http_info(_request_timeout=2.0)
        except ApiException as error:
            assert (
                error.status == 401 and error.headers is not None and error.body and error.raw_data
            )
        else:
            raise AssertionError("Missing authentication must fail")
        assert (
            await HealthApi(client).get_health_with_http_info(_request_timeout=2.0)
        ).status_code == 200
    finally:
        await client.close()
    assert client.rest_client.pool_manager is not None
    assert client.rest_client.pool_manager.is_closed


def main() -> None:
    assert inframeld_sdk.__version__ == version("inframeld-sdk")
    assert importlib.util.find_spec("inframeld_backend") is None
    assert importlib.util.find_spec("inframeld_sdk_fixtures") is None
    synchronous(sys.argv[1])
    asyncio.run(asynchronous(sys.argv[1]))
    print(
        json.dumps(
            {
                "python": sys.version,
                "httpx": version("httpx"),
                "pydantic": version("pydantic"),
                "package": inframeld_sdk.__file__,
            }
        )
    )


if __name__ == "__main__":
    main()
