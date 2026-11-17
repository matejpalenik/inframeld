"""Exercise the parser's private request and result verification."""

import errno
import json
import os
import select
import socket
import stat
import subprocess
import sys
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic
from types import SimpleNamespace
from typing import TypedDict, cast
from unittest import TestCase, skipUnless
from unittest.mock import MagicMock, Mock, patch
from uuid import UUID

from inframeld_parser import parse_launcher
from inframeld_parser.canonical_pdf import MAX_OUTPUT_BYTES, CanonicalPdf, TextBlock, canonicalize
from inframeld_parser.parse_request import ParseRequest, ParseRequestError, read_parse_request
from inframeld_parser.parse_result import (
    ParseResult,
    ParseResultError,
    encode_parse_result,
    validate_parse_result,
)
from inframeld_parser.pdf_conversion import MAX_INPUT_BYTES

_ATTEMPT = UUID("018b596c-4db5-7e1a-ae43-855809cd985b")
_SOURCE = b"%PDF-1.7\nlocal-private-content\n"
_SOURCE_SHA = sha256(_SOURCE).hexdigest()
_REQUEST = ParseRequest(_ATTEMPT, _SOURCE_SHA, 8, _SOURCE)
_CANONICAL = canonicalize(
    (TextBlock("Figure", (1,)), TextBlock("A🙂B", (1, 2)), TextBlock("Tail", (500,))),
    source_sha256=_SOURCE_SHA,
).canonical_bytes
_PARSER_SOURCE = Path(__file__).resolve().parents[1] / "src"
_CHILD_SCRIPT = _PARSER_SOURCE / "inframeld_parser/parse_child.py"
_CHILD_ARGUMENTS = (str(_ATTEMPT), _SOURCE_SHA, "8")


def _header(**changes: object) -> bytes:
    fields = {
        "attempt_id": str(_ATTEMPT),
        "source_sha256": _SOURCE_SHA,
        "source_size": len(_SOURCE),
        "max_content_tokens": 8,
        "merge_peers": False,
        **changes,
    }
    return json.dumps(fields).encode("utf-8")


def _frame(header: bytes, source: bytes = b"") -> bytes:
    return len(header).to_bytes(4, "big") + header + source


def _result_header(canonical: bytes, **changes: object) -> bytes:
    return json.dumps(
        {
            "attempt_id": str(_ATTEMPT),
            "source_sha256": _SOURCE_SHA,
            "canonical_sha256": sha256(canonical).hexdigest(),
            "canonical_size": len(canonical),
            "chunk_ranges": [[8, 9], [11, 15]],
            **changes,
        }
    ).encode("utf-8")


class ParseRequestContractTest(TestCase):
    def test_returns_one_verified_source_with_its_attempt_and_settings(self) -> None:
        sender, receiver = socket.socketpair()
        with sender, receiver:
            receiver.settimeout(0.75)
            sender.sendall(_frame(_header(), _SOURCE))
            result = read_parse_request(receiver, deadline=monotonic() + 1)
            self.assertEqual(receiver.gettimeout(), 0.75)
        self.assertEqual(result, ParseRequest(_ATTEMPT, _SOURCE_SHA, 8, _SOURCE))
        self.assertNotIn("local-private-content", repr(result))

    def test_rejects_malformed_or_unsupported_headers_before_waiting_on_body(self) -> None:
        valid = _header()
        for header in (
            _header(attempt_id=str(_ATTEMPT).upper()),
            _header(attempt_id=_ATTEMPT.hex),
            _header(source_sha256=_SOURCE_SHA.upper()),
            _header(source_sha256="x" * 64),
            _header(source_size=25 * 1024**2 + 1),
            _header(source_size=True),
            _header(source_size=0),
            _header(source_size=float(len(_SOURCE))),
            _header(max_content_tokens=0),
            _header(max_content_tokens=1025),
            _header(max_content_tokens=True),
            _header(merge_peers=True),
            _header(merge_peers=0),
            _header(source_path="protected-input"),
            valid.replace(b'"merge_peers": false', b'"merge_peers": false, "merge_peers": false'),
            valid.replace(b', "merge_peers": false', b""),
            b"\xff",
            b"[]",
        ):
            with self.subTest(header=header), self.assertRaisesRegex(ParseRequestError, "header"):
                self._read(_frame(header))

    def test_rejects_empty_or_oversize_header_lengths_without_reading_header(self) -> None:
        for size in (0, 1025):
            with self.subTest(size=size), self.assertRaisesRegex(ParseRequestError, "header"):
                self._read(size.to_bytes(4, "big"))

    def test_rejects_truncated_header_and_body(self) -> None:
        for frame in (b"\0\0", _frame(_header())[:-1], _frame(_header(), _SOURCE[:-1])):
            with self.subTest(frame=frame), self.assertRaisesRegex(ParseRequestError, "truncated"):
                self._read(frame)

    def test_rejects_digest_mismatch_and_invalid_pdf_prefix(self) -> None:
        changed = _SOURCE[:-1] + b"x"
        with self.assertRaisesRegex(ParseRequestError, "digest") as failure:
            self._read(_frame(_header(), changed))
        self.assertNotIn("local-private-content", str(failure.exception))

        invalid = b"%PDF-9.9\n"
        with self.assertRaisesRegex(ParseRequestError, "PDF header"):
            self._read(
                _frame(
                    _header(source_sha256=sha256(invalid).hexdigest(), source_size=len(invalid)),
                    invalid,
                )
            )

    def test_times_out_a_slow_body_without_waiting_for_the_peers_close(self) -> None:
        sender, receiver = socket.socketpair()
        with sender, receiver:
            receiver.settimeout(1.0)
            sender.sendall(_frame(_header(), _SOURCE[:1]))
            with self.assertRaisesRegex(ParseRequestError, "deadline"):
                read_parse_request(receiver, deadline=monotonic() + 0.02)
            self.assertEqual(receiver.gettimeout(), 1.0)

    def _read(self, data: bytes) -> ParseRequest:
        sender, receiver = socket.socketpair()
        with sender, receiver:
            sender.sendall(data)
            sender.shutdown(socket.SHUT_WR)
            return read_parse_request(receiver, deadline=monotonic() + 1)


class ParseResultContractTest(TestCase):
    def test_binds_the_exact_artifact_and_its_code_point_ranges(self) -> None:
        result = validate_parse_result(
            _frame(_result_header(_CANONICAL), _CANONICAL), request=_REQUEST
        )
        self.assertEqual(
            result,
            ParseResult(
                _ATTEMPT,
                _SOURCE_SHA,
                sha256(_CANONICAL).hexdigest(),
                ((8, 9), (11, 15)),
                _CANONICAL,
            ),
        )
        self.assertNotIn("Figure", repr(result))

    def test_rejects_bad_frame_lengths_and_nonexact_binding(self) -> None:
        header = _result_header(_CANONICAL)
        changed = (
            _result_header(_CANONICAL, attempt_id=str(UUID(int=1))),
            _result_header(_CANONICAL, source_sha256="a" * 64),
            _result_header(_CANONICAL, canonical_sha256="b" * 64),
            _result_header(_CANONICAL, canonical_size=True),
            _result_header(_CANONICAL, canonical_size=len(_CANONICAL) + 1),
            _result_header(_CANONICAL, storage_path="controlled-private-name"),
            header[:-1] + b', "chunk_ranges": [[8, 9]]}',
            b"\xff",
            b"[]",
            b'{"canonical_size":' + b"1" * 4400 + b"}",
        )
        frames = (
            b"\0\0\0",
            bytes(MAX_OUTPUT_BYTES + 1),
            (65537).to_bytes(4, "big"),
            _frame(b""),
            _frame(header)[:-1],
            _frame(header, _CANONICAL[:-1]),
            _frame(header, _CANONICAL + b"x"),
            *(_frame(candidate, _CANONICAL) for candidate in changed),
        )
        for index, frame in enumerate(frames):
            with self.subTest(frame=index):
                with self.assertRaises(ParseResultError) as failure:
                    validate_parse_result(frame, request=_REQUEST)
                self.assertNotIn("controlled-private-name", str(failure.exception))

    def test_rejects_noncanonical_prose_before_trusting_its_ranges(self) -> None:
        for canonical in (
            _CANONICAL + b"\n",
            _CANONICAL.replace(b'"kind":"text"', b'"kind":"table"', 1),
            _CANONICAL.replace(b'"pages":[1,2]', b'"pages":[2,1]'),
            _CANONICAL.replace(b'"pages":[1,2]', b'"pages":[1,1]'),
            _CANONICAL.replace(b'"pages":[1,2]', b'"pages":[true,2]'),
            _CANONICAL.replace(b'"pages":[500]', b'"pages":[501]'),
            _CANONICAL.replace(b'"span":[7,10]', b'"span":[5,10]'),
            _CANONICAL.replace(b'"span":[7,10]', b'"span":[8,10]'),
            _CANONICAL[:-1] + b',"text":"controlled-private-name"}',
        ):
            with self.assertRaisesRegex(ParseResultError, "canonical") as failure:
                validate_parse_result(
                    _frame(_result_header(canonical), canonical), request=_REQUEST
                )
            self.assertNotIn("controlled-private-name", str(failure.exception))

    def test_rejects_empty_excessive_or_invalid_chunk_ranges(self) -> None:
        for ranges in (
            [],
            [[8, 9]] * 2001,
            [[True, 9]],
            [[8, 9, 10]],
            [[8, 8]],
            [[9, 8]],
            [[11, 15], [8, 9]],
            [[7, 9], [8, 10]],
            [[9, 12]],
            [[10, 11]],
            [[100, 101]],
        ):
            with self.assertRaisesRegex(ParseResultError, "range"):
                validate_parse_result(
                    _frame(_result_header(_CANONICAL, chunk_ranges=ranges), _CANONICAL),
                    request=_REQUEST,
                )

    def test_encoder_rejects_a_body_that_fits_but_would_overflow_the_whole_frame(self) -> None:
        artifact = CanonicalPdf(_SOURCE_SHA, bytes(MAX_OUTPUT_BYTES - 32))
        with self.assertRaisesRegex(ParseResultError, "size"):
            encode_parse_result(_ATTEMPT, artifact, ((0, 1),))


class ParseChildContractTest(TestCase):
    def test_waits_for_the_exact_release_without_emitting_a_result(self) -> None:
        for release in (b"", b"x"):
            with self.subTest(release=release):
                outcome = subprocess.run(
                    [sys.executable, "-IBS", str(_CHILD_SCRIPT), *_CHILD_ARGUMENTS],
                    input=release,
                    capture_output=True,
                    timeout=5,
                    check=False,
                )
                self.assertEqual(outcome.stdout, b"ready\n")
                self.assertNotEqual(outcome.returncode, 0)
                self.assertEqual(
                    outcome.stderr, b"Parser child did not receive its release signal.\n"
                )

    def test_released_child_emits_one_verified_frame_without_converter_chatter(self) -> None:
        outcome = self._run_released_child(_SOURCE_SHA, require_scratch=True)
        self.assertEqual(outcome.returncode, 0, outcome.stderr)
        self.assertEqual(outcome.stderr, b"")
        self.assertTrue(outcome.stdout.startswith(b"ready\n"))
        result = validate_parse_result(outcome.stdout.removeprefix(b"ready\n"), request=_REQUEST)
        self.assertEqual(result.canonical_bytes, _CANONICAL)
        self.assertEqual(result.chunk_ranges, ((8, 9), (11, 15)))

    def test_refuses_a_conversion_from_different_source_bytes(self) -> None:
        outcome = self._run_released_child("a" * 64)
        self.assertNotEqual(outcome.returncode, 0)
        self.assertEqual(outcome.stdout, b"ready\n")
        self.assertEqual(outcome.stderr, b"Parser child conversion or result failed.\n")

    def _run_released_child(
        self, converted_digest: str, *, require_scratch: bool = False
    ) -> subprocess.CompletedProcess[bytes]:
        # A controlled converter exercises the real child and its result descriptor.
        code = """
import errno
import os
import runpy
import sys
import tempfile
from pathlib import Path

script, source, canonical, digest, require_scratch, *arguments = sys.argv[1:]
sys.path.insert(0, source)
from inframeld_parser import pdf_conversion
from inframeld_parser.canonical_pdf import CanonicalPdf
from inframeld_parser.prose_chunks import ProseChunk

converted = False
def convert(path, *, asset_root, manifest, max_content_tokens, merge_peers):
    global converted
    assert not converted
    converted = True
    try:
        os.fstat(0)
    except OSError as error:
        assert error.errno == errno.EBADF
    else:
        raise AssertionError('The release descriptor reached the converter.')
    assert os.environ['HF_HUB_OFFLINE'] == '1'
    if require_scratch == '1':
        assert tempfile.gettempdir() == '/scratch'
        if Path.home() != Path('/scratch'):
            os.write(2, b'Controlled converter did not resolve the sandbox home.\\n')
            raise AssertionError('Unexpected sandbox home.')
    assert path == Path('/input/source.pdf')
    assert asset_root == Path('/opt/inframeld-parser/assets')
    assert manifest == Path('/opt/inframeld-parser/docling-parser-v1.json')
    assert max_content_tokens == 8 and merge_peers is False
    os.write(1, b'private converter chatter')
    return CanonicalPdf(digest, bytes.fromhex(canonical)), (ProseChunk('🙂', 8, 9), ProseChunk('Tail', 11, 15))

pdf_conversion.convert_pdf_with_prose_chunks = convert
if require_scratch == '1':
    def no_temp_candidates():
        os.write(2, b'Controlled temp-directory discovery was required.\\n')
        return []

    os.environ['HOME'] = '/outside-parser-home'
    tempfile.tempdir = None
    tempfile._candidate_tempdir_list = no_temp_candidates
sys.argv = [script, *arguments]
runpy.run_path(script, run_name='__main__')
"""
        return subprocess.run(
            [
                sys.executable,
                "-IBS",
                "-c",
                code,
                str(_CHILD_SCRIPT),
                str(_PARSER_SOURCE),
                _CANONICAL.hex(),
                converted_digest,
                "1" if require_scratch else "0",
                *_CHILD_ARGUMENTS,
            ],
            input=b"r",
            capture_output=True,
            timeout=5,
            check=False,
        )


class ParseLauncherContractTest(TestCase):
    def setUp(self) -> None:
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.proc = Path(scratch.name) / "proc"
        self.enterContext(patch.object(parse_launcher, "_PROC", self.proc))
        self.machine = self.enterContext(
            patch.object(os, "uname", return_value=SimpleNamespace(machine="x86_64"))
        )
        self.enterContext(patch.object(os, "getuid", return_value=10001))
        self.enterContext(patch.object(os, "pidfd_open", self._open_pidfd, create=True))

        self.owned: list[int] = []
        self.addCleanup(self._close_pinned)
        self.pid_signals = {pid: self._pipe() for pid in (101, 102, 103)}
        self.ready_in, self.ready_out = self._pipe()
        self.release_in, release_out = os.pipe()
        self.addCleanup(os.close, self.release_in)
        os.set_blocking(self.release_in, False)
        stdin = os.fdopen(release_out, "wb")
        stdout = os.fdopen(self.ready_in, "rb", closefd=False)
        stderr_in, self.stderr_out = self._pipe()
        stderr = os.fdopen(stderr_in, "rb", closefd=False)
        self.addCleanup(stdin.close)
        self.addCleanup(stdout.close)
        self.addCleanup(stderr.close)
        self.monitor = cast(
            "subprocess.Popen[bytes]",
            SimpleNamespace(pid=101, stdin=stdin, stdout=stdout, stderr=stderr),
        )
        self.diagnostics = bytearray()
        self.report = Path(scratch.name) / "namespaces"
        self._write(self.report, b'{"child-pid":102,"mnt-namespace":41}\n')
        report = self.report.open("rb")
        self.addCleanup(report.close)
        self.report_fd = report.fileno()

        self._write(self.proc / "101/task/101/children", b"102 ")
        self._write(self.proc / "102/task/102/children", b"103 ")
        self._write(
            self.proc / "101/status",
            f"PPid:\t{os.getpid()}\nSeccomp:\t2\nSeccomp_filters:\t3\n".encode(),
        )
        self._write(self.proc / "102/status", b"PPid:\t101\nNSpid:\t102 1\n")
        self._write(
            self.proc / "103/status",
            b"PPid:\t102\nNSpid:\t103 2\n"
            + (
                "Uid:\t" + f"{os.getuid()} " * 4 + "\n"
                "NoNewPrivs:\t1\nSeccomp:\t2\nSeccomp_filters:\t4\n"
                "CapEff:\t0000000000000000\nCapPrm:\t0000000000000000\nCapBnd:\t0000000000000000\n"
            ).encode(),
        )
        for subject in ("self", "101", "102", "103"):
            self._write(self.proc / subject / "attr/current", b"inframeld-parser-probe (enforce)\n")
        for subject, number in (("self", 21), ("102", 41), ("103", 41)):
            directory = self.proc / subject / "ns"
            directory.mkdir(parents=True)
            for namespace in ("mnt", "pid", "ipc", "net", "user"):
                (directory / namespace).symlink_to(f"{namespace}:[{number}]")

        self._write(self.proc / "self/fdinfo" / str(self.pid_signals[101][0]), b"Pid:\t101\n")

    def test_releases_once_after_independent_observation_and_retains_the_pins(self) -> None:
        os.write(self.ready_out, b"ready\n")
        os.write(self.stderr_out, b"protected before ready")
        self._observe()
        self.assertEqual(self.diagnostics, b"protected before ready")
        self.assertEqual(select.select([self.release_in], [], [], 0)[0], [self.release_in])
        self.assertEqual(os.read(self.release_in, 2), b"r")
        self.assertEqual(len(self.owned), 2)
        for descriptor in self.owned:
            os.fstat(descriptor)
        self.assertEqual(select.select([self.release_in], [], [], 0)[0], [self.release_in])
        self.assertEqual(os.read(self.release_in, 1), b"")

    def test_retains_a_bound_init_when_its_parent_exits_before_release(self) -> None:
        monitor_fd, monitor_signal = self.pid_signals[101]
        real_select = select.select

        def exit_after_binding(
            readers: list[int], writers: list[int], errors: list[int], timeout: float
        ) -> tuple[list[int], list[int], list[int]]:
            if len(readers) == 2 and readers[0] == monitor_fd and timeout == 0:
                os.write(monitor_signal, b"exited")
            return real_select(readers, writers, errors, timeout)

        os.write(self.ready_out, b"ready\n")
        with (
            patch.object(select, "select", side_effect=exit_after_binding),
            self.assertRaisesRegex(parse_launcher.ParseObservationError, "live"),
        ):
            self._observe()
        self.assertEqual(len(self.owned), 1)
        os.fstat(self.owned[0])
        self._assert_no_release()

    def test_refuses_a_child_with_only_the_outer_seccomp_filters(self) -> None:
        status = self.proc / "103/status"
        status.write_bytes(
            status.read_bytes().replace(b"Seccomp_filters:\t4", b"Seccomp_filters:\t3")
        )
        os.write(self.ready_out, b"ready\n")
        with self.assertRaisesRegex(parse_launcher.ParseObservationError, "seccomp"):
            self._observe()
        self.assertEqual(len(self.owned), 2)
        self._assert_no_release()

    def test_refuses_a_bad_marker_before_pinning_or_release(self) -> None:
        os.write(self.ready_out, b"ready?")
        with self.assertRaisesRegex(parse_launcher.ParseObservationError, "readiness"):
            self._observe()
        self.assertEqual(self.owned, [])
        self._assert_no_release()

    def test_caps_diagnostics_before_releasing_the_held_child(self) -> None:
        os.write(self.stderr_out, b"excess")
        os.write(self.ready_out, b"ready\n")
        with (
            patch.object(parse_launcher, "_DIAGNOSTIC_LIMIT", 4),
            self.assertRaisesRegex(parse_launcher.ParseObservationError, "bounds"),
        ):
            self._observe()
        self.assertEqual(self.owned, [])
        self._assert_no_release()

    def test_refuses_an_incomplete_marker_at_the_original_deadline(self) -> None:
        os.write(self.ready_out, b"rea")
        with self.assertRaisesRegex(parse_launcher.ParseObservationError, "deadline"):
            self._observe(deadline=monotonic() + 0.02)
        self.assertEqual(self.owned, [])
        self._assert_no_release()

    def test_refuses_a_mismatched_namespace_hint_but_retains_both_pins(self) -> None:
        self.report.write_bytes(b'{"child-pid":102,"mnt-namespace":42}\n')
        os.write(self.ready_out, b"ready\n")
        with self.assertRaisesRegex(parse_launcher.ParseObservationError, "namespace"):
            self._observe()
        self.assertEqual(len(self.owned), 2)
        for descriptor in self.owned:
            os.fstat(descriptor)
        self._assert_no_release()

    def test_refuses_a_live_descriptor_for_the_wrong_monitor(self) -> None:
        self._write(self.proc / "self/fdinfo" / str(self.pid_signals[101][0]), b"Pid:\t109\n")
        os.write(self.ready_out, b"ready\n")
        with self.assertRaisesRegex(parse_launcher.ParseObservationError, "identity"):
            self._observe()
        self.assertEqual(self.owned, [])
        self._assert_no_release()

    def test_refuses_a_retired_converter_even_with_a_matching_report(self) -> None:
        os.write(self.pid_signals[103][1], b"exited")
        os.write(self.ready_out, b"ready\n")
        with self.assertRaisesRegex(parse_launcher.ParseObservationError, "live"):
            self._observe()
        self._assert_no_release()

    def test_releases_an_arm_child_with_the_exact_selinux_labels(self) -> None:
        self._use_arm_labels()
        os.write(self.ready_out, b"ready\n")
        self._observe(selinux_level="s0:c21,c25")
        self.assertEqual(os.read(self.release_in, 2), b"r")

    def test_refuses_mismatched_arm_selinux_labels_before_release(self) -> None:
        self._use_arm_labels()
        self._write(self.proc / "103/attr/current", b"system_u:system_r:container_t:s0:c21,c26\0")
        os.write(self.ready_out, b"ready\n")
        with self.assertRaisesRegex(parse_launcher.ParseObservationError, "context"):
            self._observe(selinux_level="s0:c21,c25")
        self.assertEqual(len(self.owned), 2)
        self._assert_no_release()

    def _use_arm_labels(self) -> None:
        self.machine.return_value = SimpleNamespace(machine="aarch64")
        for subject in ("self", "101", "102", "103"):
            self._write(
                self.proc / subject / "attr/current", b"system_u:system_r:container_t:s0:c21,c25\0"
            )

    def _observe(self, *, deadline: float | None = None, selinux_level: str | None = None) -> None:
        parse_launcher.observe_and_release(
            self.monitor,
            self.pid_signals[101][0],
            report_fd=self.report_fd,
            diagnostics=self.diagnostics,
            owned_pidfds=self.owned,
            selinux_level=selinux_level,
            deadline=deadline if deadline is not None else monotonic() + 1,
        )

    def _assert_no_release(self) -> None:
        with self.assertRaises(BlockingIOError):
            os.read(self.release_in, 1)

    def _pipe(self) -> tuple[int, int]:
        reader, writer = os.pipe()
        self.addCleanup(os.close, reader)
        self.addCleanup(os.close, writer)
        return reader, writer

    def _open_pidfd(self, pid: int) -> int:
        descriptor = os.dup(self.pid_signals[pid][0])
        self._write(self.proc / "self/fdinfo" / str(descriptor), f"Pid:\t{pid}\n".encode())
        return descriptor

    def _close_pinned(self) -> None:
        for descriptor in self.owned:
            os.close(descriptor)

    @staticmethod
    def _write(path: Path, text: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text)


class ParseAttemptOwnerTest(TestCase):
    def setUp(self) -> None:
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        self.scratch = root / "scratch"
        self.scratch.mkdir()
        helpers = root / "helpers"
        helpers.mkdir()
        (helpers / "child-seccomp.bpf").write_bytes(b"controlled-policy")
        self.enterContext(patch.object(parse_launcher, "_SCRATCH_ROOT", self.scratch))
        self.enterContext(patch.object(parse_launcher, "_HELPERS", helpers))
        device = MagicMock(spec=Path)
        device.configure_mock(**{"__str__.return_value": "/dev/urandom"})
        device.lstat.return_value = SimpleNamespace(st_mode=stat.S_IFCHR, st_rdev=os.makedev(1, 9))
        self.enterContext(patch.object(parse_launcher, "_URANDOM", device))
        self.enterContext(patch.object(os, "getpid", return_value=1))
        self.enterContext(patch.object(os, "uname", return_value=SimpleNamespace(machine="x86_64")))
        self.enterContext(
            patch.object(os, "waitpid", side_effect=ChildProcessError(errno.ECHILD, "no children"))
        )

    def test_rejects_unexpected_entropy_device_before_starting_or_staging(self) -> None:
        outside = self.scratch.parent
        regular = outside / "regular"
        regular.touch()
        symlink = outside / "symlink"
        symlink.symlink_to(regular)
        wrong_device = Mock(spec=Path)
        wrong_device.lstat.return_value = SimpleNamespace(
            st_mode=stat.S_IFCHR, st_rdev=os.makedev(1, 8)
        )

        for device in (regular, symlink, outside / "missing", wrong_device):
            with (
                self.subTest(device=device),
                patch.object(parse_launcher, "_URANDOM", device),
                patch.object(parse_launcher, "mkdtemp", wraps=parse_launcher.mkdtemp) as stage,
                patch.object(
                    subprocess, "Popen", side_effect=OSError("unexpected launch")
                ) as start,
                self.assertRaisesRegex(parse_launcher.ParseLaunchError, "start") as failure,
            ):
                parse_launcher.ParserLauncher(selinux_level=None).run(
                    _REQUEST, deadline=monotonic() + 1
                )
            start.assert_not_called()
            stage.assert_not_called()
            self.assertTrue(failure.exception.cleanup_confirmed)
            self.assertEqual(list(self.scratch.iterdir()), [])

    def test_reconciles_failed_startup_before_returning_its_fixed_error(self) -> None:
        launcher = parse_launcher.ParserLauncher(selinux_level=None)
        with (
            patch.object(
                subprocess, "Popen", side_effect=OSError("protected startup detail")
            ) as start,
            self.assertRaisesRegex(parse_launcher.ParseLaunchError, "start") as failure,
        ):
            launcher.run(_REQUEST, deadline=monotonic() + 1)
        self.assertTrue(failure.exception.cleanup_confirmed)
        self.assertNotIn("protected", str(failure.exception))
        self.assertEqual(list(self.scratch.iterdir()), [])
        argv = cast("list[str]", start.call_args.args[0])
        self.assertEqual(
            [argv[index : index + 3] for index, value in enumerate(argv) if value == "--dev-bind"],
            [
                ["--dev-bind", "/dev/null", "/dev/null"],
                ["--dev-bind", "/dev/urandom", "/dev/urandom"],
            ],
        )

    def test_incomplete_cleanup_keeps_original_error_and_quarantines_the_next_attempt(self) -> None:
        launcher = parse_launcher.ParserLauncher(selinux_level=None)
        with (
            patch.object(
                subprocess, "Popen", side_effect=OSError("protected startup detail")
            ) as start,
            patch("shutil.rmtree", side_effect=OSError("protected cleanup detail")),
        ):
            with self.assertRaisesRegex(parse_launcher.ParseLaunchError, "start") as failure:
                launcher.run(_REQUEST, deadline=monotonic() + 1)
            self.assertFalse(failure.exception.cleanup_confirmed)
            self.assertNotIn("protected", str(failure.exception))
            self.assertEqual(len(list(self.scratch.iterdir())), 1)
            with self.assertRaisesRegex(parse_launcher.ParseLaunchError, "quarantined"):
                launcher.run(_REQUEST, deadline=monotonic() + 1)
            start.assert_called_once()

    def test_unbound_monitor_is_never_waited_and_leaves_cleanup_unconfirmed(self) -> None:
        monitor = SimpleNamespace(pid=101, stdin=None, stdout=None, stderr=None, wait=Mock())
        launcher = parse_launcher.ParserLauncher(selinux_level=None)
        with (
            patch.object(subprocess, "Popen", return_value=monitor),
            patch.object(
                os, "pidfd_open", side_effect=OSError("protected pidfd detail"), create=True
            ),
            self.assertRaisesRegex(parse_launcher.ParseLaunchError, "identity") as failure,
        ):
            launcher.run(_REQUEST, deadline=monotonic() + 1)
        monitor.wait.assert_not_called()
        self.assertFalse(failure.exception.cleanup_confirmed)
        self.assertEqual(len(list(self.scratch.iterdir())), 1)

    def test_captures_fragmented_bytes_through_eof_with_same_diagnostics_buffer(self) -> None:
        frame = _frame(_result_header(_CANONICAL), _CANONICAL)
        diagnostics: list[bytearray] = []
        with patch.object(parse_launcher, "_READ_CHUNK", 3):
            result = self._run_captured(frame, diagnostics)
        self.assertEqual(result.canonical_bytes, _CANONICAL)
        self.assertEqual(diagnostics, [b"before-after"])
        self.assertEqual(list(self.scratch.iterdir()), [])

    def test_rejects_an_output_byte_after_the_exact_cap(self) -> None:
        with (
            patch.object(parse_launcher, "MAX_OUTPUT_BYTES", 4),
            self.assertRaisesRegex(parse_launcher.ParseLaunchError, "bounds") as failure,
        ):
            self._run_captured(b"extra", [])
        self.assertTrue(failure.exception.cleanup_confirmed)
        self.assertEqual(list(self.scratch.iterdir()), [])

    def test_does_not_decode_a_frame_from_a_nonzero_exit(self) -> None:
        with self.assertRaisesRegex(parse_launcher.ParseLaunchError, "finish successfully"):
            self._run_captured(b"invalid frame", [], exit_status=1)

    def test_waits_passively_for_a_held_child_after_monitor_and_pipe_exit(self) -> None:
        reader, writer = os.pipe()
        self.addCleanup(os.close, reader)
        self.addCleanup(os.close, writer)
        pins: list[int] = []
        real_select = select.select
        signalled = False

        def notify_retirement(
            readers: list[int], writers: list[int], errors: list[int], timeout: float
        ) -> tuple[list[int], list[int], list[int]]:
            nonlocal signalled
            if pins and readers == pins and timeout > 0 and not signalled:
                os.write(writer, b"exited")
                signalled = True
            return real_select(readers, writers, errors, timeout)

        with (
            patch.object(select, "select", side_effect=notify_retirement),
            patch.object(parse_launcher.signal, "pidfd_send_signal", create=True) as send_signal,
        ):
            result = self._run_captured(
                _frame(_result_header(_CANONICAL), _CANONICAL), [], pending=(reader, pins)
            )
        self.assertEqual(result.canonical_bytes, _CANONICAL)
        self.assertTrue(signalled)
        send_signal.assert_not_called()

    def test_reserves_staged_input_and_report_pages_inside_the_attempt_quota(self) -> None:
        for size, reservation in ((4096, 8192), (4097, 12288)):
            source = _SOURCE.ljust(size, b" ")
            request = ParseRequest(_ATTEMPT, sha256(source).hexdigest(), 8, source)
            with (
                self.subTest(size=size),
                patch.object(os, "sysconf", return_value=4096),
                patch.object(
                    subprocess, "Popen", side_effect=OSError("controlled startup")
                ) as start,
            ):
                with self.assertRaisesRegex(parse_launcher.ParseLaunchError, "start"):
                    parse_launcher.ParserLauncher(selinux_level=None).run(
                        request, deadline=monotonic() + 1
                    )
                argv = cast("list[str]", start.call_args.args[0])
                self.assertEqual(int(argv[argv.index("--size") + 1]), 1024**3 - reservation)

    def _run_captured(
        self,
        frame: bytes,
        diagnostics_seen: list[bytearray],
        *,
        exit_status: int = 0,
        pending: tuple[int, list[int]] | None = None,
    ) -> ParseResult:
        signal_fd = self._filled_pipe(b"exited")
        stdout = os.fdopen(self._filled_pipe(frame), "rb", closefd=False)
        stderr = os.fdopen(self._filled_pipe(b"after"), "rb", closefd=False)
        self.addCleanup(stdout.close)
        self.addCleanup(stderr.close)
        pinned = False

        def bind(descriptor: int, pid: int) -> None:
            nonlocal pinned
            self.assertEqual(pid, 101)
            os.fstat(descriptor)
            pinned = True

        def open_pidfd(pid: int) -> int:
            self.assertEqual(pid, 101)
            return os.dup(signal_fd)

        def wait(timeout: float) -> int:
            self.assertTrue(pinned)
            self.assertGreaterEqual(timeout, 0)
            return exit_status

        def release(
            monitor: object,
            descriptor: int,
            *,
            diagnostics: bytearray,
            owned_pidfds: list[int],
            **kwargs: object,
        ) -> int:
            self.assertTrue(pinned)
            diagnostics_seen.append(diagnostics)
            diagnostics.extend(b"before-")
            if pending is not None:
                descriptor = os.dup(pending[0])
                owned_pidfds.append(descriptor)
                pending[1].append(descriptor)
            return stderr.fileno()

        monitor = SimpleNamespace(pid=101, stdin=None, stdout=stdout, stderr=stderr, wait=wait)
        with (
            patch.object(subprocess, "Popen", return_value=monitor),
            patch.object(os, "pidfd_open", side_effect=open_pidfd, create=True),
            patch.object(parse_launcher, "_require_pidfd_identity", side_effect=bind),
            patch.object(parse_launcher, "observe_and_release", side_effect=release),
        ):
            return parse_launcher.ParserLauncher(selinux_level=None).run(
                _REQUEST, deadline=monotonic() + 1
            )

    def _filled_pipe(self, content: bytes) -> int:
        reader, writer = os.pipe()
        self.addCleanup(os.close, reader)
        try:
            os.write(writer, content)
        finally:
            os.close(writer)
        return reader


class _NativeTextBlock(TypedDict):
    pages: list[int]
    span: list[int]


class _NativeArtifactView(TypedDict):
    text: str
    blocks: list[_NativeTextBlock]


@skipUnless(os.getenv("INFRAMELD_PARSER_RUNTIME_TEST") == "1", "Requires the native parser image")
class ParseRuntimeContractTest(TestCase):
    def test_real_alice_returns_verified_stock_spans_and_confirms_teardown(self) -> None:
        self.assertEqual((os.getpid(), os.geteuid(), os.getegid()), (1, 10001, 10001))
        self.assertEqual(os.uname().machine, "aarch64")
        selinux_level = os.environ["INFRAMELD_PARSER_SELINUX_LEVEL"]
        with Path("/probe-allowed").open("rb") as matched:
            self.assertEqual(matched.read(9), b"matched\n")
        with self.assertRaises(PermissionError) as denial, Path("/probe-denied").open("rb"):
            pass
        self.assertEqual(denial.exception.errno, errno.EACCES)

        with Path("/qualification/alice.pdf").open("rb") as fixture:
            source = fixture.read(MAX_INPUT_BYTES + 1)
        digest = "b952b92e13900624ec2a780633e792bb0a3adeff561a45d0aa9de68a47db07c7"
        self.assertEqual(sha256(source).hexdigest(), digest)
        self._assert_empty_runtime()
        launcher = parse_launcher.ParserLauncher(selinux_level=selinux_level)
        result = launcher.run(ParseRequest(_ATTEMPT, digest, 8, source), deadline=monotonic() + 300)
        self._assert_empty_runtime()

        self.assertEqual((result.attempt_id, result.source_sha256), (_ATTEMPT, digest))
        self.assertEqual(result.canonical_sha256, sha256(result.canonical_bytes).hexdigest())
        document = cast("_NativeArtifactView", json.loads(result.canonical_bytes))
        text = document["text"]
        blocks = document["blocks"]
        self.assertTrue("Oh dear! Oh dear! I shall be late!" in text, "Alice text was missing.")
        self.assertTrue(all(block["pages"] == [1] for block in blocks))
        self.assertGreater(len(result.chunk_ranges), len(blocks), "Alice must have mapped splits.")
        previous_end = 0
        for start, end in result.chunk_ranges:
            self.assertTrue(previous_end <= start < end <= len(text))
            self.assertTrue(
                any(low <= start < end <= high for low, high in (block["span"] for block in blocks))
            )
            self.assertTrue(bool(text[start:end].strip()), "A returned span contained no text.")
            previous_end = end

    def _assert_empty_runtime(self) -> None:
        with self.assertRaises(ChildProcessError) as children:
            os.waitpid(-1, os.WNOHANG)
        self.assertEqual(children.exception.errno, errno.ECHILD)
        self.assertFalse(any(Path("/tmp").glob("inframeld-parser-*")), "Attempt scratch remained.")
