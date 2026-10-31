"""Retain one SDK tooling target until all numeric group signalling ends."""

import json
import os
import select
import shutil
import signal
import subprocess
import sys
import time
from contextlib import suppress
from dataclasses import dataclass, field
from typing import cast


@dataclass(frozen=True)
class StartRequest:
    argv: tuple[str, ...]
    cwd: str | None
    env: dict[str, str]
    execution_deadline: int
    startup_deadline: int
    cleanup_ms: int
    mode: str


def parse_start(value: dict[str, object]) -> StartRequest:
    expected = {
        "version",
        "type",
        "argv",
        "cwd",
        "env",
        "executionDeadline",
        "startupDeadline",
        "cleanupMs",
        "mode",
    }
    if set(value) != expected or type(value["version"]) is not int or value["version"] != 1:
        raise ValueError("Invalid start fields or version.")
    if value["type"] != "start" or value["mode"] not in ("command", "backend"):
        raise ValueError("Invalid start kind.")
    arguments = value["argv"]
    if not isinstance(arguments, list) or not arguments:
        raise ValueError("A target program is required.")
    argv = tuple(_text(item) for item in cast("list[object]", arguments))
    if not argv[0]:
        raise ValueError("A target program is required.")
    cwd = None if value["cwd"] is None else _text(value["cwd"])
    raw_env = value["env"]
    if not isinstance(raw_env, dict):
        raise ValueError("Invalid target environment.")
    env = {_text(key): _text(item) for key, item in cast("dict[object, object]", raw_env).items()}
    if any(not key or "=" in key for key in env):
        raise ValueError("Invalid target environment key.")
    execution = _integer(value["executionDeadline"])
    startup = _integer(value["startupDeadline"])
    cleanup = _integer(value["cleanupMs"])
    if cleanup <= 0:
        raise ValueError("A positive cleanup budget is required.")
    return StartRequest(argv, cwd, env, execution, startup, cleanup, _text(value["mode"]))


def _text(value: object) -> str:
    if not isinstance(value, str) or "\0" in value:
        raise ValueError("Invalid control text.")
    return value


def _integer(value: object) -> int:
    if type(value) is not int:
        raise ValueError("Invalid control integer.")
    return value


@dataclass
class OwnedTarget:
    """Keep the immediate target waitable through its final group signal."""

    child: subprocess.Popen[bytes]
    owned: bool = True
    status: int | None = None
    errors: list[str] = field(default_factory=list[str])
    reaped: bool = False
    signal_attempted: bool = False
    exited_before_signal: bool = False

    def observe(self) -> bool:
        if not self.owned:
            return False
        try:
            observed = os.waitid(os.P_PID, self.child.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
        except OSError:
            self.owned = False
            self.errors.append("wait-ownership-lost")
            return False
        if observed is not None:
            if not self.signal_attempted:
                self.exited_before_signal = True
            self.status = (
                observed.si_status
                if observed.si_code == os.CLD_EXITED
                else 128 + observed.si_status
            )
        return observed is not None

    def signal_group(self, number: signal.Signals) -> bool:
        """Attempt a signal only while the sole waiter still owns this child."""
        if not self.owned:
            return False
        self.observe()
        if not self.owned:
            return False
        self.signal_attempted = True
        try:
            os.killpg(self.child.pid, number)
        except ProcessLookupError:
            return True
        except OSError:
            self.errors.append("group-signal-failed")
            return False
        return True

    def reap(self) -> bool:
        if not self.observe() or not self.owned:
            return False
        self.owned = False
        try:
            pid, status = os.waitpid(self.child.pid, os.WNOHANG)
        except OSError:
            self.errors.append("target-reap-failed")
            return False
        if pid != self.child.pid:
            self.errors.append("target-not-reaped")
            return False
        self.child.returncode = os.waitstatus_to_exitcode(status)
        self.reaped = True
        return True


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate control field.")
        result[key] = value
    return result


def _invalid_constant(value: str) -> object:
    raise ValueError("Non-finite control number.")


def decode_document(payload: bytes) -> dict[str, object]:
    if len(payload) > 1024 * 1024:
        raise ValueError("Control document exceeded its byte budget.")
    value: object = json.loads(
        payload.decode("utf-8", errors="strict"),
        object_pairs_hook=_unique_pairs,
        parse_constant=_invalid_constant,
    )
    if not isinstance(value, dict):
        raise ValueError("Control document must be an object.")
    return cast("dict[str, object]", value)


def executable_members(payload: bytes, group: int) -> bool:
    live = False
    for line in payload.decode("ascii", errors="strict").splitlines():
        if not line.strip():
            continue
        fields = line.split()
        if len(fields) != 3:
            raise ValueError("Incomplete process observation.")
        pid, pgid = int(fields[0]), int(fields[1])
        if pid <= 0 or pgid < 0:
            raise ValueError("Invalid process observation.")
        if pgid == group and not fields[2].startswith("Z"):
            live = True
    return live


def _clock() -> int:
    return time.monotonic_ns() // 1_000_000


def _members(target: OwnedTarget, deadline: int) -> bool:
    """Read a checked, byte-bounded ps result within the existing stop deadline."""
    deadline = min(deadline, _clock() + 1000)
    if _clock() >= deadline:
        raise TimeoutError
    observation = subprocess.Popen(
        ["ps", "-A", "-o", "pid=,pgid=,stat="],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    assert observation.stdout is not None
    output = bytearray()
    stream = observation.stdout
    try:
        os.set_blocking(stream.fileno(), False)
        while _clock() < deadline:
            readable, _, _ = select.select([stream], [], [], max(0, deadline - _clock()) / 1000)
            if not readable:
                raise TimeoutError
            chunk = os.read(stream.fileno(), 65536)
            if not chunk:
                break
            output.extend(chunk)
            if len(output) > 4 * 1024 * 1024:
                raise ValueError("Process observation exceeded its byte budget.")
        else:
            raise TimeoutError
        code = observation.wait(timeout=max(0, deadline - _clock()) / 1000)
        if code != 0:
            raise ValueError("Process observation failed.")
        return executable_members(bytes(output), target.child.pid)
    finally:
        # Python is the sole waiter of this separate immediate ps child too.
        if observation.poll() is None:
            observation.kill()
            try:
                observation.wait(timeout=max(0, deadline - _clock()) / 1000)
            except subprocess.TimeoutExpired:
                target.errors.append("observation-child-unresolved")
        stream.close()


def stop_target(target: OwnedTarget, deadline: int, cleanup_ms: int, mode: str) -> str:
    """Finish owned signalling and reaping inside the first fixed cleanup budget."""
    reserve = min(1000, max(1, cleanup_ms // 2))
    term_deadline = deadline - reserve
    if mode == "backend":
        term_deadline = min(term_deadline, _clock() + 1500)
    quiescent = False
    observation_valid = True

    def check() -> bool:
        nonlocal observation_valid
        if not target.observe():
            return False
        try:
            return not _members(target, deadline)
        except (OSError, ValueError, subprocess.SubprocessError, TimeoutError):
            observation_valid = False
            if "group-observation-failed" not in target.errors:
                target.errors.append("group-observation-failed")
            return False

    quiescent = check()
    for number, phase_deadline in (
        (signal.SIGTERM, term_deadline),
        (signal.SIGKILL, deadline),
    ):
        if quiescent or not target.owned or _clock() >= deadline:
            break
        target.signal_group(number)
        while target.owned and _clock() < phase_deadline:
            quiescent = check()
            if quiescent:
                break
            time.sleep(min(0.01, max(0, phase_deadline - _clock()) / 1000))

    # Revoke even when a surviving target cannot yet be reaped. No later signal is allowed.
    target.reap()
    target.owned = False
    if not quiescent:
        target.errors.append("group-shutdown-unconfirmed")
    if not target.reaped:
        target.errors.append("target-reap-unconfirmed")
    if not observation_valid:
        return "unknown"
    return "quiescent" if quiescent else "unknown"


class Control:
    """Bound one inherited private channel, without exposing it to the target."""

    def __init__(self, fd: int) -> None:
        self.fd = fd
        self.buffer = bytearray()
        self.sent = 0
        os.set_blocking(fd, False)

    def send(self, value: dict[str, object], deadline: int) -> None:
        payload = json.dumps({"version": 1, **value}, separators=(",", ":")).encode() + b"\n"
        self.sent += len(payload)
        if len(payload) > 16384 or self.sent > 65536:
            raise ValueError("Control output exceeded its byte budget.")
        deadline = min(deadline, _clock() + 2000)
        remaining = memoryview(payload)
        while remaining:
            try:
                count = os.write(self.fd, remaining)
                if not count:
                    raise BrokenPipeError
                remaining = remaining[count:]
            except BlockingIOError:
                if _clock() >= deadline:
                    raise TimeoutError from None
                select.select([], [self.fd], [], max(0, deadline - _clock()) / 1000)

    def receive(self, deadline: int, maximum: int) -> dict[str, object] | None:
        while True:
            if b"\n" in self.buffer:
                payload, _, rest = self.buffer.partition(b"\n")
                self.buffer = bytearray(rest)
                if len(payload) > maximum:
                    raise ValueError("Control input exceeded its byte budget.")
                return decode_document(bytes(payload))
            if len(self.buffer) > maximum:
                raise ValueError("Control input exceeded its byte budget.")
            readable, _, _ = select.select([self.fd], [], [], max(0, deadline - _clock()) / 1000)
            if not readable:
                return None
            chunk = os.read(self.fd, 65536)
            if not chunk:
                raise EOFError
            self.buffer.extend(chunk)


def _stop_document(value: dict[str, object]) -> tuple[str, int]:
    if (
        set(value) != {"version", "type", "reason", "deadline"}
        or type(value["version"]) is not int
        or value["version"] != 1
        or value["type"] != "stop"
        or value["reason"] not in ("cancel", "timeout", "overflow", "close")
    ):
        raise ValueError("Invalid stop document.")
    return _text(value["reason"]), _integer(value["deadline"])


def main() -> int:
    try:
        control = Control(3)
    except OSError:
        return 2
    target: OwnedTarget | None = None
    request: StartRequest | None = None
    reason = "control-lost"
    deadline = _clock() + 2000
    cancelled = False
    stopping = False

    def interrupt(number: int, frame: object) -> None:
        nonlocal cancelled
        cancelled = True

    try:
        if (
            sys.version_info < (3, 13)
            or os.name != "posix"
            or not all(
                hasattr(os, name)
                for name in ("waitid", "WNOWAIT", "WEXITED", "P_PID", "WNOHANG", "killpg")
            )
            or shutil.which("ps") is None
        ):
            control.send({"type": "refused", "reason": "python-3.13-waitid-ps-required"}, deadline)
            return 2
        signal.signal(signal.SIGCHLD, signal.SIG_DFL)
        signal.signal(signal.SIGINT, interrupt)
        signal.signal(signal.SIGTERM, interrupt)
        control.send(
            {"type": "ready", "clock": _clock(), "python": sys.version.split()[0]}, deadline
        )
        document = control.receive(deadline, 1024 * 1024)
        if document is None:
            raise TimeoutError
        request = parse_start(document)
        if cancelled or _clock() >= min(request.startup_deadline, request.execution_deadline):
            control.send({"type": "refused", "reason": "startup-deadline-expired"}, deadline)
            return 2
        target = OwnedTarget(
            subprocess.Popen(
                request.argv,
                cwd=request.cwd,
                env=request.env,
                stdin=0,
                stdout=1,
                stderr=2,
                close_fds=True,
                start_new_session=True,
            )
        )
        for fd in (0, 1, 2):
            os.close(fd)
        control.send({"type": "started", "pid": target.child.pid}, request.startup_deadline)
        while True:
            document = control.receive(min(request.execution_deadline, _clock() + 10), 16384)
            if document is not None:
                reason, requested_deadline = _stop_document(document)
                deadline = min(requested_deadline, _clock() + request.cleanup_ms)
                stopping = True
                break
            if target.observe():
                reason = "target-exit"
                deadline = _clock() + request.cleanup_ms
                stopping = True
                # Do not wait for a pipe-holding descendant or blocked diagnostics.
                control.send({"type": "exited", "status": target.status}, _clock())
                break
            if cancelled or _clock() >= request.execution_deadline:
                reason = "cancel" if cancelled else "timeout"
                deadline = _clock() + request.cleanup_ms
                stopping = True
                break
    except (OSError, ValueError, EOFError, TimeoutError):
        if target is None:
            with suppress(OSError, ValueError, TimeoutError):
                control.send(
                    {"type": "refused", "reason": "target-start-or-control-failed"}, deadline
                )
            return 2
        target.errors.append("control-or-owner-failed")
        if not stopping:
            deadline = _clock() + (request.cleanup_ms if request else 1000)
    assert target is not None and request is not None
    group = stop_target(target, deadline, request.cleanup_ms, request.mode)
    try:
        control.send(
            {
                "type": "finished",
                "status": target.status,
                "reason": "target-exit" if target.exited_before_signal else reason,
                "leaderReaped": target.reaped,
                "groupState": group,
                "errors": target.errors[:16],
            },
            deadline,
        )
    except (OSError, ValueError, TimeoutError):
        return 1
    finally:
        os.close(control.fd)
    return 0 if not target.errors and group == "quiescent" and target.reaped else 1


if __name__ == "__main__":
    raise SystemExit(main())
