"""Serve one bounded parser exchange on an already connected Unix stream."""

import select
from math import ceil
from socket import AF_UNIX, SOCK_STREAM, socket
from time import monotonic

from inframeld_parser.parse_launcher import (
    MAX_ATTEMPT_SECONDS,
    ParseLaunchError,
    ParserLauncher,
)
from inframeld_parser.parse_request import ParseRequestError, read_parse_request
from inframeld_parser.parse_result import ParseResultError, encode_verified_result

# A zero header length cannot start a successful parser frame.
_REQUEST_REJECTED = b"\0\0\0\0\x01"
_ATTEMPT_FAILED = b"\0\0\0\0\x02"
_CLEANUP_UNCONFIRMED = b"\0\0\0\0\x03"


def serve_parse_connection(
    connection: socket, launcher: ParserLauncher, *, deadline: float
) -> None:
    """Serve one request on a stream that the caller closes after this returns.

    The peer keeps its write side open without sending more bytes until the reply.
    The original absolute monotonic deadline also bounds intake and output.
    """
    if (
        connection.family != AF_UNIX
        or connection.type != SOCK_STREAM
        or connection.fileno() < 0
        or not 0 < deadline - monotonic() <= MAX_ATTEMPT_SECONDS
    ):
        return

    poller = select.poll()
    peer_fd = connection.fileno()
    poller.register(peer_fd, select.POLLIN)
    try:
        request = read_parse_request(connection, deadline=deadline)
    except ParseRequestError:
        reply = _REQUEST_REJECTED
    else:
        if poller.poll(0):
            return
        try:
            result = launcher.run(request, deadline=deadline, peer_fd=peer_fd)
            reply = encode_verified_result(result)
        except ParseLaunchError as error:
            reply = _ATTEMPT_FAILED if error.cleanup_confirmed else _CLEANUP_UNCONFIRMED
        except ParseResultError:
            reply = _ATTEMPT_FAILED

    poller.modify(peer_fd, select.POLLIN | select.POLLOUT)
    previous_timeout = connection.gettimeout()
    try:
        connection.setblocking(False)
        pending = memoryview(reply)
        while pending:
            remaining = deadline - monotonic()
            if remaining <= 0:
                return
            ready = poller.poll(ceil(remaining * 1000))
            if not ready or ready[0][1] != select.POLLOUT or monotonic() >= deadline:
                return
            try:
                sent = connection.send(pending)
            except BlockingIOError:
                continue
            if sent == 0:
                return
            pending = pending[sent:]
    except OSError:
        return
    finally:
        connection.settimeout(previous_timeout)
