import base64
from uuid import UUID

import pytest

from inframeld_backend.access.application.value_objects.application_key_credential import (
    ApplicationKeyCredential,
)
from inframeld_backend.access.domain.value_objects.application_key_id import ApplicationKeyId

KEY_ID = UUID("00000000-0000-4000-8000-000000000001")
SECRET = base64.urlsafe_b64encode(b"S" * 32).decode().rstrip("=")
KEY = f"ifm_app_{KEY_ID}_{SECRET}"


def test_complete_canonical_key_exposes_only_its_lookup_identifier() -> None:
    credential = ApplicationKeyCredential(KEY)
    assert credential.key_id == ApplicationKeyId(KEY_ID)
    assert KEY not in repr(credential)
    assert SECRET not in repr(credential)


@pytest.mark.parametrize(
    "value",
    [
        "",
        "ifm_app_",
        f"ifm_app_{KEY_ID}",
        KEY + "=",
        " " + KEY,
        KEY + "\n",
        KEY[:-1],
        KEY.replace("ifm_app_", "IFM_APP_"),
        KEY[:-1] + "!",
    ],
)
def test_noncanonical_or_incomplete_key_is_rejected_without_echo(value: str) -> None:
    with pytest.raises(ValueError) as rejected:
        ApplicationKeyCredential(value)
    assert SECRET not in str(rejected.value)


def test_noncanonical_base64_tail_is_rejected() -> None:
    secret = base64.urlsafe_b64encode(bytes(32)).decode().rstrip("=")
    with pytest.raises(ValueError):
        ApplicationKeyCredential(f"ifm_app_{KEY_ID}_{secret[:-1]}B")
