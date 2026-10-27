import os
from unittest.mock import patch

import pytest

from inframeld_backend.bootstrap.recovery_worker import main


def test_invalid_worker_configuration_fails_before_io_without_disclosing_values(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # No complete database or authority configuration is supplied.
    with patch.dict(os.environ, {"INFRAMELD_DATABASE__PASSWORD": "private-value"}, clear=True):
        assert main() == 2
    assert capsys.readouterr().out.strip() == '{"code":"invalid_configuration"}'
