"""Native values, byte fidelity and conversion failures stay honest at the boundary."""

import unittest
from dataclasses import dataclass
from unittest.mock import patch

import httpx
import inframeld_sdk
import inframeld_sdk_fixtures
from main import execute
from observations import failure, success, wire
from operations import Binding, Clients
from protocol import Call, DriverFailure, DriverRequest


@dataclass
class BrokenResponse:
    status_code: int = 200
    data: object = object()
    headers: httpx.Headers | None = None
    raw_data: bytes = b"{}"


def broken_sync(clients: Clients, call: Call) -> BrokenResponse:
    return BrokenResponse()


async def broken_async(clients: Clients, call: Call) -> BrokenResponse:
    return BrokenResponse()


class ObservationTests(unittest.IsolatedAsyncioTestCase):
    def test_binary_raw_content_and_repeated_headers_survive(self) -> None:
        observed = failure(
            "one",
            ValueError("decode"),
            status=200,
            response_headers=httpx.Headers([("set-cookie", "a=1"), ("set-cookie", "b=2")]),
            raw=b"\xff",
        )
        self.assertEqual(wire(b"\xff").value, "/w==")
        self.assertEqual([entry.value for entry in observed.headers], ["a=1", "b=2"])
        self.assertIsNotNone(observed.raw)

    def test_conversion_does_not_repair_non_json_sdk_values(self) -> None:
        with self.assertRaises(ValueError):
            success("one", BrokenResponse(), True)

    async def test_conversion_defect_is_a_driver_failure(self) -> None:
        request = DriverRequest.model_validate_json(
            '{"version":2,"profile":"python-async","caseId":"one","baseUrl":"http://localhost","calls":[{"id":"one","operation":"getHealth","headers":{},"timeout":1000}]}'
        )
        with patch.dict("main.BINDINGS", {"getHealth": Binding(broken_sync, broken_async)}):
            result = await execute(request)
        self.assertIsInstance(result, DriverFailure)
        assert isinstance(result, DriverFailure)
        self.assertIn("Execution", result.error)

    async def test_execution_and_both_cleanup_failures_are_retained(self) -> None:
        request = DriverRequest.model_validate_json(
            '{"version":2,"profile":"python-async","caseId":"combined","baseUrl":"http://localhost","calls":[{"id":"one","operation":"getHealth","headers":{},"timeout":1000}]}'
        )
        clients = Clients(inframeld_sdk.ApiClient(), inframeld_sdk_fixtures.ApiClient())

        async def close_production() -> None:
            raise RuntimeError("production cleanup")

        async def close_fixtures() -> None:
            raise RuntimeError("fixture cleanup")

        with (
            patch("main.Clients", return_value=clients),
            patch.dict("main.BINDINGS", {"getHealth": Binding(broken_sync, broken_async)}),
            patch.object(clients.production, "close", close_production),
            patch.object(clients.fixtures, "close", close_fixtures),
        ):
            result = await execute(request)
        assert isinstance(result, DriverFailure)
        self.assertIn("Execution", result.error)
        self.assertIn("production cleanup", result.error)
        self.assertIn("fixture cleanup", result.error)
