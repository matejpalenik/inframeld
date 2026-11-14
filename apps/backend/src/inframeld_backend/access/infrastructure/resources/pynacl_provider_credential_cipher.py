import os
import re
import stat
from hashlib import sha256
from hmac import compare_digest
from pathlib import Path
from typing import override

from nacl.exceptions import CryptoError
from nacl.secret import Aead

from inframeld_backend.access.application.dtos.encrypted_provider_credential_dto import (
    EncryptedProviderCredentialDTO,
)
from inframeld_backend.access.application.dtos.provider_credential_binding_dto import (
    ProviderCredentialBindingDTO,
)
from inframeld_backend.access.application.protocols.provider_credential_cipher import (
    ProviderCredentialCipher,
)
from inframeld_backend.access.application.value_objects.provider_credential_value import (
    ProviderCredentialValue,
)
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation

_KEY_ID = re.compile(r"[0-9a-f]{64}")
_FORMAT = 1
_ALGORITHM = "xchacha20-poly1305"
_PURPOSE = b"inframeld:provider-credential:v1\x00"
_ENVELOPE_OVERHEAD = Aead.NONCE_SIZE + Aead.MACBYTES
_KEY_UNAVAILABLE = "The provider credential encryption key is unavailable."
_CREDENTIAL_UNUSABLE = "The stored provider credential cannot be opened."


class PyNaClProviderCredentialCipher(ProviderCredentialCipher):
    """Use only the separately configured deployment key, even for the first write."""

    def __init__(
        self, key_file: Path | None, expected_key_id: str | None, fingerprint_key_id: str
    ) -> None:
        self._key_file = key_file
        self._expected_key_id = expected_key_id
        self._fingerprint_key_id = fingerprint_key_id

    @override
    def require_key(self, current_key_id: str | None) -> None:
        self._open(current_key_id)

    @override
    def encrypt(
        self,
        value: ProviderCredentialValue,
        binding: ProviderCredentialBindingDTO,
        current_key_id: str | None,
    ) -> EncryptedProviderCredentialDTO:
        cipher, key_id = self._open(current_key_id)
        try:
            message = bytes(
                cipher.encrypt(value.value.encode("ascii"), self._associated_data(binding))
            )
        except CryptoError:
            raise DependencyUnavailableError(_KEY_UNAVAILABLE) from None
        return EncryptedProviderCredentialDTO(_FORMAT, _ALGORITHM, key_id, message)

    def decrypt(
        self, envelope: EncryptedProviderCredentialDTO, binding: ProviderCredentialBindingDTO
    ) -> ProviderCredentialValue:
        if (
            envelope.format_version != _FORMAT
            or envelope.algorithm != _ALGORITHM
            or _KEY_ID.fullmatch(envelope.key_id) is None
            or not 1
            <= len(envelope.message) - _ENVELOPE_OVERHEAD
            <= ProviderCredentialValue.MAX_BYTES
        ):
            raise DependencyUnavailableError(_CREDENTIAL_UNUSABLE)
        cipher, key_id = self._open(None)
        if not compare_digest(envelope.key_id, key_id):
            raise DependencyUnavailableError(_CREDENTIAL_UNUSABLE)
        try:
            plaintext = cipher.decrypt(envelope.message, self._associated_data(binding))
            return ProviderCredentialValue(plaintext.decode("ascii"))
        except (CryptoError, ValueError):
            raise DependencyUnavailableError(_CREDENTIAL_UNUSABLE) from None

    def _open(self, current_key_id: str | None) -> tuple[Aead, str]:
        path, expected = self._key_file, self._expected_key_id
        if (
            path is None
            or expected is None
            or _KEY_ID.fullmatch(expected) is None
            or compare_digest(expected, self._fingerprint_key_id)
            or (
                current_key_id is not None
                and (
                    _KEY_ID.fullmatch(current_key_id) is None
                    or not compare_digest(expected, current_key_id)
                )
            )
        ):
            raise DependencyUnavailableError(_KEY_UNAVAILABLE)
        try:
            # Nonblocking open keeps a misconfigured pipe from hanging before the mode check.
            descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOCTTY)
            try:
                mode = os.fstat(descriptor).st_mode
                if not stat.S_ISREG(mode) or mode & (stat.S_IRWXG | stat.S_IRWXO):
                    raise DependencyUnavailableError(_KEY_UNAVAILABLE)
                material = os.read(descriptor, Aead.KEY_SIZE + 1)
            finally:
                os.close(descriptor)
        except OSError:
            raise DependencyUnavailableError(_KEY_UNAVAILABLE) from None
        if len(material) != Aead.KEY_SIZE or not compare_digest(
            sha256(material).hexdigest(), expected
        ):
            raise DependencyUnavailableError(_KEY_UNAVAILABLE)
        return Aead(material), expected

    @staticmethod
    def _associated_data(binding: ProviderCredentialBindingDTO) -> bytes:
        RevisionValidation.require(binding.revision)
        if binding.revision == 0:
            raise ValueError("Encrypted credentials require a written revision.")
        return (
            _PURPOSE
            + binding.organization_id.value.bytes
            + binding.project_id.value.bytes
            + binding.connection_id.value.bytes
            + binding.credential_id.bytes
            + binding.revision.to_bytes(8, "big")
        )
