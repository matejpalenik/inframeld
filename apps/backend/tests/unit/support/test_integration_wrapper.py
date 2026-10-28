"""Verify the serial wrapper's real process and exit behavior without containers."""

import os
import signal
import subprocess
import sys
import time
from contextlib import suppress
from pathlib import Path

import pytest

_WRAPPER = Path(__file__).resolve().parents[5] / "scripts/test-integration.sh"
_PROBE = r"""
source "$1"
set -euo pipefail
cleanup_file="$2"
cleanup_status="$3"
shift 3
set -m
active_pid=""
cleanup_stack() {
    printf 'cleanup\n' >> "${cleanup_file}"
    return "${cleanup_status}"
}
trap cleanup_test_services EXIT
trap 'interrupt_run 130' INT
trap 'interrupt_run 143' TERM
run_step "$@"
"""


def _arguments(cleanup: Path, code: str, cleanup_status: int = 0) -> list[str]:
    return [
        "bash",
        "-c",
        _PROBE,
        "wrapper-probe",
        str(_WRAPPER),
        str(cleanup),
        str(cleanup_status),
        sys.executable,
        "-c",
        code,
    ]


def _wait_for_file(path: Path, child: subprocess.Popen[str]) -> None:
    deadline = time.monotonic() + 5
    while not path.exists() and child.poll() is None and time.monotonic() < deadline:
        time.sleep(0.01)
    assert path.exists(), "Controlled child did not become ready"


def _assert_process_stops(pid: int) -> None:
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.01)
    pytest.fail(f"Controlled process {pid} survived wrapper shutdown")


def _kill_if_alive(pid: int | None) -> None:
    if pid is not None:
        with suppress(ProcessLookupError):
            os.kill(pid, signal.SIGKILL)


def _close_probe(child: subprocess.Popen[str], pid: int | None) -> None:
    if child.poll() is None:
        child.terminate()
    try:
        child.communicate(timeout=12)
    except subprocess.TimeoutExpired:
        _kill_if_alive(pid)
        child.kill()
        child.communicate(timeout=3)
    finally:
        _kill_if_alive(pid)


@pytest.mark.parametrize(
    "child_status, cleanup_status, expected", [(0, 0, 0), (7, 0, 7), (0, 9, 1), (7, 9, 7)]
)
def test_exit_status_and_cleanup(
    tmp_path: Path, child_status: int, cleanup_status: int, expected: int
) -> None:
    cleanup = tmp_path / "cleanup"
    completed = subprocess.run(
        _arguments(cleanup, f"raise SystemExit({child_status})", cleanup_status),
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert completed.returncode == expected
    assert cleanup.read_text() == "cleanup\n"


@pytest.mark.parametrize(
    "requested_signal, expected", [(signal.SIGINT, 130), (signal.SIGTERM, 143)]
)
def test_cancellation_reaps_active_child(
    tmp_path: Path, requested_signal: signal.Signals, expected: int
) -> None:
    ready, cleanup = tmp_path / "ready", tmp_path / "cleanup"
    code = f"from pathlib import Path; import os,time; Path({str(ready)!r}).write_text(str(os.getpid())); time.sleep(60)"
    child = subprocess.Popen(
        _arguments(cleanup, code), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    pid = None
    try:
        _wait_for_file(ready, child)
        pid = int(ready.read_text())
        child.send_signal(requested_signal)
        _, errors = child.communicate(timeout=13)
        assert child.returncode == expected, errors
        _assert_process_stops(pid)
        assert cleanup.read_text() == "cleanup\n"
    finally:
        _close_probe(child, pid)


def test_term_ignoring_child_is_killed_and_reaped(tmp_path: Path) -> None:
    ready, cleanup = tmp_path / "ready", tmp_path / "cleanup"
    code = f"from pathlib import Path; import os,signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); Path({str(ready)!r}).write_text(str(os.getpid())); time.sleep(60)"
    child = subprocess.Popen(
        _arguments(cleanup, code), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    pid = None
    try:
        _wait_for_file(ready, child)
        pid = int(ready.read_text())
        started = time.monotonic()
        child.terminate()
        _, errors = child.communicate(timeout=13)
        assert child.returncode == 143, errors
        assert time.monotonic() - started < 12
        _assert_process_stops(pid)
        assert cleanup.read_text() == "cleanup\n"
    finally:
        _close_probe(child, pid)


def test_descendant_is_stopped_after_its_leader_exits(tmp_path: Path) -> None:
    ready, cleanup = tmp_path / "ready", tmp_path / "cleanup"
    descendant_code = f"from pathlib import Path; import os,time; Path({str(ready)!r}).write_text(str(os.getpid())); time.sleep(60)"
    code = f"import subprocess,sys,time; from pathlib import Path; subprocess.Popen([sys.executable, '-c', {descendant_code!r}]); p=Path({str(ready)!r});\nwhile not p.exists(): time.sleep(0.01)"
    child = subprocess.Popen(
        _arguments(cleanup, code), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    pid = None
    try:
        _wait_for_file(ready, child)
        pid = int(ready.read_text())
        _, errors = child.communicate(timeout=13)
        assert child.returncode == 0, errors
        _assert_process_stops(pid)
        assert cleanup.read_text() == "cleanup\n"
    finally:
        _close_probe(child, pid)


_CLEANUP_PROBE = r"""
source "$1"
set -euo pipefail
cleanup_python="$2"
cleanup_code="$3"
phase_code="$4"
set -m
active_pid=""
cleanup_stack() {
    "$cleanup_python" -c "$cleanup_code"
}
trap 'cleanup_test_services 1' EXIT
trap 'interrupt_run 130' INT
trap 'interrupt_run 143' TERM
run_step "$cleanup_python" -c "$phase_code"
"""


def _cleanup_arguments(cleanup_code: str, phase_code: str) -> list[str]:
    return [
        "bash",
        "-c",
        _CLEANUP_PROBE,
        "cleanup-probe",
        str(_WRAPPER),
        sys.executable,
        cleanup_code,
        phase_code,
    ]


def _read_cleanup_processes(ready: Path, child: subprocess.Popen[str]) -> list[int]:
    _wait_for_file(ready, child)
    return [int(value) for value in ready.read_text().split()]


def _close_cleanup_probe(child: subprocess.Popen[str], ready: Path, phase_pid: int | None) -> None:
    if ready.exists():
        values = [int(value) for value in ready.read_text().split()]
        if len(values) >= 2:
            with suppress(ProcessLookupError):
                os.killpg(values[1], signal.SIGKILL)
    _close_probe(child, phase_pid)


@pytest.mark.parametrize(
    "prior_status, expected",
    [(0, 1), (7, 7), (130, 130), (143, 143)],
    ids=["success", "test-failure", "interrupt", "termination"],
)
def test_hanging_cleanup_preserves_original_exit(
    tmp_path: Path, prior_status: int, expected: int
) -> None:
    ready, phase_ready = tmp_path / "cleanup-ready", tmp_path / "phase-ready"
    cleanup_code = (
        "from pathlib import Path; import os,time; "
        f"p=Path({str(ready)!r}); temporary=p.with_suffix('.tmp'); "
        "temporary.write_text(f'{os.getpid()} {os.getpgrp()}'); temporary.replace(p); time.sleep(60)"
    )
    if prior_status in (130, 143):
        phase_code = f"from pathlib import Path; import os,time; Path({str(phase_ready)!r}).write_text(str(os.getpid())); time.sleep(60)"
    else:
        phase_code = f"raise SystemExit({prior_status})"
    child = subprocess.Popen(
        _cleanup_arguments(cleanup_code, phase_code),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    phase_pid = None
    try:
        if prior_status in (130, 143):
            _wait_for_file(phase_ready, child)
            phase_pid = int(phase_ready.read_text())
            child.send_signal(signal.SIGINT if prior_status == 130 else signal.SIGTERM)
        processes = _read_cleanup_processes(ready, child)
        started = time.monotonic()
        _, errors = child.communicate(timeout=13)
        assert child.returncode == expected, errors
        assert time.monotonic() - started < 12
        assert "cleanup exceeded" in errors
        assert "incomplete" in errors
        assert "test-services-down" in errors
        for pid in processes:
            _assert_process_stops(pid)
        if phase_pid is not None:
            _assert_process_stops(phase_pid)
    finally:
        _close_cleanup_probe(child, ready, phase_pid)


def test_cleanup_ignoring_term_and_its_descendant_are_killed(tmp_path: Path) -> None:
    ready, descendant_ready = tmp_path / "cleanup-ready", tmp_path / "descendant-ready"
    descendant_code = f"from pathlib import Path; import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); Path({str(descendant_ready)!r}).touch(); time.sleep(60)"
    cleanup_code = (
        "from pathlib import Path; import os,signal,subprocess,sys,time; "
        "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        f"descendant=subprocess.Popen([sys.executable,'-c',{descendant_code!r}]); "
        f"descendant_ready=Path({str(descendant_ready)!r}); "
        "\nwhile not descendant_ready.exists(): time.sleep(0.01)\n"
        f"p=Path({str(ready)!r}); temporary=p.with_suffix('.tmp'); "
        "temporary.write_text(f'{os.getpid()} {os.getpgrp()} {descendant.pid}'); "
        "temporary.replace(p); time.sleep(60)"
    )
    child = subprocess.Popen(
        _cleanup_arguments(cleanup_code, "raise SystemExit(0)"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        processes = _read_cleanup_processes(ready, child)
        started = time.monotonic()
        _, errors = child.communicate(timeout=13)
        assert child.returncode == 1, errors
        assert time.monotonic() - started < 12
        assert "cleanup exceeded" in errors
        for pid in processes:
            _assert_process_stops(pid)
        with pytest.raises(ProcessLookupError):
            os.killpg(processes[1], 0)
    finally:
        _close_cleanup_probe(child, ready, None)
