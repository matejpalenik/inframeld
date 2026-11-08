import base64
import hashlib
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


def test_generated_key_has_a_v4_identifier_and_32_canonical_secret_bytes() -> None:
    credential = ApplicationKeyCredential.generate()
    secret = credential.value[45:]

    assert credential.key_id.value.version == 4
    assert len(secret) == 43
    assert len(base64.urlsafe_b64decode(secret + "=")) == 32
    assert ApplicationKeyCredential(credential.value) == credential
    assert credential.value not in repr(credential)
    assert secret not in repr(credential)


def test_separate_fresh_credentials_change_both_identifier_and_secret() -> None:
    first = ApplicationKeyCredential.generate()
    second = ApplicationKeyCredential.generate()

    assert first.key_id != second.key_id
    assert first.value[45:] != second.value[45:]


def test_verifier_hashes_the_complete_key_including_its_identifier() -> None:
    credential = ApplicationKeyCredential(KEY)
    another_id = ApplicationKeyCredential(f"ifm_app_00000000-0000-4000-8000-000000000002_{SECRET}")

    assert credential.digest() == hashlib.sha256(KEY.encode("ascii")).digest()
    assert len(credential.digest()) == 32
    assert credential.digest() != another_id.digest()
