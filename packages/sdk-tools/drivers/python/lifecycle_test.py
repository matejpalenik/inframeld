"""Public async cancellation releases a used transport and permits client reuse."""

import asyncio
import unittest
from time import monotonic

import httpx
import inframeld_sdk
from inframeld_sdk.api.health_api import HealthApi
from inframeld_sdk.sync_helper import run_sync


class LifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_cancel_active_operation_then_reuse_and_close_used_pool(self) -> None:
        entered = asyncio.Event()
        cancelled = asyncio.Event()
        slow = True

        async def handler(request: httpx.Request) -> httpx.Response:
            if slow:
                entered.set()
                try:
                    await asyncio.sleep(30)
                except asyncio.CancelledError:
                    cancelled.set()
                    raise
            return httpx.Response(200, json={"status": "ok"})

        client = inframeld_sdk.ApiClient(inframeld_sdk.Configuration(host="http://sdk.test"))
        client.rest_client.pool_manager = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        try:
            task = asyncio.create_task(
                HealthApi(client).get_health_with_http_info(_request_timeout=2.0)
            )
            await asyncio.wait_for(entered.wait(), timeout=1)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            self.assertTrue(cancelled.is_set())
            slow = False
            result = await HealthApi(client).get_health_with_http_info(_request_timeout=2.0)
            self.assertEqual(result.data, {"status": "ok"})
        finally:
            await client.close()
        self.assertTrue(client.rest_client.pool_manager.is_closed)


class DeadlineTests(unittest.IsolatedAsyncioTestCase):
    async def test_default_deadline_bounds_a_buffered_response(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            await asyncio.sleep(6)
            return httpx.Response(200, json={"status": "ok"})

        client = inframeld_sdk.ApiClient(inframeld_sdk.Configuration(host="http://sdk.test"))
        client.rest_client.pool_manager = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        started = monotonic()
        try:
            with self.assertRaises(httpx.TimeoutException):
                await HealthApi(client).get_health_with_http_info()
            self.assertGreater(monotonic() - started, 4.5)
            self.assertLess(monotonic() - started, 5.8)
        finally:
            await client.close()
        self.assertTrue(client.rest_client.pool_manager.is_closed)

    async def test_scalar_deadline_cancels_then_allows_reuse(self) -> None:
        count = 0

        async def handler(request: httpx.Request) -> httpx.Response:
            nonlocal count
            count += 1
            if count == 1:
                await asyncio.sleep(0.2)
            return httpx.Response(200, json={"status": "ok"})

        client = inframeld_sdk.ApiClient(inframeld_sdk.Configuration(host="http://sdk.test"))
        client.rest_client.pool_manager = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        try:
            with self.assertRaises(httpx.TimeoutException):
                await HealthApi(client).get_health_with_http_info(_request_timeout=0.025)
            self.assertEqual(
                (await HealthApi(client).get_health_with_http_info(_request_timeout=0.1)).data,
                {"status": "ok"},
            )
            self.assertEqual(count, 2)
        finally:
            await client.close()

    async def test_explicit_tuple_keeps_native_phase_budgets(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.extensions["timeout"]["connect"], 0.1)
            self.assertEqual(request.extensions["timeout"]["read"], 0.2)
            return httpx.Response(200, json={"status": "ok"})

        client = inframeld_sdk.ApiClient(inframeld_sdk.Configuration(host="http://sdk.test"))
        client.rest_client.pool_manager = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        try:
            self.assertEqual(
                (
                    await HealthApi(client).get_health_with_http_info(_request_timeout=(0.1, 0.2))
                ).status_code,
                200,
            )
        finally:
            await client.close()


class SyncDeadlineTests(unittest.TestCase):
    def test_sync_deadline_then_reuse_and_close_used_pool(self) -> None:
        count = 0

        async def handler(request: httpx.Request) -> httpx.Response:
            nonlocal count
            count += 1
            if count == 1:
                await asyncio.sleep(0.2)
            return httpx.Response(200, json={"status": "ok"})

        client = inframeld_sdk.ApiClient(inframeld_sdk.Configuration(host="http://sdk.test"))
        client.rest_client.pool_manager = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        try:
            with self.assertRaises(httpx.TimeoutException):
                HealthApi(client).get_health_sync_with_http_info(_request_timeout=0.025)
            self.assertEqual(
                HealthApi(client).get_health_sync_with_http_info(_request_timeout=0.1).data,
                {"status": "ok"},
            )
            self.assertEqual(count, 2)
        finally:
            run_sync(client.close())
        self.assertTrue(client.rest_client.pool_manager.is_closed)


class EncodedPathTests(unittest.IsolatedAsyncioTestCase):
    async def test_invalid_paths_never_dispatch(self) -> None:
        from inframeld_sdk.api.discovery_api import DiscoveryApi

        count = 0

        async def handler(request: httpx.Request) -> httpx.Response:
            nonlocal count
            count += 1
            return httpx.Response(500)

        client = inframeld_sdk.ApiClient(inframeld_sdk.Configuration(host="http://sdk.test"))
        client.rest_client.pool_manager = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        try:
            for value in [
                "/absolute",
                "a?x=1",
                "a#fragment",
                "a\\b",
                "a%",
                "a%GG",
                "../admin",
                "a/%2e%2e/admin",
                "a%00b",
                "a%FF",
                "a b",
                "a" * 24577,
            ]:
                with self.assertRaises(ValueError):
                    await DiscoveryApi(
                        client
                    ).get_protected_resource_metadata_for_path_with_http_info(value)
                with self.assertRaises(ValueError):
                    await asyncio.to_thread(
                        DiscoveryApi(
                            client
                        ).get_protected_resource_metadata_for_path_sync_with_http_info,
                        value,
                    )
            self.assertEqual(count, 0)
        finally:
            await client.close()

    async def test_maximum_encoded_path_dispatches_sync_and_async(self) -> None:
        from inframeld_sdk.api.discovery_api import DiscoveryApi

        path = "a" * 24576
        count = 0

        async def handler(request: httpx.Request) -> httpx.Response:
            nonlocal count
            count += 1
            self.assertEqual(
                request.url.raw_path,
                b"/.well-known/oauth-protected-resource/" + path.encode("ascii"),
            )
            return httpx.Response(
                200,
                json={
                    "resource": "https://api.test",
                    "authorization_servers": ["https://auth.test/"],
                    "scopes_supported": ["inframeld:api"],
                    "bearer_methods_supported": ["header"],
                    "inframeld": {
                        "schema_version": 1,
                        "client_id": "inframeld-cli",
                        "installation_id": "00000000-0000-4000-8000-000000000001",
                    },
                },
            )

        for synchronous in (False, True):
            with self.subTest(synchronous=synchronous):
                client = inframeld_sdk.ApiClient(
                    inframeld_sdk.Configuration(host="http://sdk.test")
                )
                client.rest_client.pool_manager = httpx.AsyncClient(
                    transport=httpx.MockTransport(handler)
                )
                api = DiscoveryApi(client)
                try:
                    if synchronous:
                        response = await asyncio.to_thread(
                            api.get_protected_resource_metadata_for_path_sync_with_http_info, path
                        )
                    else:
                        response = (
                            await api.get_protected_resource_metadata_for_path_with_http_info(path)
                        )
                    self.assertEqual(response.status_code, 200)
                    assert response.data is not None
                    self.assertEqual(response.data.resource, "https://api.test")
                finally:
                    if synchronous:
                        await asyncio.to_thread(run_sync, client.close())
                    else:
                        await client.close()
        self.assertEqual(count, 2)
