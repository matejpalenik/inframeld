import os
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import pytest

from inframeld_backend.access.application.dtos.provider_credential_binding_dto import (
    ProviderCredentialBindingDTO,
)
from inframeld_backend.access.application.value_objects.provider_credential_value import (
    ProviderCredentialValue,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.resources.pynacl_provider_credential_cipher import (
    PyNaClProviderCredentialCipher,
)
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.application.value_objects.model_connection_id import ModelConnectionId

_ROOT = bytes(range(32))
_ROOT_ID = sha256(_ROOT).hexdigest()
_FINGERPRINT_ID = sha256(bytes(reversed(_ROOT))).hexdigest()
_TOKEN = "synthetic-provider-key.123+/_~="
_BINDING = ProviderCredentialBindingDTO(
    OrganizationId(uuid4()), ProjectId(uuid4()), ModelConnectionId(uuid4()), uuid4(), 7
)


def _key(path: Path, value: bytes) -> None:
    path.write_bytes(value)
    path.chmod(0o600)


def test_credential_survives_reopen_with_unique_nonce_and_exact_binding(tmp_path: Path) -> None:
    key_file = tmp_path / "root.key"
    _key(key_file, _ROOT)
    cipher = PyNaClProviderCredentialCipher(key_file, _ROOT_ID, _FINGERPRINT_ID)
    plaintext = ProviderCredentialValue(_TOKEN)

    first = cipher.encrypt(plaintext, _BINDING, None)
    second = cipher.encrypt(plaintext, _BINDING, first.key_id)

    assert first.key_id == _ROOT_ID
    assert first.message[:24] != second.message[:24]
    assert len(first.message) == len(_TOKEN) + 40
    assert _TOKEN.encode() not in first.message
    assert _TOKEN not in repr(plaintext)
    assert repr(first.message) not in repr(first)
    reopened = PyNaClProviderCredentialCipher(key_file, _ROOT_ID, _FINGERPRINT_ID)
    assert reopened.decrypt(first, _BINDING) == plaintext
    assert reopened.decrypt(second, _BINDING) == plaintext

    for different_binding in (
        replace(_BINDING, organization_id=OrganizationId(uuid4())),
        replace(_BINDING, project_id=ProjectId(uuid4())),
        replace(_BINDING, connection_id=ModelConnectionId(uuid4())),
        replace(_BINDING, credential_id=uuid4()),
        replace(_BINDING, revision=_BINDING.revision + 1),
    ):
        with pytest.raises(DependencyUnavailableError, match="credential cannot be opened"):
            reopened.decrypt(first, different_binding)
    for damaged in (
        replace(first, message=bytes([first.message[0] ^ 1]) + first.message[1:]),
        replace(first, message=first.message[:-1]),
        replace(first, message=first.message[:39]),
        replace(first, format_version=2),
        replace(first, algorithm="unrecognized"),
        replace(first, key_id=_FINGERPRINT_ID),
    ):
        with pytest.raises(DependencyUnavailableError, match="credential cannot be opened"):
            reopened.decrypt(damaged, _BINDING)


def test_first_slot_cannot_enroll_a_wrong_or_shared_root(tmp_path: Path) -> None:
    key_file = tmp_path / "root.key"
    cipher = PyNaClProviderCredentialCipher(key_file, _ROOT_ID, _FINGERPRINT_ID)
    with pytest.raises(DependencyUnavailableError, match="encryption key is unavailable"):
        cipher.require_key(None)
    _key(key_file, bytes(reversed(_ROOT)))
    with pytest.raises(DependencyUnavailableError, match="encryption key is unavailable"):
        cipher.require_key(None)
    assert key_file.read_bytes() == bytes(reversed(_ROOT))
    _key(key_file, _ROOT)
    for key_id, fingerprint_id in ((None, _FINGERPRINT_ID), (_ROOT_ID, _ROOT_ID)):
        with pytest.raises(DependencyUnavailableError, match="encryption key is unavailable"):
            PyNaClProviderCredentialCipher(key_file, key_id, fingerprint_id).require_key(None)
    with pytest.raises(DependencyUnavailableError, match="encryption key is unavailable"):
        cipher.require_key(_FINGERPRINT_ID)
    key_file.chmod(0o644)
    with pytest.raises(DependencyUnavailableError, match="encryption key is unavailable"):
        cipher.require_key(None)
    with pytest.raises(DependencyUnavailableError, match="encryption key is unavailable"):
        PyNaClProviderCredentialCipher(tmp_path, _ROOT_ID, _FINGERPRINT_ID).require_key(None)
    pipe = tmp_path / "pipe"
    os.mkfifo(pipe, 0o600)
    with pytest.raises(DependencyUnavailableError, match="encryption key is unavailable"):
        PyNaClProviderCredentialCipher(pipe, _ROOT_ID, _FINGERPRINT_ID).require_key(None)


@pytest.mark.parametrize(
    "token", ["", "Bearer key", "key\r\n", "key\x00", "é", "x=a", "x" * 16_385]
)
def test_invalid_bearer_value_is_rejected_without_reflection(token: str) -> None:
    with pytest.raises(ValueError, match="supported provider bearer token"):
        ProviderCredentialValue(token)


def test_maximum_bearer_value_is_kept_exactly() -> None:
    token = "x" * 16_384
    assert ProviderCredentialValue(token).value == token
