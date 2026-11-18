"""Own one private pathname Unix stream for the isolated parser."""

import os
import socket
import stat
import struct
import sys
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from time import monotonic

from inframeld_parser.parse_launcher import MAX_ATTEMPT_SECONDS, ParserLauncher
from inframeld_parser.parse_service import serve_parse_connection

_SOCKET_NAME = "parser.sock"
_CREDENTIALS = struct.Struct("=iII")


class ParseListenerError(RuntimeError):
    """The exact private listening socket could not be owned."""


@contextmanager
def open_parse_listener(directory: Path) -> Generator[socket.socket]:
    """Listen in the caller's trusted private directory and retire only this socket."""
    if not directory.is_absolute():
        raise ParseListenerError("The parser socket directory must be absolute.")
    try:
        descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            owner = os.geteuid()
            root = os.fstat(descriptor)
            if root.st_uid != owner or root.st_mode & 0o077:
                raise ParseListenerError("The parser socket directory is not private.")

            created = None
            try:
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
                    # The Linux supervisor has procfs. Bind in the pinned directory even if
                    # the advertised mount path has moved since open.
                    bind_directory = (
                        Path(f"/proc/self/fd/{descriptor}")
                        if sys.platform == "linux"
                        else directory
                    )
                    previous = os.umask(0o177)
                    try:
                        listener.bind(str(bind_directory / _SOCKET_NAME))
                    finally:
                        os.umask(previous)
                    node = os.stat(_SOCKET_NAME, dir_fd=descriptor, follow_symlinks=False)
                    if not stat.S_ISSOCK(node.st_mode) or node.st_uid != owner:
                        raise ParseListenerError("The parser socket entry is not owned.")
                    created = (node.st_dev, node.st_ino)
                    if stat.S_IMODE(node.st_mode) != 0o600:
                        raise ParseListenerError("The parser socket entry is not private.")
                    advertised = directory.lstat()
                    if (advertised.st_dev, advertised.st_ino) != (root.st_dev, root.st_ino):
                        raise ParseListenerError("The parser socket directory changed.")
                    listener.listen(1)
                    yield listener
            finally:
                if created is not None:
                    current = os.stat(_SOCKET_NAME, dir_fd=descriptor, follow_symlinks=False)
                    if (
                        (current.st_dev, current.st_ino) != created
                        or not stat.S_ISSOCK(current.st_mode)
                        or current.st_uid != owner
                    ):
                        raise ParseListenerError("The parser socket entry changed.")
                    os.unlink(_SOCKET_NAME, dir_fd=descriptor)
        finally:
            os.close(descriptor)
    except OSError:
        raise ParseListenerError("The private parser socket is unavailable.") from None


def serve_once(
    listener: socket.socket, launcher: ParserLauncher, *, accept_deadline: float
) -> bool:
    """Accept one stream and start a bounded exchange only for a verified local peer."""
    remaining = accept_deadline - monotonic()
    if not 0 < remaining <= MAX_ATTEMPT_SECONDS:
        return False
    try:
        listener.settimeout(remaining)
        connection, _ = listener.accept()
    except OSError:
        return False
    with connection:
        deadline = monotonic() + MAX_ATTEMPT_SECONDS
        if monotonic() >= accept_deadline or not _same_uid_peer(connection):
            return False
        serve_parse_connection(connection, launcher, deadline=deadline)
    return True


def _same_uid_peer(connection: socket.socket) -> bool:
    if sys.platform != "linux":
        return False
    try:
        raw = connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, _CREDENTIALS.size)
        _, uid, _ = _CREDENTIALS.unpack(raw)
    except (OSError, struct.error):
        return False
    # The peer's PID may be invisible across the private container PID namespaces.
    return uid == os.geteuid()
