"""Exercise the private parser socket's path and peer ownership."""

import os
import socket
import stat
import struct
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic
from typing import override
from unittest import TestCase, skipUnless
from unittest.mock import MagicMock, Mock, patch

from inframeld_parser import parse_listener
from inframeld_parser.parse_launcher import ParserLauncher


class ParseListenerTest(TestCase):
    @override
    def setUp(self) -> None:
        directory = TemporaryDirectory(prefix="ip-", dir="/tmp")
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)
        self.path = self.directory / "parser.sock"
        self.launcher = ParserLauncher(selinux_level=None)

    def test_owns_one_private_socket_and_closes_it_after_the_exchange(self) -> None:
        with (
            parse_listener.open_parse_listener(self.directory) as listener,
            socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client,
            patch.object(parse_listener, "_same_uid_peer", return_value=True),
            patch.object(parse_listener, "serve_parse_connection") as exchange,
        ):
            node = self.path.lstat()
            self.assertTrue(stat.S_ISSOCK(node.st_mode))
            self.assertEqual((stat.S_IMODE(node.st_mode), node.st_uid), (0o600, os.geteuid()))
            client.settimeout(1)
            client.connect(str(self.path))
            self.assertTrue(
                parse_listener.serve_once(listener, self.launcher, accept_deadline=monotonic() + 1)
            )
            exchange.assert_called_once()
            connection, launcher = exchange.call_args.args
            self.assertEqual(connection.fileno(), -1)
            self.assertIs(launcher, self.launcher)
            self.assertEqual(client.recv(1), b"")
        self.assertFalse(self.path.exists())

    def test_untrusted_peer_never_reaches_converter(self) -> None:
        with (
            parse_listener.open_parse_listener(self.directory) as listener,
            socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client,
            patch.object(parse_listener, "_same_uid_peer", return_value=False),
            patch.object(parse_listener, "serve_parse_connection") as exchange,
        ):
            client.settimeout(1)
            client.connect(str(self.path))
            self.assertFalse(
                parse_listener.serve_once(listener, self.launcher, accept_deadline=monotonic() + 1)
            )
            exchange.assert_not_called()
            self.assertEqual(client.recv(1), b"")
        self.assertFalse(self.path.exists())

    def test_stale_socket_is_left_in_place(self) -> None:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as original:
            original.bind(str(self.path))
        held = self.path.stat()
        with (
            self.assertRaises(parse_listener.ParseListenerError),
            parse_listener.open_parse_listener(self.directory),
        ):
            self.fail("The stale pathname was accepted.")
        retained = self.path.stat()
        self.assertEqual((retained.st_dev, retained.st_ino), (held.st_dev, held.st_ino))

    def test_shared_or_redirected_directory_is_rejected_before_binding(self) -> None:
        self.directory.chmod(0o750)
        target = self.directory / "private"
        target.mkdir(mode=0o700)
        alias = self.directory / "alias"
        alias.symlink_to(target, target_is_directory=True)
        for directory in (self.directory, alias):
            with (
                self.subTest(directory=directory),
                self.assertRaises(parse_listener.ParseListenerError),
                parse_listener.open_parse_listener(directory),
            ):
                self.fail("The untrusted directory was accepted.")
        self.assertFalse(self.path.exists())
        self.assertFalse((target / self.path.name).exists())

    def test_cleanup_leaves_a_replacement_path_untouched(self) -> None:
        with (
            self.assertRaises(parse_listener.ParseListenerError),
            parse_listener.open_parse_listener(self.directory),
        ):
            self.path.unlink()
            self.path.write_bytes(b"replacement")
        self.assertEqual(self.path.read_bytes(), b"replacement")

    def test_replaced_parent_does_not_receive_a_socket_or_keep_the_original(self) -> None:
        original_bind = socket.socket.bind
        emulate_proc = sys.platform != "linux"
        with TemporaryDirectory(prefix="ip-", dir="/tmp") as custody:
            moved = Path(custody) / "original"

            def swap_parent(listener: socket.socket, address: str) -> None:
                self.directory.rename(moved)
                self.directory.mkdir(mode=0o700)
                self.directory.chmod(0o700)
                if address.startswith("/proc/self/fd/"):
                    descriptor = int(Path(address).parent.name)
                    ours = os.fstat(descriptor)
                    observed = moved.stat()
                    self.assertEqual((ours.st_dev, ours.st_ino), (observed.st_dev, observed.st_ino))
                    if emulate_proc:
                        address = str(moved / self.path.name)
                original_bind(listener, address)

            with (
                patch.object(sys, "platform", "linux"),
                patch.object(socket.socket, "bind", swap_parent),
                self.assertRaises(parse_listener.ParseListenerError),
                parse_listener.open_parse_listener(self.directory),
            ):
                self.fail("The replacement directory was accepted.")
            self.assertFalse(self.path.exists())
            self.assertEqual(list(moved.iterdir()), [])

    @skipUnless(sys.platform == "linux", "Linux supplies SO_PEERCRED")
    def test_accepts_the_same_uid_from_actual_linux_credentials(self) -> None:
        with (
            parse_listener.open_parse_listener(self.directory) as listener,
            socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client,
            patch.object(parse_listener, "serve_parse_connection") as exchange,
        ):
            client.settimeout(1)
            client.connect(str(self.path))
            self.assertTrue(
                parse_listener.serve_once(listener, self.launcher, accept_deadline=monotonic() + 1)
            )
            exchange.assert_called_once()


class ParseListenerPeerTest(TestCase):
    @override
    def setUp(self) -> None:
        self.listener = Mock(spec=socket.socket)
        self.peer = MagicMock(spec=socket.socket)
        self.listener.accept.return_value = (self.peer, "")
        self.launcher = ParserLauncher(selinux_level=None)

    def _serve(self) -> bool:
        return parse_listener.serve_once(
            self.listener, self.launcher, accept_deadline=monotonic() + 1
        )

    def test_requires_exact_linux_credentials_with_the_expected_local_uid(self) -> None:
        with (
            patch.object(sys, "platform", "linux"),
            patch.object(socket, "SO_PEERCRED", 17, create=True),
            patch.object(parse_listener, "serve_parse_connection") as exchange,
        ):
            self.peer.getsockopt.return_value = struct.pack("=iII", 0, os.geteuid(), 0)
            self.assertTrue(self._serve())
            self.peer.getsockopt.assert_called_once_with(socket.SOL_SOCKET, 17, 12)
            for value in (b"", struct.pack("=iII", 1, os.geteuid() + 1, 0)):
                with self.subTest(value=value):
                    self.peer.getsockopt.return_value = value
                    self.assertFalse(self._serve())
            self.peer.getsockopt.side_effect = OSError()
            self.assertFalse(self._serve())
            exchange.assert_called_once()

    def test_unsupported_platform_does_not_accept_unverified_peers(self) -> None:
        with (
            patch.object(sys, "platform", "darwin"),
            patch.object(parse_listener, "serve_parse_connection") as exchange,
        ):
            self.assertFalse(self._serve())
        self.peer.getsockopt.assert_not_called()
        exchange.assert_not_called()
