"""Observe the real cleanup client's DELETEs and interrupt one before its local ACK."""

import os
import signal
import sys
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

import boto3
from botocore.awsrequest import AWSPreparedRequest, AWSResponse

from inframeld_backend.bootstrap.application_worker import main


def _attempt(url: str) -> str:
    return UUID(urlsplit(url).path.rsplit("/", 1)[-1]).hex


def _observe_deletes(journal: Path, crash_after: str | None) -> None:
    def observe_send(request: AWSPreparedRequest, **_: object) -> None:
        attempt = _attempt(request.url)
        with journal.open("a", encoding="ascii") as output:
            assert output.tell() < 4 * 33, "The observed cleanup exceeded four DELETE attempts."
            output.write(attempt + "\n")

    def interrupt_after_success(http_response: AWSResponse, **_: object) -> None:
        if 200 <= http_response.status_code < 300 and _attempt(http_response.url) == crash_after:
            # The native client received success, but the worker cannot checkpoint it.
            os.kill(os.getpid(), signal.SIGKILL)

    boto3.setup_default_session()
    session = boto3.DEFAULT_SESSION
    assert session is not None
    session.events.register("before-send.s3.DeleteObject", observe_send)
    if crash_after is not None:
        session.events.register("after-call.s3.DeleteObject", interrupt_after_success)


if __name__ == "__main__":
    journal = Path(sys.argv[1])
    _observe_deletes(journal, sys.argv[2] if len(sys.argv) == 3 else None)
    raise SystemExit(main())
