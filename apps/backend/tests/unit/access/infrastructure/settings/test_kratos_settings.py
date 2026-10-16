import pytest
from pydantic import HttpUrl, ValidationError

from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.infrastructure.settings.kratos_settings import KratosSettings


def test_cookie_only_settings_do_not_require_an_admin_url() -> None:
    """Keep existing browser cookie configuration valid before Hydra is enabled."""

    settings = KratosSettings(
        public_url=HttpUrl("http://kratos:4433"), authority=IdentityAuthority("kratos:test")
    )

    assert settings.admin_url is None


def test_admin_url_is_parsed_as_a_typed_endpoint() -> None:
    """Read the operator's explicit admin endpoint without deriving it from the public URL."""

    settings = KratosSettings.model_validate(
        {
            "public_url": "http://kratos:4433",
            "authority": "kratos:test",
            "admin_url": "http://kratos:4434",
        }
    )

    assert settings.public_url == HttpUrl("http://kratos:4433")
    assert settings.admin_url == HttpUrl("http://kratos:4434")


@pytest.mark.parametrize(
    "admin_url",
    [
        "not-a-url",
        "ftp://kratos:4434",
        "http://user:synthetic-password@kratos:4434",
        "http://user@kratos:4434",
        "http://kratos:4434?account=alice",
        "http://kratos:4434#fragment",
        "http://kratos:4434?",
        "http://kratos:4434#",
        " http://kratos:4434",
        "http://kratos:4434 ",
        "http://kra\ttos:4434",
        "http://kratos:not-a-port",
    ],
)
def test_invalid_admin_endpoints_are_rejected(admin_url: str) -> None:
    """Reject credentials, request-specific data and malformed text in the trusted endpoint."""

    with pytest.raises(ValidationError):
        KratosSettings.model_validate(
            {"public_url": "http://kratos:4433", "authority": "kratos:test", "admin_url": admin_url}
        )
