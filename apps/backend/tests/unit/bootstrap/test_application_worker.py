import pytest

from inframeld_backend.bootstrap.application_worker import main


def test_invalid_configuration_fails_safely_before_any_worker_resources(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for key in ("HOST", "NAME", "USER", "PASSWORD"):
        monkeypatch.delenv("INFRAMELD_DATABASE__" + key, raising=False)
    assert main() == 2
    assert capsys.readouterr().out == '{"code":"invalid_configuration"}\n'
