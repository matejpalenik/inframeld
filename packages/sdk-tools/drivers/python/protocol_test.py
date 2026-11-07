"""Invalid control documents must fail as driver errors before SDK invocation."""

import json
import unittest

from protocol import DriverRequest
from pydantic import JsonValue, ValidationError


class ProtocolTests(unittest.TestCase):
    def test_application_identity_is_a_header_only_known_operation(self) -> None:
        source: dict[str, JsonValue] = {
            "version": 2,
            "profile": "python-sync",
            "caseId": "application-session",
            "baseUrl": "http://localhost/",
            "calls": [
                {
                    "id": "identity",
                    "operation": "getCurrentApplicationSession",
                    "headers": {"Authorization": "Bearer synthetic-input"},
                    "timeout": 100,
                }
            ],
        }
        request = DriverRequest.model_validate_json(json.dumps(source))
        self.assertEqual(
            json.loads(request.model_dump_json(by_alias=True, exclude_unset=True)), source
        )

    def test_json_enums_round_trip_without_relaxing_the_protocol(self) -> None:
        source: dict[str, JsonValue] = {
            "version": 2,
            "profile": "python-sync",
            "caseId": "one",
            "baseUrl": "http://localhost/",
            "calls": [{"id": "one", "operation": "getHealth", "headers": {}, "timeout": 100}],
        }
        request = DriverRequest.model_validate_json(json.dumps(source))
        self.assertEqual(
            json.loads(request.model_dump_json(by_alias=True, exclude_unset=True)), source
        )
        for changes in ({"profile": "unknown"}, {"unexpected": True}):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                DriverRequest.model_validate_json(json.dumps(source | changes))
        with self.assertRaises(ValidationError):
            DriverRequest.model_validate_json(
                json.dumps(
                    source
                    | {
                        "calls": [
                            {"id": "one", "operation": "unknown", "headers": {}, "timeout": 100}
                        ]
                    }
                )
            )

    def test_unsupported_protocol_version_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            DriverRequest.model_validate_json(
                '{"version": 1, "profile": "python-sync", "caseId": "one", "baseUrl": "http://localhost", "calls": [{"id": "one", "operation": "getHealth", "headers": {}, "timeout": 100}]}'
            )


if __name__ == "__main__":
    unittest.main()
