import pytest

from inframeld_backend.access.cli.mappers.maintenance_input_mapper import MaintenanceInputMapper


@pytest.mark.parametrize(
    "payload", [b"x", b"{}{}", b"[]", b'{"mode":"a","mode":"b"}', b'{"x":NaN}', b" " * 65537]
)
def test_invalid_framing_or_oversize_input_is_rejected(payload: bytes) -> None:
    with pytest.raises((ValueError, TypeError)):
        MaintenanceInputMapper.read(payload)


def test_safe_original_correlation_is_retained_without_secret_reflection() -> None:
    values = MaintenanceInputMapper.read(
        b'{"operationId":"original","identityProof":{"accessToken":"secret"}}'
    )
    correlation = MaintenanceInputMapper.correlation(values)
    assert correlation is not None and correlation.value == "original"
