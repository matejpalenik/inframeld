# Inframeld Python SDK

The generated client follows Inframeld's native OpenAPI contract. This package remains version `0.0.0` with publication protection. Building or consuming it requires neither the backend nor a generator. Registry publication and server-version compatibility remain separate work.

Install the `inframeld-sdk` wheel and import `inframeld_sdk`. Generated operations use HTTPX and Pydantic, with async methods and generated synchronous bridge variants. Omitted fields differ from explicit null. Non-nullable values, primitive response types and array/map shapes are decoded strictly. Exact status precedes class/default, then the selected media type determines decoding. Missing content type requires an unambiguous declared representation. Response annotations preserve model alternatives and nullable/bodyless outcomes. Detailed results expose `data`, `status_code`, native HTTPX `headers` and `raw_data`. Repeated values remain accessible through `headers.get_list(...)`. JSON serialization of detailed response headers emits ordered pairs.

HTTP and decoding failures retain `ApiException.status`, `headers`, `body`, exact `raw_data` when available and decoding causes. They may have a successful HTTP status. Never redispatch to recover metadata. The qualified HTTPX runtime disables redirects and retries. The default is five seconds. Default and scalar `_request_timeout` values bound total buffered network/body collection and raise native HTTPX timeout errors. Explicit `(connect, read)` tuples preserve HTTPX phase budgets instead of a total deadline. Supply credentials through generated call headers/configuration. Deliberate caller transport overrides change the qualified policy.

Close an async-used client with `await client.close()`. Close a sync-used client with `run_sync(client.close())` on the generated background loop. Blocking sync calls do not belong inside an async application loop. Async cancellation is qualified, while the public sync bridge does not expose equivalent operation cancellation. General concurrent loop switching and streaming remain unqualified.

The complete [strictly checked consumer](../sdk-tools/consumers/python/main.py) below runs from clean Python 3.11 and primary-interpreter environments, makes real requests and closes used pools in both modes. Replace its fixture credential for actual use.

## Build and use locally

```sh
python -m pip install build
# Run from this package directory. These are this package's owned build outputs.
rm -rf build dist
python -m build
# Install the wheel in a separate environment with python -m pip install /absolute/path/to/archive.whl
```

Rust/TypeScript consumers take the fixture base URL as their first argument. Python uses the same argument. The examples expect the controlled conformance backend, while application callers supply their own server URL and credentials.

```python
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
```

## Maintain generation

Generation is explicit. Follow the [SDK runbook](../sdk-tools/README.md) for verified inputs, drift, native checks and package consumers. Fixtures and development tooling are outside this distribution. Fix generator source or shipped resources before regeneration, never generated SDK output. See the [response-fix evidence](../../docs/development/reports/sdk-response-fixes-verification.md) for actually executed checks and platform limits.
