"""Own one confined parser attempt from startup through confirmed teardown."""

import errno
import json
import os
import re
import select
import shutil
import signal
import stat
import subprocess
from contextlib import suppress
from math import ceil, isfinite
from pathlib import Path
from tempfile import mkdtemp
from threading import Lock
from time import monotonic, sleep
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from subprocess import Popen

    from inframeld_parser.parse_request import ParseRequest

from inframeld_parser.canonical_pdf import MAX_OUTPUT_BYTES
from inframeld_parser.parse_result import ParseResult, ParseResultError, validate_parse_result

_PROC = Path("/proc")
_SCRATCH_ROOT = Path("/tmp")
_HELPERS = Path("/opt/inframeld-sandbox")
_RUNTIME = Path("/opt/inframeld-parser")
_URANDOM = Path("/dev/urandom")
_READ_CHUNK = 64 * 1024
_DIAGNOSTIC_LIMIT = 4096
_REPORT_LIMIT = 4096
_ATTEMPT_SCRATCH_BYTES = 1024**3
MAX_ATTEMPT_SECONDS = 300
_CLEANUP_SECONDS = 10
_READY = b"ready\n"
_APPARMOR_LABEL = b"inframeld-parser-probe (enforce)"
_NAMESPACES = ("mnt", "pid", "ipc", "net", "user")
_REPORT_FIELDS = {"child-pid", *(f"{name}-namespace" for name in _NAMESPACES[:-1])}
_BAD_IDENTITY = "The parser process identity could not be verified."
_BAD_REPORT = "The parser namespace report is invalid."
_NOT_LIVE = "A held parser process was no longer live."
_BAD_READY = "The parser readiness marker is invalid."
_PEER_ENDED = "The parser connection ended or sent extra input."
_BAD_SECCOMP = "The held parser seccomp filters did not match."


class ParseObservationError(RuntimeError):
    """A held child could not be verified before release."""


class ParseLaunchError(RuntimeError):
    """The fixed attempt failure and its independently observed cleanup state."""

    def __init__(self, message: str, *, cleanup_confirmed: bool) -> None:
        super().__init__(message)
        self.cleanup_confirmed = cleanup_confirmed


class ParserLauncher:
    """Run serial attempts as the sole parent and reaper in a private PID namespace."""

    def __init__(self, *, selinux_level: str | None) -> None:
        self._selinux_level = selinux_level
        self._turn = Lock()
        self._quarantined = False
        self._unreconciled_monitor: Popen[bytes] | None = None

    def run(
        self, request: "ParseRequest", *, deadline: float, peer_fd: int | None = None
    ) -> ParseResult:
        """Run one attempt while borrowing the optional caller-owned connection descriptor."""
        if not self._turn.acquire(blocking=False):
            raise ParseLaunchError("The parser already owns an attempt.", cleanup_confirmed=True)
        try:
            if self._quarantined:
                raise ParseLaunchError("The parser is quarantined.", cleanup_confirmed=False)
            if os.getpid() != 1 or not 0 < deadline - monotonic() <= MAX_ATTEMPT_SECONDS:
                raise ParseLaunchError(
                    "The parser attempt owner or deadline is invalid.", cleanup_confirmed=True
                )
            try:
                empty = _no_children()
            except OSError:
                empty = False
            if not empty:
                self._quarantined = True
                raise ParseLaunchError(
                    "The parser process inventory is uncertain.", cleanup_confirmed=False
                )
            return self._run_attempt(request, deadline, peer_fd)
        finally:
            self._turn.release()

    def _run_attempt(
        self, request: "ParseRequest", deadline: float, peer_fd: int | None
    ) -> ParseResult:
        scratch = None
        monitor = None
        monitor_fd = None
        held: list[int] = []
        diagnostics = bytearray()
        result = None
        failure = None
        stage = "The parser could not start the attempt."
        try:
            _require_silent_peer(peer_fd)
            _expected_label(self._selinux_level)
            entropy = _URANDOM.lstat()
            if not stat.S_ISCHR(entropy.st_mode) or (
                os.major(entropy.st_rdev),
                os.minor(entropy.st_rdev),
            ) != (1, 9):
                raise ValueError("The parser entropy device is invalid.")
            scratch = Path(mkdtemp(prefix="inframeld-parser-", dir=_SCRATCH_ROOT))
            source = scratch / "source.pdf"
            with os.fdopen(
                os.open(source, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb"
            ) as file:
                file.write(request.source)
            with (
                os.fdopen(
                    os.open(scratch / "namespaces", os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600),
                    "w+b",
                ) as report,
                (_HELPERS / "child-seccomp.bpf").open("rb") as policy,
            ):
                _remaining(deadline)
                _require_silent_peer(peer_fd)
                monitor = subprocess.Popen(
                    _arguments(source, report.fileno(), policy.fileno(), request),
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    bufsize=0,
                    close_fds=True,
                    pass_fds=(report.fileno(), policy.fileno()),
                    start_new_session=True,
                )
                stage = _BAD_IDENTITY
                descriptor = os.pidfd_open(monitor.pid)
                try:
                    _require_pidfd_identity(descriptor, monitor.pid)
                except BaseException:
                    os.close(descriptor)
                    raise
                monitor_fd = descriptor
                stderr_fd = observe_and_release(
                    monitor,
                    monitor_fd,
                    report_fd=report.fileno(),
                    diagnostics=diagnostics,
                    owned_pidfds=held,
                    selinux_level=self._selinux_level,
                    deadline=deadline,
                    peer_fd=peer_fd,
                )
                stage = "The parser output could not be captured."
                assert monitor.stdout is not None
                payload = _capture_result(
                    monitor.stdout.fileno(), stderr_fd, diagnostics, deadline, peer_fd=peer_fd
                )
                if peer_fd is not None and _wait_handles([monitor_fd], deadline, peer_fd=peer_fd):
                    raise ParseObservationError("The parser observation deadline elapsed.")
                remaining = _remaining(deadline)
                if monitor.wait(timeout=remaining if peer_fd is None else 0) != 0:
                    raise ParseObservationError("The parser child did not finish successfully.")
                if _wait_handles(held, deadline, peer_fd=peer_fd):
                    raise ParseObservationError("The parser observation deadline elapsed.")
                _remaining(deadline)
                _require_silent_peer(peer_fd)
                result = validate_parse_result(payload, request=request)
                _remaining(deadline)
                _require_silent_peer(peer_fd)
        except (ParseObservationError, ParseResultError) as error:
            failure = str(error)
        except subprocess.TimeoutExpired:
            failure = "The parser observation deadline elapsed."
        except (OSError, ValueError, subprocess.SubprocessError):
            failure = stage
        finally:
            cleanup_deadline = monotonic() + _CLEANUP_SECONDS
            clean, intervened = _retire_processes(monitor, monitor_fd, held, cleanup_deadline)
            clean = _close_attempt(monitor, monitor_fd, held) and clean
            clean = clean and monotonic() < cleanup_deadline
            if clean and scratch is not None:
                try:
                    shutil.rmtree(scratch)
                    clean = not os.path.lexists(scratch) and monotonic() < cleanup_deadline
                except OSError:
                    clean = False
            if not clean:
                # Retain it so Popen cannot independently reap during garbage collection.
                self._unreconciled_monitor = monitor
                self._quarantined = True

        if failure is not None:
            raise ParseLaunchError(failure, cleanup_confirmed=clean)
        if not clean:
            raise ParseLaunchError(
                "The parser attempt cleanup could not be confirmed.", cleanup_confirmed=False
            )
        if intervened:
            raise ParseLaunchError(
                "A parser process outlived its completed attempt.", cleanup_confirmed=True
            )
        assert result is not None
        return result


def _arguments(source: Path, report: int, policy: int, request: "ParseRequest") -> list[str]:
    argv = [
        str(_HELPERS / "bwrap"),
        "--unshare-user",
        "--unshare-pid",
        "--unshare-ipc",
        "--unshare-net",
        "--new-session",
        "--die-with-parent",
        "--clearenv",
        "--setenv",
        "LD_ORIGIN_PATH",
        "/usr/local/bin",
        "--json-status-fd",
        str(report),
        "--ro-bind",
        "/usr/local",
        "/usr/local",
    ]
    if os.uname().machine == "aarch64":
        library = "/usr/lib/aarch64-linux-gnu"
        argv.extend(
            (
                "--ro-bind",
                library,
                library,
                "--symlink",
                "aarch64-linux-gnu/ld-linux-aarch64.so.1",
                "/usr/lib/ld-linux-aarch64.so.1",
            )
        )
    else:
        for path in ("/usr/lib/x86_64-linux-gnu", "/lib64/ld-linux-x86-64.so.2"):
            argv.extend(("--ro-bind", path, path))
    argv.extend(
        (
            "--symlink",
            "usr/lib",
            "/lib",
            "--ro-bind",
            str(_RUNTIME),
            str(_RUNTIME),
            "--ro-bind",
            str(source),
            "/input/source.pdf",
            "--dev-bind",
            "/dev/null",
            "/dev/null",
            "--dev-bind",
            str(_URANDOM),
            str(_URANDOM),
            "--perms",
            "0700",
            "--size",
            str(_child_scratch_bytes(source.stat().st_size)),
            "--tmpfs",
            "/scratch",
            "--chdir",
            "/scratch",
            "--seccomp",
            str(policy),
            "--",
            "/usr/local/bin/python",
            "-IBS",
            str(_RUNTIME / "src/inframeld_parser/parse_child.py"),
            str(request.attempt_id),
            request.source_sha256,
            str(request.max_content_tokens),
        )
    )
    return argv


def _child_scratch_bytes(staged_input_bytes: int) -> int:
    page_size = os.sysconf("SC_PAGE_SIZE")
    if page_size <= 0:
        raise ValueError("The parser scratch allocation could not be sized.")
    reserved = sum(
        (size + page_size - 1) // page_size * page_size
        for size in (staged_input_bytes, _REPORT_LIMIT)
    )
    available = _ATTEMPT_SCRATCH_BYTES - reserved
    if available <= 0:
        raise ValueError("The parser scratch allocation could not be sized.")
    return available


def _capture_result(
    stdout_fd: int,
    stderr_fd: int | None,
    diagnostics: bytearray,
    deadline: float,
    *,
    peer_fd: int | None = None,
) -> bytes:
    result = bytearray()
    streams = {stdout_fd: (result, MAX_OUTPUT_BYTES)}
    if stderr_fd is not None:
        streams[stderr_fd] = diagnostics, _DIAGNOSTIC_LIMIT
    while streams:
        readable = _readable(list(streams), _remaining(deadline), peer_fd)
        if not readable:
            raise ParseObservationError("The parser observation deadline elapsed.")
        for descriptor in readable:
            buffer, limit = streams[descriptor]
            if not _read_bounded(descriptor, buffer, limit):
                del streams[descriptor]
    return bytes(result)


def _read_bounded(descriptor: int, buffer: bytearray, limit: int) -> bool:
    raw = os.read(descriptor, min(_READ_CHUNK, limit - len(buffer) + 1))
    if len(raw) > limit - len(buffer):
        raise ParseObservationError("The parser capture exceeds its bounds.")
    buffer.extend(raw)
    return bool(raw)


def _retire_processes(
    monitor: "Popen[bytes] | None", monitor_fd: int | None, held: list[int], deadline: float
) -> tuple[bool, bool]:
    if monitor is not None and monitor_fd is None:
        return False, False
    intervened = False
    try:
        if monitor is not None and monitor_fd is not None:
            descriptors = [monitor_fd, *held]
            retired = select.select(descriptors, [], [], 0)[0]
            live = [fd for fd in descriptors if fd not in retired]
            intervened = bool(live)
            if live:
                _signal_owned(live, signal.SIGTERM)
                live = _wait_handles(live, min(deadline, monotonic() + 1))
            if live:
                _signal_owned(live, signal.SIGKILL)
                if _wait_handles(live, deadline):
                    return False, True
            monitor.wait(timeout=max(0, deadline - monotonic()))

        while monotonic() < deadline:
            if _no_children():
                return True, intervened
            sleep(min(0.02, max(0, deadline - monotonic())))
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    return False, intervened


def _no_children() -> bool:
    try:
        os.waitpid(-1, os.WNOHANG)
    except ChildProcessError as error:
        if error.errno == errno.ECHILD:
            return True
        raise
    return False


def _signal_owned(descriptors: list[int], sig: signal.Signals) -> None:
    for descriptor in descriptors:
        with suppress(OSError):
            signal.pidfd_send_signal(descriptor, sig)


def _wait_handles(
    descriptors: list[int], deadline: float, *, peer_fd: int | None = None
) -> list[int]:
    while descriptors:
        retired = _readable(descriptors, max(0, deadline - monotonic()), peer_fd)
        if not retired:
            break
        descriptors = [fd for fd in descriptors if fd not in retired]
    return descriptors


def _readable(descriptors: list[int], timeout: float, peer_fd: int | None) -> list[int]:
    if peer_fd is None:
        return select.select(descriptors, [], [], timeout)[0]
    poller = select.poll()
    for descriptor in descriptors:
        poller.register(descriptor, select.POLLIN)
    poller.register(peer_fd, select.POLLIN)
    ready = poller.poll(ceil(timeout * 1000))
    if any(descriptor == peer_fd for descriptor, _ in ready):
        raise ParseObservationError(_PEER_ENDED)
    if any(events & select.POLLNVAL for _, events in ready):
        raise ParseObservationError(_BAD_IDENTITY)
    return [descriptor for descriptor, _ in ready]


def _require_silent_peer(peer_fd: int | None) -> None:
    if peer_fd is not None:
        _readable([], 0, peer_fd)


def _close_attempt(monitor: "Popen[bytes] | None", monitor_fd: int | None, held: list[int]) -> bool:
    closed = True
    if monitor is not None:
        for stream in (monitor.stdin, monitor.stdout, monitor.stderr):
            if stream is not None:
                try:
                    stream.close()
                except OSError:
                    closed = False
    for descriptor in held if monitor_fd is None else [monitor_fd, *held]:
        try:
            os.close(descriptor)
        except OSError:
            closed = False
    return closed


def observe_and_release(
    monitor: "Popen[bytes]",
    monitor_pidfd: int,
    *,
    report_fd: int,
    diagnostics: bytearray,
    owned_pidfds: list[int],
    selinux_level: str | None,
    deadline: float,
    peer_fd: int | None = None,
) -> int | None:
    """Verify the held process tree and release its child exactly once.

    The caller owns the monitor, its pidfd and report. The opened init and child
    pidfds join the caller's cleanup scope as soon as they are bound to that tree.
    This step closes the release stream and leaves stdout and reaping to its owner.
    """
    if monitor.stdin is None or monitor.stdout is None or monitor.stderr is None:
        raise ParseObservationError("The parser control streams are unavailable.")
    try:
        _remaining(deadline)
        label = _expected_label(selinux_level)
        if _status(monitor.pid).get(b"PPid") != [str(os.getpid()).encode("ascii")]:
            raise ParseObservationError(_BAD_IDENTITY)
        _require_pidfd_identity(monitor_pidfd, monitor.pid)
        ready_fd = monitor.stdout.fileno()
        release_fd = monitor.stdin.fileno()
        stderr_fd = _read_ready(
            ready_fd, monitor_pidfd, monitor.stderr.fileno(), diagnostics, deadline, peer_fd
        )

        init = _sole_child(monitor.pid)
        init_fd = _pin_child(init, monitor.pid, monitor_pidfd, owned_pidfds)
        child = _sole_child(init)
        child_fd = _pin_child(child, init, init_fd, owned_pidfds)

        report = _read_report(report_fd)
        if report["child-pid"] != init:
            raise ParseObservationError(_BAD_REPORT)
        _verify_status(monitor.pid, init, child)
        _verify_namespaces(init, child, report)
        for subject in ("self", str(monitor.pid), str(init), str(child)):
            observed = _read_proc(_PROC / subject / "attr/current", 127)
            if observed.removesuffix(b"\n").removesuffix(b"\0") != label:
                raise ParseObservationError("The parser process security context did not match.")

        if _sole_child(monitor.pid) != init or _sole_child(init) != child:
            raise ParseObservationError(_BAD_IDENTITY)
        readable, writable, _ = select.select(
            [ready_fd, monitor_pidfd, init_fd, child_fd], [release_fd], [], 0
        )
        if any(descriptor != ready_fd for descriptor in readable):
            raise ParseObservationError(_NOT_LIVE)
        if ready_fd in readable:
            raise ParseObservationError(_BAD_READY)
        _remaining(deadline)
        _require_silent_peer(peer_fd)
        if not writable or os.write(release_fd, b"r") != 1:
            raise ParseObservationError("The parser release could not be sent.")
        monitor.stdin.close()
        return stderr_fd
    except (OSError, ValueError):
        raise ParseObservationError("The held parser could not be observed or released.") from None


def _remaining(deadline: float) -> float:
    remaining = deadline - monotonic()
    if not isfinite(remaining) or remaining <= 0:
        raise ParseObservationError("The parser observation deadline elapsed.")
    return remaining


def _expected_label(selinux_level: str | None) -> bytes:
    machine = os.uname().machine
    if machine == "x86_64" and selinux_level is None:
        return _APPARMOR_LABEL
    if machine == "aarch64" and selinux_level is not None:
        match = re.fullmatch(r"s0:c(0|[1-9][0-9]{0,3}),c(0|[1-9][0-9]{0,3})", selinux_level)
        if match is not None and int(match[1]) + 1 < int(match[2]) <= 1023:
            return f"system_u:system_r:container_t:{selinux_level}".encode("ascii")
    raise ParseObservationError("The parser security context selection is invalid.")


def _read_ready(
    ready_fd: int,
    monitor_pidfd: int,
    stderr_fd: int | None,
    diagnostics: bytearray,
    deadline: float,
    peer_fd: int | None,
) -> int | None:
    marker = b""
    while len(marker) < len(_READY):
        descriptors = [ready_fd, monitor_pidfd]
        if stderr_fd is not None:
            descriptors.append(stderr_fd)
        readable = _readable(descriptors, _remaining(deadline), peer_fd)
        if (
            stderr_fd is not None
            and stderr_fd in readable
            and not _read_bounded(stderr_fd, diagnostics, _DIAGNOSTIC_LIMIT)
        ):
            stderr_fd = None
        if monitor_pidfd in readable:
            raise ParseObservationError(_NOT_LIVE)
        if not readable:
            raise ParseObservationError("The parser observation deadline elapsed.")
        if ready_fd not in readable:
            continue
        raw = os.read(ready_fd, len(_READY) - len(marker))
        marker += raw
        if not raw or not _READY.startswith(marker):
            raise ParseObservationError(_BAD_READY)
    return stderr_fd


def _sole_child(pid: int) -> int:
    value = _read_proc(_PROC / str(pid) / "task" / str(pid) / "children", 128).strip()
    if re.fullmatch(rb"[1-9][0-9]{0,9}", value) is None:
        raise ParseObservationError(_BAD_IDENTITY)
    return int(value)


def _pin_child(pid: int, parent: int, parent_pidfd: int, owned: list[int]) -> int:
    descriptor = os.pidfd_open(pid)
    try:
        _require_pidfd_identity(descriptor, pid)
        if _sole_child(parent) != pid or _status(pid).get(b"PPid") != [str(parent).encode("ascii")]:
            raise ParseObservationError(_BAD_IDENTITY)
    except BaseException:
        os.close(descriptor)
        raise
    owned.append(descriptor)
    if select.select([parent_pidfd, descriptor], [], [], 0)[0]:
        raise ParseObservationError(_NOT_LIVE)
    return descriptor


def _require_pidfd_identity(descriptor: int, pid: int) -> None:
    fields = _kernel_fields(_PROC / "self/fdinfo" / str(descriptor))
    if fields.get(b"Pid") != [str(pid).encode("ascii")]:
        raise ParseObservationError(_BAD_IDENTITY)


def _verify_status(monitor: int, init: int, child: int) -> None:
    init_status = _status(init)
    child_status = _status(child)
    uid = os.getuid()
    if (
        uid == 0
        or init_status.get(b"NSpid") != [str(init).encode("ascii"), b"1"]
        or child_status.get(b"NSpid") != [str(child).encode("ascii"), b"2"]
        or child_status.get(b"Uid") != [str(uid).encode("ascii")] * 4
        or child_status.get(b"NoNewPrivs") != [b"1"]
        or any(
            child_status.get(key) != [b"0000000000000000"]
            for key in (b"CapEff", b"CapPrm", b"CapBnd")
        )
    ):
        raise ParseObservationError("The held parser process status did not match.")
    if _seccomp_filters(child_status) != _seccomp_filters(_status(monitor)) + 1:
        raise ParseObservationError(_BAD_SECCOMP)


def _seccomp_filters(status: dict[bytes, list[bytes]]) -> int:
    count = status.get(b"Seccomp_filters", [])
    if (
        status.get(b"Seccomp") != [b"2"]
        or len(count) != 1
        or re.fullmatch(rb"[1-9][0-9]{0,9}", count[0]) is None
    ):
        raise ParseObservationError(_BAD_SECCOMP)
    return int(count[0])


def _verify_namespaces(init: int, child: int, report: dict[str, int]) -> None:
    for namespace in _NAMESPACES:
        outer = _namespace_inode("self", namespace)
        init_inode = _namespace_inode(str(init), namespace)
        child_inode = _namespace_inode(str(child), namespace)
        if init_inode != child_inode or child_inode == outer:
            raise ParseObservationError("The parser namespace identities did not match.")
        hint = report.get(f"{namespace}-namespace")
        if hint is not None and hint != child_inode:
            raise ParseObservationError("The parser namespace report did not match observation.")


def _namespace_inode(subject: str, namespace: str) -> int:
    target = os.readlink(_PROC / subject / "ns" / namespace)
    match = re.fullmatch(rf"{namespace}:\[([1-9][0-9]{{0,19}})\]", target)
    if match is None:
        raise ParseObservationError("The parser namespace link is invalid.")
    return int(match[1])


def _read_report(descriptor: int) -> dict[str, int]:
    raw = os.pread(descriptor, _REPORT_LIMIT + 1, 0)
    if not 1 <= len(raw) <= _REPORT_LIMIT or not raw.endswith(b"\n") or raw.count(b"\n") != 1:
        raise ParseObservationError(_BAD_REPORT)
    try:
        report: object = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_fields)
    except (ValueError, RecursionError):
        raise ParseObservationError(_BAD_REPORT) from None
    if not isinstance(report, dict):
        raise ParseObservationError(_BAD_REPORT)
    fields = cast("dict[str, object]", report)
    if (
        "child-pid" not in fields
        or not fields.keys() <= _REPORT_FIELDS
        or any(type(value) is not int or value <= 0 for value in fields.values())
    ):
        raise ParseObservationError(_BAD_REPORT)
    return cast("dict[str, int]", fields)


def _unique_fields(pairs: list[tuple[str, object]]) -> dict[str, object]:
    fields = dict(pairs)
    if len(fields) != len(pairs):
        raise ValueError("The namespace report has duplicate fields.")
    return fields


def _status(pid: int) -> dict[bytes, list[bytes]]:
    return _kernel_fields(_PROC / str(pid) / "status")


def _kernel_fields(path: Path) -> dict[bytes, list[bytes]]:
    fields: dict[bytes, list[bytes]] = {}
    for line in _read_proc(path, 8192).splitlines():
        name, separator, value = line.partition(b":")
        if not separator or not name or name in fields:
            raise ParseObservationError("The parser process observation is invalid.")
        fields[name] = value.split()
    return fields


def _read_proc(path: Path, limit: int) -> bytes:
    with path.open("rb") as source:
        value = source.read(limit + 1)
    if not 0 < len(value) <= limit:
        raise ParseObservationError("The parser process observation exceeds its bounds.")
    return value
