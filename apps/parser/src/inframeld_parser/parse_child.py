"""Run one released PDF conversion as the fixed sandbox child."""

import fcntl
import os
import re
import sys
from collections.abc import Generator
from contextlib import contextmanager, suppress
from io import BufferedWriter
from pathlib import Path
from uuid import UUID

_RUNTIME = Path("/opt/inframeld-parser")
_SOURCE = Path("/input/source.pdf")
_READY = b"ready\n"


def main(arguments: list[str]) -> int:
    try:
        attempt_id, source_sha256, max_content_tokens = _attempt(arguments)
    except ValueError:
        return _fail(b"Parser child arguments were invalid.\n")

    try:
        released = os.write(1, _READY) == len(_READY) and os.read(0, 1) == b"r"
    except OSError:
        released = False
    if not released:
        return _fail(b"Parser child did not receive its release signal.\n")

    try:
        with _result_output() as output:
            frame = _convert(attempt_id, source_sha256, max_content_tokens)
            if output.write(frame) != len(frame):
                raise OSError("Parser child result write was incomplete.")
    except Exception:
        return _fail(b"Parser child conversion or result failed.\n")
    return 0


def _attempt(arguments: list[str]) -> tuple[UUID, str, int]:
    if len(arguments) != 3:
        raise ValueError("Parser child expects one attempt binding.")
    attempt, digest, limit = arguments
    attempt_id = UUID(attempt)
    if (
        str(attempt_id) != attempt
        or re.fullmatch(r"[0-9a-f]{64}", digest) is None
        or re.fullmatch(r"[1-9][0-9]{0,3}", limit) is None
        or int(limit) > 1024
    ):
        raise ValueError("Parser child expects one attempt binding.")
    return attempt_id, digest, int(limit)


@contextmanager
def _result_output() -> Generator[BufferedWriter]:
    """Keep the result pipe separate from converter writes to standard output."""
    descriptor = fcntl.fcntl(1, fcntl.F_DUPFD_CLOEXEC, 3)
    try:
        # Only stdlib code has run. Refill FD 1 before importing the converter.
        os.close(1)
        sink = os.open(os.devnull, os.O_WRONLY)
        if sink != 1:
            os.close(sink)
            raise OSError("Parser child could not isolate standard output.")
        os.close(0)
        with os.fdopen(descriptor, "wb", closefd=False) as output:
            yield output
    finally:
        os.close(descriptor)


def _convert(attempt_id: UUID, source_sha256: str, max_content_tokens: int) -> bytes:
    sys.path[:0] = [str(_RUNTIME / "src"), str(_RUNTIME / "site")]
    os.environ.update(
        HF_HOME="/scratch/huggingface",
        HF_HUB_OFFLINE="1",
        HF_HUB_DISABLE_IMPLICIT_TOKEN="1",
        HF_HUB_DISABLE_TELEMETRY="1",
        TRANSFORMERS_OFFLINE="1",
    )

    from inframeld_parser.parse_result import encode_parse_result
    from inframeld_parser.pdf_conversion import convert_pdf_with_prose_chunks

    artifact, chunks = convert_pdf_with_prose_chunks(
        _SOURCE,
        asset_root=_RUNTIME / "assets",
        manifest=_RUNTIME / "docling-parser-v1.json",
        max_content_tokens=max_content_tokens,
        merge_peers=False,
    )
    if artifact.source_sha256 != source_sha256:
        raise ValueError("Parser child converted a different source.")
    return encode_parse_result(
        attempt_id, artifact, tuple((chunk.start, chunk.end) for chunk in chunks)
    )


def _fail(message: bytes) -> int:
    with suppress(OSError):
        os.write(2, message)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
