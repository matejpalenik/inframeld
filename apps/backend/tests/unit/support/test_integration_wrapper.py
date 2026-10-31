"""Exercise owned phase lifetimes and serial cleanup using only private bounded children."""

import json
import os
import shutil
import signal
import subprocess
import sys
import time
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[5]
_DRIVER = r"""
import json, os, signal, subprocess, sys, time
from pathlib import Path
root = Path(__file__).resolve().parents[1]
configuration = json.loads((root / "fixture.json").read_text())
phase = sys.argv[1]
with (root / "calls").open("a") as output:
    output.write(json.dumps({"phase": phase, "arguments": sys.argv[2:], "value": os.getenv("WRAPPER_FIXTURE_VALUE"), "cwd": os.getcwd()}) + "\n")
print("output:" + phase, flush=True)
print("error:" + phase, file=sys.stderr, flush=True)
if phase == "test-services-up":
    if configuration.get("startup_status"):
        raise SystemExit(configuration["startup_status"])
    active = configuration.get("blocked_phase") == "startup"
elif phase == "test-run":
    assert sys.stdin.read() == ""
    active = configuration.get("blocked_phase") == "test"
else:
    active = configuration.get("hang_cleanup", False)
if active or (phase == "test-run" and configuration.get("descendant")):
    ignore = configuration.get("ignore_term", False)
    program = "import os,signal,time; " + ("signal.signal(signal.SIGTERM,signal.SIG_IGN); " if ignore else "") + "time.sleep(8)"
    descendant = subprocess.Popen([sys.executable, "-c", program])
    # Allow the bounded descendant to install its handler before the leader exits.
    time.sleep(0.05)
    (root / ("cleanup-ready" if phase == "test-services-down" else "ready")).write_text(json.dumps({"leader": os.getpid(), "descendant": descendant.pid}))
if active:
    if phase == "test-services-down" and not configuration.get("cleanup_term_default"):
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
    time.sleep(8)
if phase == "test-run":
    raise SystemExit(configuration.get("test_status", 0))
if phase == "test-services-down":
    raise SystemExit(configuration.get("cleanup_status", 0))
"""
_PROBE = r"""
import json, os, runpy, signal, sys
from pathlib import Path
root = Path(sys.argv[1])
namespace = runpy.run_path(str(root / "apps/backend/tests/support/integration_process_runner.py"))
class ProbeRunner(namespace["IntegrationRunner"]):
    def _signal_group(self, phase, number):
        observed = os.waitid(os.P_PID, phase.child.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
        self.record({"event": "signal", "pid": phase.child.pid, "number": number, "retained_exit": observed is not None})
        return super()._signal_group(phase, number)
    def _reap(self, phase):
        result = super()._reap(phase)
        self.record({"event": "reap", "pid": phase.child.pid, "owned": phase.owned})
        return result
    def _run_phase(self, name, arguments, *, cleanup=False):
        result = super()._run_phase(name, arguments, cleanup=cleanup)
        if name == "test-services-up" and (root / "between").exists():
            os.kill(os.getpid(), signal.SIGTERM)
        return result
    def record(self, event):
        with (root / "ownership").open("a") as output:
            output.write(json.dumps(event) + "\n")
raise SystemExit(ProbeRunner(root, cleanup_work_seconds=0.2, term_seconds=0.2, kill_seconds=0.2).run(sys.argv[2:]))
"""


@dataclass
class Probe:
    """Keep the fixture's immediate wrapper child unreaped until its last possible signal."""

    child: subprocess.Popen[bytes]
    root: Path
    reaped: bool = False
    status: int | None = None

    def observe(self) -> bool:
        if self.reaped:
            return True
        return os.waitid(os.P_PID, self.child.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT) is not None

    def finish(self, timeout: float = 5) -> tuple[int, str, str]:
        deadline = time.monotonic() + timeout
        while not self.observe() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert self.observe(), "The owned wrapper did not exit within the fixture deadline."
        if not self.reaped:
            pid, status = os.waitpid(self.child.pid, os.WNOHANG)
            assert pid == self.child.pid
            self.status = os.waitstatus_to_exitcode(status)
            self.child.returncode = self.status
            self.reaped = True
        assert self.status is not None
        return self.status, (self.root / "stdout").read_text(), (self.root / "stderr").read_text()

    def wait_file(self, name: str) -> Path:
        path = self.root / name
        deadline = time.monotonic() + 3
        while not path.exists() and not self.observe() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert path.exists(), (self.root / "stderr").read_text()
        return path

    def send(self, number: signal.Signals) -> None:
        assert not self.reaped and not self.observe()
        os.kill(self.child.pid, number)

    def close(self) -> None:
        if self.reaped:
            return
        if not self.observe():
            # Only this retained immediate child's group is owned by the fixture.
            os.killpg(self.child.pid, signal.SIGTERM)
            deadline = time.monotonic() + 2
            while not self.observe() and time.monotonic() < deadline:
                time.sleep(0.01)
            if not self.observe():
                os.killpg(self.child.pid, signal.SIGKILL)
        self.finish(timeout=2)

    def calls(self) -> list[dict[str, object]]:
        path = self.root / "calls"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def assert_descendants_stopped(self, timeout: float = 1) -> None:
        for name in ("ready", "cleanup-ready"):
            path = self.root / name
            if not path.exists():
                continue
            pid = json.loads(path.read_text())["descendant"]
            deadline = time.monotonic() + timeout
            while True:
                state = subprocess.run(
                    ["ps", "-p", str(pid), "-o", "stat="],
                    capture_output=True,
                    text=True,
                    timeout=1,
                    check=False,
                )
                assert state.returncode in (0, 1), "Private descendant state was unavailable."
                if not state.stdout.strip() or state.stdout.strip().startswith("Z"):
                    break
                assert time.monotonic() < deadline, "Private descendant remained executable."
                time.sleep(0.01)


@contextmanager
def launch(
    tmp_path: Path,
    configuration: dict[str, object],
    selectors: tuple[str, ...] = (),
    *,
    public: bool = False,
    between: bool = False,
    program: str | None = None,
) -> Generator[Probe]:
    root = tmp_path / "private repository"
    (root / "scripts").mkdir(parents=True)
    (root / "apps/backend/tests/support").mkdir(parents=True)
    shutil.copy2(_ROOT / "scripts/test-integration.sh", root / "scripts/test-integration.sh")
    shutil.copy2(
        _ROOT / "apps/backend/tests/support/integration_process_runner.py",
        root / "apps/backend/tests/support/integration_process_runner.py",
    )
    driver = root / "scripts/dev-compose.sh"
    driver.write_text(f"#!{sys.executable}\n" + _DRIVER)
    driver.chmod(0o700)
    (root / "fixture.json").write_text(json.dumps(configuration))
    if between:
        (root / "between").touch()
    environment = dict(os.environ)
    environment["PATH"] = str(Path(sys.executable).parent) + os.pathsep + environment["PATH"]
    environment["WRAPPER_FIXTURE_VALUE"] = "kept value with spaces"
    arguments = (
        ["bash", str(root / "scripts/test-integration.sh"), *selectors]
        if public
        else [sys.executable, "-c", program or _PROBE, str(root), *selectors]
    )
    with (root / "stdout").open("wb") as output, (root / "stderr").open("wb") as errors:
        child = subprocess.Popen(
            arguments,
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=errors,
            env=environment,
            start_new_session=True,
        )
        probe = Probe(child, root)
        try:
            yield probe
        finally:
            probe.close()
            # On a failing test, the fixture observes its bounded descendants' fuse.
            # It never signals a numeric descendant PID from a stale ready file.
            probe.assert_descendants_stopped(timeout=9)


@pytest.mark.parametrize(
    "test_status,cleanup_status,expected", [(0, 0, 0), (7, 0, 7), (0, 9, 1), (7, 9, 7)]
)
def test_exit_status_and_single_cleanup(
    tmp_path: Path, test_status: int, cleanup_status: int, expected: int
) -> None:
    with launch(
        tmp_path, {"test_status": test_status, "cleanup_status": cleanup_status}, public=True
    ) as probe:
        status, _, _ = probe.finish()
        assert status == expected
        assert [event["phase"] for event in probe.calls()] == [
            "test-services-up",
            "test-run",
            "test-services-down",
        ]


def test_startup_failure_still_cleans_once_without_testing(tmp_path: Path) -> None:
    with launch(tmp_path, {"startup_status": 3}) as probe:
        status, _, _ = probe.finish()
        assert status == 3
        assert [event["phase"] for event in probe.calls()] == [
            "test-services-up",
            "test-services-down",
        ]


def test_public_launcher_preserves_arguments_environment_streams_and_closed_stdin(
    tmp_path: Path,
) -> None:
    selectors = ("tests/a path/test_example.py", "-k", "first or second")
    with launch(tmp_path, {}, selectors, public=True) as probe:
        status, output, errors = probe.finish()
        assert status == 0
        calls = probe.calls()
        assert calls[1]["arguments"] == list(selectors)
        assert all(event["cwd"] == str(probe.root) for event in calls)
        assert all(event["value"] == "kept value with spaces" for event in calls)
        assert "output:test-run" in output and "error:test-run" in errors


@pytest.mark.parametrize("ignore_term", [False, True])
def test_exited_leader_is_retained_until_descendant_shutdown(
    tmp_path: Path, ignore_term: bool
) -> None:
    with launch(
        tmp_path, {"descendant": True, "ignore_term": ignore_term, "test_status": 7}
    ) as probe:
        started = time.monotonic()
        status, _, errors = probe.finish()
        assert status == 7, errors
        assert time.monotonic() - started < 3
        probe.assert_descendants_stopped()
        ownership = [
            json.loads(line) for line in (probe.root / "ownership").read_text().splitlines()
        ]
        reaped: set[int] = set()
        for event in ownership:
            if event["event"] == "signal":
                assert event["pid"] not in reaped
                assert event["retained_exit"] is True
            else:
                assert event["owned"] is False
                reaped.add(event["pid"])
        if ignore_term:
            assert any(event.get("number") == signal.SIGKILL for event in ownership)


@pytest.mark.parametrize("phase", ["startup", "test"])
@pytest.mark.parametrize("number,expected", [(signal.SIGINT, 130), (signal.SIGTERM, 143)])
def test_cancellation_stops_owned_work_before_single_cleanup(
    tmp_path: Path, phase: str, number: signal.Signals, expected: int
) -> None:
    with launch(tmp_path, {"blocked_phase": phase, "ignore_term": True}) as probe:
        probe.wait_file("ready")
        probe.send(number)
        status, _, errors = probe.finish()
        assert status == expected, errors
        probe.assert_descendants_stopped()
        phases = [event["phase"] for event in probe.calls()]
        assert phases.count("test-services-down") == 1
        assert phases == (
            ["test-services-up", "test-services-down"]
            if phase == "startup"
            else ["test-services-up", "test-run", "test-services-down"]
        )


def test_between_phase_cancellation_never_starts_testing(tmp_path: Path) -> None:
    with launch(tmp_path, {}, between=True) as probe:
        status, _, errors = probe.finish()
        assert status == 143, errors
        assert [event["phase"] for event in probe.calls()] == [
            "test-services-up",
            "test-services-down",
        ]


@pytest.mark.parametrize("prior,expected", [(0, 1), (7, 7)])
def test_hanging_cleanup_has_bounded_stop_and_preserves_failure(
    tmp_path: Path, prior: int, expected: int
) -> None:
    with launch(
        tmp_path, {"test_status": prior, "hang_cleanup": True, "ignore_term": True}
    ) as probe:
        probe.wait_file("cleanup-ready")
        started = time.monotonic()
        status, _, errors = probe.finish()
        assert status == expected, errors
        assert time.monotonic() - started < 2
        probe.assert_descendants_stopped()
        assert "Cleanup may be incomplete" in errors
        assert "./scripts/dev-compose.sh test-services-down" in errors
        assert [event["phase"] for event in probe.calls()].count("test-services-down") == 1


@pytest.mark.parametrize("number,expected", [(signal.SIGINT, 130), (signal.SIGTERM, 143)])
def test_repeated_signals_during_cleanup_preserve_original_cancellation(
    tmp_path: Path, number: signal.Signals, expected: int
) -> None:
    with launch(
        tmp_path, {"blocked_phase": "test", "hang_cleanup": True, "ignore_term": True}
    ) as probe:
        probe.wait_file("ready")
        probe.send(number)
        probe.wait_file("cleanup-ready")
        probe.send(signal.SIGINT)
        probe.send(signal.SIGTERM)
        status, _, errors = probe.finish()
        assert status == expected, errors
        probe.assert_descendants_stopped()
        assert [event["phase"] for event in probe.calls()].count("test-services-down") == 1


def test_cleanup_executable_keeps_default_term_disposition(tmp_path: Path) -> None:
    with launch(tmp_path, {"hang_cleanup": True, "cleanup_term_default": True}) as probe:
        probe.wait_file("cleanup-ready")
        status, _, errors = probe.finish()
        assert status == 1, errors
        probe.assert_descendants_stopped()
        ownership = [
            json.loads(line) for line in (probe.root / "ownership").read_text().splitlines()
        ]
        assert any(event.get("number") == signal.SIGTERM for event in ownership)
        assert not any(event.get("number") == signal.SIGKILL for event in ownership)


@pytest.mark.parametrize("owned", [False, True])
def test_lost_or_reaped_child_identity_never_permits_group_signalling(
    tmp_path: Path, owned: bool
) -> None:
    program = r"""
import json, os, runpy, sys
from pathlib import Path
root = Path(sys.argv[1])
class LostChild(runpy.run_path(str(root / "apps/backend/tests/support/integration_process_runner.py"))["IntegrationRunner"]):
    def _stop_phase(self, phase):
        assert phase.observe()
        _, status = os.waitpid(phase.child.pid, os.WNOHANG)
        phase.child.returncode = os.waitstatus_to_exitcode(status)
        phase.owned = json.loads((root / "fixture.json").read_text())["stale_owned"]
        with (root / "reaped").open("a") as output:
            output.write("reaped\n")
        original = os.killpg
        def forbidden(*arguments):
            raise AssertionError("A numeric group was signalled after its leader was reaped.")
        os.killpg = forbidden
        try:
            return super()._stop_phase(phase)
        finally:
            os.killpg = original
raise SystemExit(LostChild(root, cleanup_work_seconds=0.2, term_seconds=0.2, kill_seconds=0.2).run([]))
"""
    with launch(tmp_path, {"stale_owned": owned}, program=program) as probe:
        status, _, errors = probe.finish()
        assert status == 1, errors
        assert "numeric group was signalled" not in errors
        assert (probe.root / "reaped").read_text() == "reaped\nreaped\n"


def test_ps_observation_timeout_is_bounded_by_the_existing_deadline(tmp_path: Path) -> None:
    program = r"""
import runpy, subprocess, sys, time
from pathlib import Path
root = Path(sys.argv[1])
class UnavailableProcesses(runpy.run_path(str(root / "apps/backend/tests/support/integration_process_runner.py"))["IntegrationRunner"]):
    def _running_members(self, phase, deadline):
        original = subprocess.run
        def unavailable(*arguments, **options):
            assert 0 < options["timeout"] <= 0.2
            with (root / "timeouts").open("a") as output:
                output.write(str(options["timeout"]) + "\n")
            raise subprocess.TimeoutExpired("ps", options["timeout"])
        subprocess.run = unavailable
        try:
            return super()._running_members(phase, deadline)
        finally:
            subprocess.run = original
raise SystemExit(UnavailableProcesses(root, cleanup_work_seconds=0.2, term_seconds=0.2, kill_seconds=0.2).run([]))
"""
    with launch(tmp_path, {}, program=program) as probe:
        status, _, errors = probe.finish()
        assert status == 1, errors
        assert "shutdown could not be confirmed" in errors
        observed = [float(line) for line in (probe.root / "timeouts").read_text().splitlines()]
        assert observed and all(0 < duration <= 0.2 for duration in observed)


def test_ps_failure_remains_incomplete_cleanup(tmp_path: Path) -> None:
    program = r"""
import runpy, sys
from pathlib import Path
root = Path(sys.argv[1])
class UnavailableProcesses(runpy.run_path(str(root / "apps/backend/tests/support/integration_process_runner.py"))["IntegrationRunner"]):
    def _running_members(self, phase, deadline):
        raise OSError("controlled observation failure")
raise SystemExit(UnavailableProcesses(root, cleanup_work_seconds=0.2, term_seconds=0.2, kill_seconds=0.2).run([]))
"""
    with launch(tmp_path, {}, program=program) as probe:
        status, _, errors = probe.finish()
        assert status == 1
        assert "shutdown could not be confirmed" in errors
        assert "Cleanup may be incomplete" in errors


def test_unsupported_waitid_toolchain_fails_before_startup(tmp_path: Path) -> None:
    program = r"""
import os, runpy, sys
from pathlib import Path
root = Path(sys.argv[1])
runner = runpy.run_path(str(root / "apps/backend/tests/support/integration_process_runner.py"))["IntegrationRunner"]
del os.WNOWAIT
raise SystemExit(runner(root).run([]))
"""
    with launch(tmp_path, {}, program=program) as probe:
        status, _, errors = probe.finish()
        assert status == 2
        assert "Python 3.13" in errors
        assert probe.calls() == []


def test_cancellation_during_spawn_retains_the_new_child_and_cleans_once(tmp_path: Path) -> None:
    program = r"""
import os, runpy, signal, subprocess, sys
from pathlib import Path
root = Path(sys.argv[1])
runner = runpy.run_path(str(root / "apps/backend/tests/support/integration_process_runner.py"))["IntegrationRunner"]
original = subprocess.Popen
sent = False
def spawn(*arguments, **options):
    global sent
    child = original(*arguments, **options)
    if not sent:
        sent = True
        os.kill(os.getpid(), signal.SIGTERM)
    return child
subprocess.Popen = spawn
raise SystemExit(runner(root, cleanup_work_seconds=0.2, term_seconds=0.2, kill_seconds=0.2).run([]))
"""
    with launch(tmp_path, {}, program=program) as probe:
        status, _, errors = probe.finish()
        assert status == 143, errors
        phases = [event["phase"] for event in probe.calls()]
        assert "test-run" not in phases and phases.count("test-services-down") == 1
