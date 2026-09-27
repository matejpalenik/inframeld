"""Check that CSRF configuration contains browser origins, not page URLs."""

import pytest
from pydantic import HttpUrl, ValidationError

from inframeld_backend.access.infrastructure.settings.csrf_settings import CSRFSettings


def test_trusted_origin_rejects_url_with_path() -> None:
    """Reject a page URL where the operator must configure an origin."""
    with pytest.raises(ValidationError):
        CSRFSettings(trusted_origins=(HttpUrl("https://studio.example/settings"),))
