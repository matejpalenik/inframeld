"""Run the serial private integration lifecycle while retaining phase-process ownership."""

import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from types import FrameType


@dataclass
class _Phase:
    """Retain the immediate leader until the final possible signal to its process group."""

    child: subprocess.Popen[bytes]
    owned: bool = True
    status: int | None = None

    def observe(self) -> bool:
        if not self.owned:
            return False
        try:
            observed = os.waitid(os.P_PID, self.child.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
        except OSError:
            self.owned = False
            self.child.returncode = 1
            return False
        if observed is not None:
            self.status = (
                observed.si_status
                if observed.si_code == os.CLD_EXITED
                else 128 + observed.si_status
            )
        return observed is not None


class IntegrationRunner:
    """Own the fixed dev-compose startup, test and single cleanup sequence."""

    def __init__(
        self,
        repository_root: Path,
        *,
        cleanup_work_seconds: float = 60,
        term_seconds: float = 5,
        kill_seconds: float = 5,
    ) -> None:
        self._root = repository_root
        self._cleanup_work_seconds = cleanup_work_seconds
        self._term_seconds = term_seconds
        self._kill_seconds = kill_seconds
        self._cancelled = 0
        self._unresolved: list[_Phase] = []

    def _interrupt(self, number: int, frame: FrameType | None) -> None:
        if not self._cancelled:
            self._cancelled = 128 + number

    @staticmethod
    def _ignore(number: int, frame: FrameType | None) -> None:
        pass

    def run(self, selectors: list[str]) -> int:
        if sys.version_info < (3, 13) or not all(
            hasattr(os, name) for name in ("waitid", "WNOWAIT", "P_PID", "WEXITED", "WNOHANG")
        ):
            print(
                "Integration wrapper requires waitid/WNOWAIT. Use the repository Python 3.13 "
                "toolchain with mise exec -- pnpm test:integration.",
                file=sys.stderr,
            )
            return 2

        previous = {
            number: signal.getsignal(number)
            for number in (signal.SIGCHLD, signal.SIGINT, signal.SIGTERM)
        }
        signal.signal(signal.SIGCHLD, signal.SIG_DFL)
        signal.signal(signal.SIGINT, self._interrupt)
        signal.signal(signal.SIGTERM, self._interrupt)
        attempted = False
        status = 0
        try:
            if not self._cancelled:
                attempted = True
                status = self._run_phase("test-services-up", [])
            if status == 0 and not self._cancelled:
                status = self._run_phase("test-run", selectors)
            if status == 0 and self._cancelled:
                status = self._cancelled
        finally:
            # Caught Python handlers become defaults on exec, unlike SIG_IGN.
            signal.signal(signal.SIGINT, self._ignore)
            signal.signal(signal.SIGTERM, self._ignore)
            try:
                if attempted and self._run_phase("test-services-down", [], cleanup=True) != 0:
                    print(
                        "Integration cleanup failed. Run ./scripts/dev-compose.sh "
                        "test-services-down to retry. Cleanup may be incomplete.",
                        file=sys.stderr,
                    )
                    if status == 0:
                        status = 1
            finally:
                for number, handler in previous.items():
                    signal.signal(number, handler)
        return status

    def _run_phase(self, name: str, arguments: list[str], *, cleanup: bool = False) -> int:
        if not cleanup and self._cancelled:
            return self._cancelled
        deadline = time.monotonic() + self._cleanup_work_seconds if cleanup else None
        try:
            child = subprocess.Popen(
                [str(self._root / "scripts/dev-compose.sh"), name, *arguments],
                cwd=self._root,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError:
            print("Unable to start the integration phase.", file=sys.stderr)
            return 1
        phase = _Phase(child)
        timed_out = False
        while not phase.observe() and phase.owned:
            if not cleanup and self._cancelled:
                break
            if deadline is not None and time.monotonic() >= deadline:
                timed_out = True
                print(
                    "Integration cleanup exceeded its work budget. Cleanup may be incomplete.",
                    file=sys.stderr,
                )
                break
            time.sleep(0.02)
        stopped = self._stop_phase(phase)
        status = self._cancelled if not cleanup and self._cancelled else phase.status
        if timed_out or not stopped:
            return status if status else 1
        return status if status is not None else 1

    @staticmethod
    def _signal_group(phase: _Phase, number: signal.Signals) -> bool:
        phase.observe()
        if not phase.owned:
            return False
        try:
            os.killpg(phase.child.pid, number)
        except ProcessLookupError:
            # A group with no executable member may already be absent.
            return True
        except OSError:
            return False
        return True

    @staticmethod
    def _running_members(phase: _Phase, deadline: float) -> bool:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError
        result = subprocess.run(
            ["ps", "-axo", "pid=,pgid=,stat="],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=remaining,
            check=True,
        )
        running = False
        for line in result.stdout.splitlines():
            columns = line.split()
            if len(columns) != 3:
                raise ValueError("Incomplete process-state observation.")
            _, group, state = columns
            if int(group) == phase.child.pid and not state.startswith("Z"):
                running = True
        return running

    def _stop_phase(self, phase: _Phase) -> bool:
        valid = True
        quiescent = False
        term_deadline = time.monotonic() + self._term_seconds
        if phase.observe():
            try:
                quiescent = not self._running_members(phase, term_deadline)
            except (OSError, ValueError, subprocess.SubprocessError, TimeoutError):
                valid = False
        for number in (signal.SIGTERM, signal.SIGKILL):
            if quiescent:
                break
            if not self._signal_group(phase, number):
                valid = False
            if not phase.owned:
                break
            deadline = (
                term_deadline if number == signal.SIGTERM else time.monotonic() + self._kill_seconds
            )
            while time.monotonic() < deadline:
                exited = phase.observe()
                if not phase.owned:
                    break
                try:
                    running = self._running_members(phase, deadline)
                except (OSError, ValueError, subprocess.SubprocessError, TimeoutError):
                    valid = False
                    break
                if exited and not running:
                    quiescent = True
                    break
                time.sleep(min(0.02, max(0, deadline - time.monotonic())))
            if quiescent or not phase.owned:
                break

        # No group signal is permitted from this point onward, even on failure.
        reaped = self._reap(phase)
        if not reaped:
            self._unresolved.append(phase)
        if not valid or not quiescent or not reaped:
            print(
                "Integration process shutdown could not be confirmed. Cleanup may be incomplete.",
                file=sys.stderr,
            )
            return False
        return True

    @staticmethod
    def _reap(phase: _Phase) -> bool:
        if not phase.observe() or not phase.owned:
            return False
        phase.owned = False
        try:
            pid, status = os.waitpid(phase.child.pid, os.WNOHANG)
        except OSError:
            phase.child.returncode = 1
            return False
        if pid != phase.child.pid:
            return False
        phase.child.returncode = os.waitstatus_to_exitcode(status)
        return True


if __name__ == "__main__":
    raise SystemExit(IntegrationRunner(Path(__file__).resolve().parents[4]).run(sys.argv[1:]))
