from collections.abc import AsyncIterable, AsyncIterator
from hashlib import sha256

from inframeld_backend.knowledge.application.errors.document_upload_errors import (
    InvalidPdfUploadError,
)
from inframeld_backend.shared.application.value_objects.artifact_content_digest import (
    ArtifactContentDigest,
)

_PDF_SIGNATURE = b"%PDF-"
_PDF_VERSIONS = (b"1.0", b"1.1", b"1.2", b"1.3", b"1.4", b"1.5", b"1.6", b"1.7", b"2.0")
_PDF_HEADER_BYTES = len(_PDF_SIGNATURE) + 4
_MAX_BYTES = 25 * 1024**2


class PdfUploadStream:
    """Check and fingerprint one PDF without keeping another copy of its bytes."""

    def __init__(self, filename: str, chunks: AsyncIterable[bytes]) -> None:
        try:
            filename_size = len(filename.encode("utf-8"))
        except UnicodeEncodeError:
            raise InvalidPdfUploadError("The PDF filename is invalid.") from None
        if (
            not filename.lower().endswith(".pdf")
            or filename_size > 255
            or any(ord(character) < 32 or character in "/\\\x7f" for character in filename)
        ):
            raise InvalidPdfUploadError("The PDF filename is invalid.")

        self._chunks = chunks
        self._started = False
        self._digest: ArtifactContentDigest | None = None
        self._length = 0

    async def read(self) -> AsyncIterator[bytes]:
        if self._started:
            raise RuntimeError("A PDF upload stream can only be consumed once.")
        self._started = True

        prefix = bytearray()
        hasher = sha256()
        total = 0
        async for chunk in self._chunks:
            if type(chunk) is not bytes or len(chunk) > _MAX_BYTES - total:
                raise InvalidPdfUploadError("The PDF exceeds its byte limit or has invalid bytes.")
            total += len(chunk)
            hasher.update(chunk)

            if len(prefix) < _PDF_HEADER_BYTES:
                prefix_size = min(len(chunk), _PDF_HEADER_BYTES - len(prefix))
                prefix.extend(chunk[:prefix_size])
                if not _PDF_SIGNATURE.startswith(prefix[: len(_PDF_SIGNATURE)]):
                    raise InvalidPdfUploadError("The file does not have a supported PDF signature.")
                if len(prefix) < _PDF_HEADER_BYTES:
                    continue
                header = bytes(prefix)
                if (
                    header[len(_PDF_SIGNATURE) : -1] not in _PDF_VERSIONS
                    or header[-1] not in b"\r\n"
                ):
                    raise InvalidPdfUploadError("The file does not have a supported PDF header.")
                yield header
                chunk = chunk[prefix_size:]

            if chunk:
                yield chunk

        if len(prefix) < _PDF_HEADER_BYTES:
            raise InvalidPdfUploadError("The PDF header is incomplete.")
        self._length = total
        self._digest = ArtifactContentDigest(hasher.digest())

    @property
    def digest(self) -> ArtifactContentDigest:
        if self._digest is None:
            raise RuntimeError("The complete PDF digest is unavailable.")
        return self._digest

    @property
    def length(self) -> int:
        if self._digest is None:
            raise RuntimeError("The complete PDF length is unavailable.")
        return self._length
