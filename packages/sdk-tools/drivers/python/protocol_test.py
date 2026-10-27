"""Invalid control documents must fail as driver errors before SDK invocation."""

import unittest

from protocol import DriverRequest
from pydantic import ValidationError


class ProtocolTests(unittest.TestCase):
    def test_unsupported_protocol_version_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            DriverRequest.model_validate_json(
                '{"version": 1, "profile": "python-sync", "caseId": "one", "baseUrl": "http://localhost", "calls": [{"id": "one", "operation": "getHealth", "headers": {}, "timeout": 100}]}'
            )


if __name__ == "__main__":
    unittest.main()
