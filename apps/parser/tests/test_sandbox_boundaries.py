"""Exercise the fixed parser sandbox against the real Ubuntu policy."""

import ctypes
import errno
import json
import os
import resource
import select
import socket
import subprocess
import sys
import time
import unittest
from contextlib import suppress
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TypedDict, cast

_DELTA = Path(__file__).resolve().parents[1] / "security/oci-seccomp.json"
_BASELINE_URL = "https://raw.githubusercontent.com/moby/moby/v28.0.4/profiles/seccomp/default.json"
_SETUP_RULES = [
    {
        "names": ["clone"],
        "action": "SCMP_ACT_ALLOW",
        "args": [{"index": 0, "value": 2013397009, "op": "SCMP_CMP_EQ"}],
    },
    {"names": ["mount", "umount2", "pivot_root"], "action": "SCMP_ACT_ALLOW"},
    # Linux ENOSYS selects the signed Bubblewrap release's legacy bind-remount path.
    {"names": ["mount_setattr"], "action": "SCMP_ACT_ERRNO", "errnoRet": 38},
]
_SETUP_NAMESPACES = ("mnt", "pid", "ipc", "net")
_DISABLED = errno.EOPNOTSUPP
_USER_NAMESPACE = 0x10000000
_WORK_SECONDS = 300
_CLEANUP_SECONDS = 10
_CAPTURE_BYTES = 4096
_FILTER = Path("/probe/security/child-seccomp.bpf")
_CHILD_PYTHON = "/usr/local/bin/python"
_PROFILE = "inframeld-parser-probe (enforce)"


class _BaselinePin(TypedDict):
    url: str
    sha256: str


class _OciDelta(TypedDict):
    baseline: _BaselinePin
    addSyscalls: list[dict[str, object]]


def compose_oci_profile(source: bytes, delta: _OciDelta) -> dict[str, object]:
    """Append only the fixed setup operations to the pinned Moby profile."""
    if (
        set(delta) != {"baseline", "addSyscalls"}
        or set(delta["baseline"]) != {"url", "sha256"}
        or delta["baseline"]["url"] != _BASELINE_URL
        or delta["addSyscalls"] != _SETUP_RULES
    ):
        raise ValueError("Unexpected sandbox seccomp delta.")
    if sha256(source).hexdigest() != delta["baseline"]["sha256"]:
        raise ValueError("The Moby seccomp profile digest does not match.")
    baseline = cast("dict[str, object]", json.loads(source))
    if (
        type(baseline) is not dict
        or set(baseline) != {"defaultAction", "defaultErrnoRet", "archMap", "syscalls"}
        or baseline["defaultAction"] != "SCMP_ACT_ERRNO"
        or baseline["defaultErrnoRet"] != 1
        or not isinstance(arch_map := baseline["archMap"], list)
        or not isinstance(syscalls := baseline["syscalls"], list)
    ):
        raise ValueError("Unsupported Moby seccomp baseline.")
    architectures = cast("list[object]", arch_map)
    if not architectures or not isinstance(primary := architectures[0], dict):
        raise ValueError("Unsupported Moby seccomp baseline architecture.")
    if cast("dict[str, object]", primary).get("architecture") != "SCMP_ARCH_X86_64":
        raise ValueError("Unsupported Moby seccomp baseline architecture.")
    rules = cast("list[object]", syscalls)
    if not all(isinstance(rule, dict) for rule in rules) or any(
        rule in rules for rule in _SETUP_RULES
    ):
        raise ValueError("A sandbox extension already exists in the Moby baseline.")
    return {**baseline, "syscalls": [*rules, *_SETUP_RULES]}


class OciPolicyPreparationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.baseline: dict[str, object] = {
            "defaultAction": "SCMP_ACT_ERRNO",
            "defaultErrnoRet": 1,
            "archMap": [{"architecture": "SCMP_ARCH_X86_64", "subArchitectures": []}],
            "syscalls": [{"names": ["read"], "action": "SCMP_ACT_ALLOW"}],
        }
        self.source = json.dumps(self.baseline).encode()
        self.delta = cast("_OciDelta", json.loads(_DELTA.read_bytes()))
        self.delta["baseline"]["sha256"] = sha256(self.source).hexdigest()

    def test_keeps_all_original_restrictions_and_adds_only_fixed_namespace_setup(self) -> None:
        prepared = compose_oci_profile(self.source, self.delta)
        self.assertEqual(
            prepared,
            {
                **self.baseline,
                "syscalls": [
                    {"names": ["read"], "action": "SCMP_ACT_ALLOW"},
                    {
                        "names": ["clone"],
                        "action": "SCMP_ACT_ALLOW",
                        "args": [{"index": 0, "value": 2013397009, "op": "SCMP_CMP_EQ"}],
                    },
                    {"names": ["mount", "umount2", "pivot_root"], "action": "SCMP_ACT_ALLOW"},
                    {
                        "names": ["mount_setattr"],
                        "action": "SCMP_ACT_ERRNO",
                        "errnoRet": 38,
                    },
                ],
            },
        )

    def test_refuses_even_a_same_length_changed_upstream_profile(self) -> None:
        changed = self.source.replace(b'"read"', b'"mmap"')
        self.assertEqual(len(self.source), len(changed))
        with self.assertRaisesRegex(ValueError, "digest"):
            compose_oci_profile(changed, self.delta)

    def test_refuses_unconditional_clone_and_duplicate_namespace_scope(self) -> None:
        rejected: tuple[list[dict[str, object]], ...] = (
            [{"names": ["clone"], "action": "SCMP_ACT_ALLOW"}],
            [*self.delta["addSyscalls"], *self.delta["addSyscalls"]],
            [{"names": ["unshare"], "action": "SCMP_ACT_ALLOW"}],
            [
                *self.delta["addSyscalls"],
                {"names": ["mount_setattr"], "action": "SCMP_ACT_ALLOW"},
            ],
        )
        for rules in rejected:
            with self.subTest(rules=rules), self.assertRaisesRegex(ValueError, "delta"):
                compose_oci_profile(self.source, {**self.delta, "addSyscalls": rules})

    def test_refuses_a_default_allow_profile_even_with_its_matching_hash(self) -> None:
        source = json.dumps({**self.baseline, "defaultAction": "SCMP_ACT_ALLOW"}).encode()
        self.delta["baseline"]["sha256"] = sha256(source).hexdigest()
        with self.assertRaisesRegex(ValueError, "baseline"):
            compose_oci_profile(source, self.delta)


class NamespaceReportTest(unittest.TestCase):
    def test_requires_the_exact_positive_setup_ids(self) -> None:
        valid = {
            "child-pid": 41,
            "mnt-namespace": 101,
            "pid-namespace": 102,
            "ipc-namespace": 103,
            "net-namespace": 104,
        }
        with TemporaryDirectory() as directory:
            report = Path(directory) / "namespaces.json"
            report.write_text(json.dumps(valid))
            self.assertEqual(_read_namespace_report(report), valid)
            for invalid in (
                {key: value for key, value in valid.items() if key != "net-namespace"},
                {**valid, "user-namespace": 105},
                {**valid, "pid-namespace": 0},
                {**valid, "child-pid": True},
                {**valid, "ipc-namespace": "103"},
            ):
                with self.subTest(invalid=invalid), self.assertRaisesRegex(ValueError, "namespace"):
                    report.write_text(json.dumps(invalid))
                    _read_namespace_report(report)
            with self.assertRaisesRegex(ValueError, "capture limit"):
                report.write_text(" " * (_CAPTURE_BYTES + 1))
                _read_namespace_report(report)


class FixtureFailureTest(unittest.TestCase):
    def test_reports_fixed_mapping_operation_and_permission_classes(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for message, category in (
                (b"setting up uid map: Permission denied", "uid-map-eacces"),
                (b"setting up gid map: Operation not permitted", "gid-map-eperm"),
                (b"error writing to setgroups: Read-only file system", "setgroups-erofs"),
                (b"setting up uid map: unexpected: protected detail", "uid-map-other"),
            ):
                with self.subTest(category=category):
                    (root / "stderr").write_bytes(b"bwrap: " + message + b"\n")
                    self.assertEqual(
                        _fixture_failure(root, "before-child-ready"),
                        f"Parser sandbox stage=before-child-ready category={category}.",
                    )


@unittest.skipUnless(
    os.getenv("INFRAMELD_PARSER_SANDBOX_TEST") == "1", "Requires the Ubuntu parser probe"
)
class ParserSandboxTest(unittest.TestCase):
    def setUp(self) -> None:
        self.assertEqual(os.uname().machine, "x86_64")
        self.assertEqual(os.getpid(), 1, "The disposable test container owns orphan reaping.")
        self.assertEqual(_children(1), ())
        self.assertNotEqual(os.geteuid(), 0)
        self.assertEqual(_apparmor(), _PROFILE)
        status = _status(Path("/proc/self"))
        self.assertEqual(status["NoNewPrivs"], "1")
        self.assertTrue(all(int(status[key], 16) == 0 for key in ("CapEff", "CapPrm", "CapBnd")))
        with self.assertRaises(PermissionError):
            Path("/probe-denied").read_bytes()

    def test_fixed_child_observes_new_namespaces_and_denied_effects(self) -> None:
        with TemporaryDirectory(dir="/tmp") as directory:
            root = Path(directory)
            deadline = time.monotonic() + _WORK_SECONDS
            process = _start_owner(root, "once")
            cleanup_deadline: float | None = None
            try:
                _, _, child = self._observe_held_child(root, process, deadline)
                descriptor = os.pidfd_open(child)
                try:
                    assert process.stdin is not None
                    self.assertEqual(process.stdin.write(b"r"), 1)
                    try:
                        status = process.wait(timeout=max(0.0, deadline - time.monotonic()))
                    except subprocess.TimeoutExpired:
                        raise AssertionError(_fixture_failure(root, "child-timeout")) from None
                    finished_at = time.monotonic()
                    cleanup_deadline = finished_at + _CLEANUP_SECONDS
                    if status != 0:
                        self.fail(_fixture_failure(root, "child-exit"))
                    if finished_at > deadline:
                        self.fail(_fixture_failure(root, "child-timeout"))
                    self.assertEqual(select.select([descriptor], [], [], 0)[0], [descriptor])
                finally:
                    os.close(descriptor)
            finally:
                _stop_owner(process, cleanup_deadline)

    def test_loss_of_owner_retires_an_observed_separate_session_child(self) -> None:
        with TemporaryDirectory(dir="/tmp") as directory:
            root = Path(directory)
            deadline = time.monotonic() + _WORK_SECONDS
            process = _start_owner(root, "hold")
            descriptors: list[int] = []
            cleanup_deadline: float | None = None
            try:
                monitor, init, child = self._observe_held_child(root, process, deadline)
                (descendant,) = _children(child)
                self.assertEqual(
                    _status(Path(f"/proc/{descendant}"))["NSpid"].split(), [str(descendant), "3"]
                )
                self.assertNotEqual(_session(descendant), _session(child))
                for pid in (monitor, init, child, descendant):
                    descriptors.append(os.pidfd_open(pid))
                if time.monotonic() > deadline:
                    self.fail(_fixture_failure(root, "child-observation-timeout"))

                cleanup_deadline = time.monotonic() + _CLEANUP_SECONDS
                process.kill()
                _wait_for_owner_exit(process, cleanup_deadline)
                for descriptor in descriptors:
                    readable, _, _ = select.select(
                        [descriptor], [], [], max(0.0, cleanup_deadline - time.monotonic())
                    )
                    self.assertEqual(readable, [descriptor], "A namespace process survived.")
            finally:
                for descriptor in descriptors:
                    os.close(descriptor)
                _stop_owner(process, cleanup_deadline)

    def _observe_held_child(
        self, root: Path, process: subprocess.Popen[bytes], deadline: float
    ) -> tuple[int, int, int]:
        ready = root / "child-ready"
        while not ready.exists() or ready.stat().st_size == 0:
            if process.poll() is not None:
                self.fail(_fixture_failure(root, "before-child-ready"))
            if time.monotonic() >= deadline:
                self.fail(_fixture_failure(root, "child-ready-timeout"))
            time.sleep(0.02)
        with ready.open("rb") as record:
            self.assertEqual(record.read(7), b"ready\n")

        # Start from the real owner and verify which process the setup report describes.
        report = _read_namespace_report(root / "namespaces.json")
        (monitor,) = _children(process.pid)
        (init,) = _children(monitor)
        (child,) = _children(init)
        self.assertEqual(report["child-pid"], init)
        self.assertEqual(_status(Path(f"/proc/{init}"))["NSpid"].split(), [str(init), "1"])
        actual = Path(f"/proc/{child}")
        status = _status(actual)
        self.assertEqual(status["NSpid"].split(), [str(child), "2"])
        self.assertEqual(status["Uid"].split(), [str(os.getuid())] * 4)
        self.assertEqual(status["NoNewPrivs"], "1")
        self.assertTrue(all(int(status[key], 16) == 0 for key in ("CapEff", "CapPrm", "CapBnd")))
        self.assertEqual(status["Seccomp"], "2")
        self.assertEqual(_apparmor(actual), _PROFILE)
        outer = Path("/proc/self")
        for namespace in _SETUP_NAMESPACES:
            outer_id = _namespace(outer, namespace)
            self.assertGreater(outer_id, 0)
            self.assertNotEqual(report[f"{namespace}-namespace"], outer_id)
        outer_user = _namespace(outer, "user")
        actual_user = _namespace(actual, "user")
        self.assertGreater(outer_user, 0)
        self.assertGreater(actual_user, 0)
        self.assertNotEqual(actual_user, outer_user)
        self.assertEqual(_namespace(actual, "pid"), report["pid-namespace"])
        if time.monotonic() > deadline:
            self.fail(_fixture_failure(root, "child-observation-timeout"))
        return monitor, init, child


def _start_owner(root: Path, mode: str) -> subprocess.Popen[bytes]:
    try:
        descriptor = os.open(root / "stderr", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as diagnostics:
            return subprocess.Popen(
                [sys.executable, "-IB", __file__, "--owner", str(root), mode],
                stdin=subprocess.PIPE if mode == "once" else subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=diagnostics,
                env={**os.environ, "LC_ALL": "C"},
                bufsize=0,
                start_new_session=True,
            )
    except OSError:
        raise RuntimeError(
            "Parser sandbox stage=owner-launch category=process-or-capture-unavailable."
        ) from None


def _wait_for_owner_exit(process: subprocess.Popen[bytes], deadline: float) -> None:
    try:
        process.wait(timeout=max(0.0, deadline - time.monotonic()))
        return
    except subprocess.TimeoutExpired:
        pass
    raise TimeoutError("Parser sandbox stage=cleanup category=owner-exit-unconfirmed.")


def _stop_owner(process: subprocess.Popen[bytes], deadline: float | None = None) -> None:
    if process.stdin is not None:
        process.stdin.close()
    deadline = deadline if deadline is not None else time.monotonic() + _CLEANUP_SECONDS
    if process.poll() is None:
        process.kill()
        _wait_for_owner_exit(process, deadline)
    # The disposable suite is PID 1 and owns orphan reaping, including after an assertion fails.
    while _children(1):
        with suppress(ChildProcessError):
            os.waitpid(-1, os.WNOHANG)
        if time.monotonic() >= deadline:
            raise TimeoutError("Parser sandbox stage=cleanup category=descendants-unconfirmed.")
        time.sleep(0.02)


def _children(pid: int) -> tuple[int, ...]:
    return tuple(
        int(child) for child in Path(f"/proc/{pid}/task/{pid}/children").read_text().split()
    )


def _namespace(process: Path, name: str) -> int:
    return (process / "ns" / name).stat().st_ino


def _session(pid: int) -> int:
    return int(Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[3])


def _status(process: Path) -> dict[str, str]:
    return {
        key: value.strip()
        for key, _, value in (
            line.partition(":") for line in (process / "status").read_text().splitlines()
        )
    }


def _apparmor(process: Path = Path("/proc/self")) -> str:
    return (process / "attr/current").read_text().strip()


def _read_namespace_report(path: Path) -> dict[str, int]:
    with path.open("rb") as capture:
        data = capture.read(_CAPTURE_BYTES + 1)
    if len(data) > _CAPTURE_BYTES:
        raise ValueError("The sandbox probe exceeded its capture limit.")
    report: object = json.loads(data)
    if type(report) is not dict:
        raise ValueError("Incomplete Bubblewrap namespace report.")
    values = cast("dict[str, object]", report)
    if set(values) != {"child-pid", *(f"{name}-namespace" for name in _SETUP_NAMESPACES)} or any(
        type(value) is not int or value <= 0 for value in values.values()
    ):
        raise ValueError("Incomplete Bubblewrap namespace report.")
    return cast("dict[str, int]", report)


def _fixture_failure(root: Path, stage: str) -> str:
    """Report a fixed classification while the raw stderr stays in private scratch."""
    try:
        with (root / "stderr").open("rb") as diagnostics:
            captured = diagnostics.read(_CAPTURE_BYTES + 1)
    except OSError:
        return f"Parser sandbox stage={stage} category=capture-unavailable."
    if len(captured) > _CAPTURE_BYTES:
        return f"Parser sandbox stage={stage} category=capture-overflow."
    lines = captured.splitlines()
    map_operations = {
        b"setting up uid map": "uid-map",
        b"setting up gid map": "gid-map",
        b"error writing to setgroups": "setgroups",
    }
    permission_classes = {
        b"Permission denied": "eacces",
        b"Operation not permitted": "eperm",
        b"Read-only file system": "erofs",
    }
    for line in lines:
        owner, _, message = line.partition(b": ")
        operation, _, detail = message.partition(b": ")
        if owner == b"bwrap" and (map_operation := map_operations.get(operation)):
            permission = permission_classes.get(detail, "other")
            return f"Parser sandbox stage={stage} category={map_operation}-{permission}."

    categories = (
        (b"parser-fixture: owner preparation failed", "owner-preparation"),
        (b"bwrap: No permissions to create a new namespace", "namespace-permission"),
        (b"bwrap: Creating new namespace failed", "namespace-create"),
        (b"bwrap: loopback:", "private-loopback"),
        (b"bwrap: Failed to make / slave", "root-propagation"),
        (b"bwrap: Failed to mount tmpfs", "initial-tmpfs"),
        (b"bwrap: setting up newroot bind", "newroot-bind"),
        (b"bwrap: mounting proc", "outer-proc-bind"),
        (b"bwrap: Can't bind mount", "fixture-bind-or-remount"),
        (b"bwrap: Failed to make old root rprivate", "oldroot-propagation"),
        (b"bwrap: unmount old root", "oldroot-detach"),
        (b"bwrap: umount old root", "oldroot-detach"),
        (b"bwrap: pivot_root", "pivot-root"),
        (b"bwrap: Unable to set up system call filtering", "child-seccomp"),
        (b"bwrap: execvp", "child-exec"),
        (b"AssertionError", "child-assertion"),
    )
    reason = next(
        (label for marker, label in categories if any(line.startswith(marker) for line in lines)),
        "unclassified",
    )
    return f"Parser sandbox stage={stage} category={reason}."


def _owner(root: Path, mode: str) -> int:
    resource.setrlimit(resource.RLIMIT_FSIZE, (_CAPTURE_BYTES, _CAPTURE_BYTES))
    sentinel = root / "outside"
    sentinel.write_bytes(b"outer fixture only")
    with (
        socket.socket(socket.AF_UNIX) as control,
        _FILTER.open("rb") as policy,
        (root / "child-ready").open("wb") as ready,
        (root / "namespaces.json").open("wb") as report,
    ):
        control.bind(os.fspath(root / "control"))
        control.listen(1)
        os.set_inheritable(control.fileno(), True)
        arguments = [
            "/opt/probe-tools/bwrap",
            "--unshare-user",
            "--unshare-pid",
            "--unshare-ipc",
            "--unshare-net",
            "--new-session",
            "--die-with-parent",
            "--clearenv",
            "--info-fd",
            str(report.fileno()),
        ]
        for path in ("/usr/local", "/usr/lib/x86_64-linux-gnu", "/lib64/ld-linux-x86-64.so.2"):
            arguments.extend(("--ro-bind", path, path))
        for option in (
            ("--symlink", "usr/lib", "/lib"),
            ("--ro-bind", __file__, "/fixture/test_sandbox_boundaries.py"),
            ("--dev-bind", "/dev/null", "/dev/null"),
            ("--perms", "0700", "--size", str(1024**3), "--tmpfs", "/scratch"),
            ("--chdir", "/scratch"),
            ("--seccomp", str(policy.fileno())),
        ):
            arguments.extend(option)
        arguments.extend(
            [
                "--",
                _CHILD_PYTHON,
                "-IB",
                "/fixture/test_sandbox_boundaries.py",
                "--child",
                str(root),
                str(control.fileno()),
                str(report.fileno()),
                mode,
            ]
        )
        with subprocess.Popen(
            arguments,
            stdout=ready,
            close_fds=True,
            pass_fds=(policy.fileno(), report.fileno()),
        ) as child:
            return child.wait()


def _child(root: Path, control_fd: int, report_fd: int, mode: str) -> None:
    assert os.getuid() != 0
    assert not (root / "outside").exists() and not (root / "control").exists()
    for path in (Path("/proc/self/status"), Path("/proc/sys")):
        try:
            path.stat()
        except FileNotFoundError:
            pass
        else:
            raise AssertionError("A process filesystem reached the sandbox.")
    for descriptor in (control_fd, report_fd):
        try:
            os.fstat(descriptor)
        except OSError as error:
            assert error.errno == errno.EBADF
        else:
            raise AssertionError("An outer descriptor reached the sandbox.")
    scratch = Path("/scratch/owned")
    scratch.write_bytes(b"private")
    assert scratch.read_bytes() == b"private"
    for family in (socket.AF_UNIX, socket.AF_INET, socket.AF_INET6):
        try:
            with socket.socket(family):
                raise AssertionError("A sandbox socket opened.")
        except OSError as error:
            assert error.errno == _DISABLED
    try:
        socket.getaddrinfo("parser-boundary.invalid", 53)
    except socket.gaierror:
        pass
    else:
        raise AssertionError("The child resolved an external name.")
    _require_namespace_syscalls_denied()

    reader, writer = os.pipe()
    descendant = os.fork()
    if descendant == 0:
        os.setsid()
        os.write(writer, b"r")
        if mode == "hold":
            os.read(reader, 1)
        os._exit(0)
    assert os.read(reader, 1) == b"r"
    if mode == "once":
        assert os.waitpid(descendant, 0) == (descendant, 0)
    assert os.write(sys.stdout.fileno(), b"ready\n") == len(b"ready\n")
    if mode == "hold":
        os.read(reader, 1)
    else:
        assert os.read(sys.stdin.fileno(), 1) == b"r"


def _require_namespace_syscalls_denied() -> None:
    syscall = ctypes.CDLL(None, use_errno=True).syscall
    syscall.restype = ctypes.c_long
    clone3 = (ctypes.c_uint64 * 11)(_USER_NAMESPACE, 0, 0, 0, 17)
    # Without seccomp, setns on this invalid FD would return EBADF.
    checks = (
        (56, ctypes.c_ulong(_USER_NAMESPACE | 17), 0, 0, 0, 0),
        (435, ctypes.byref(clone3), ctypes.sizeof(clone3)),
        (272, _USER_NAMESPACE),
        (308, -1, _USER_NAMESPACE),
    )
    for operation in checks:
        outcome = syscall(*operation)
        if operation[0] in (56, 435) and outcome == 0:
            os._exit(1)
        assert outcome == -1 and ctypes.get_errno() == _DISABLED


if __name__ == "__main__":
    match sys.argv[1:]:
        case ["--owner", root, ("once" | "hold") as mode]:
            try:
                raise SystemExit(_owner(Path(root), mode))
            except OSError:
                sys.stderr.write("parser-fixture: owner preparation failed\n")
                raise SystemExit(1) from None
        case ["--child", root, control_fd, report_fd, ("once" | "hold") as mode]:
            _child(Path(root), int(control_fd), int(report_fd), mode)
        case _:
            raise SystemExit("Unknown fixed sandbox test mode.")
