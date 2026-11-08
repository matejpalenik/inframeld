"""Own the private account qualification lifecycle and its phase identities."""

import os
import select
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from types import FrameType


def _has_development_build_space(
    host_available_bytes: int | None, engine_available_bytes: int | None
) -> bool:
    """Require 20 GiB on both filesystems, including the 8 GiB build allowance."""
    minimum_available_bytes = 20 * 1024**3
    return all(
        isinstance(available, int) and available >= minimum_available_bytes
        for available in (host_available_bytes, engine_available_bytes)
    )


@dataclass
class _Phase:
    """Keep the immediate leader waitable until its final possible group signal."""

    child: subprocess.Popen[bytes]
    owned: bool = True
    status: int | None = None
    reaped: bool = False
    errors: list[str] = field(default_factory=list)

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
            self.status = (
                observed.si_status
                if observed.si_code == os.CLD_EXITED
                else 128 + observed.si_status
            )
        return observed is not None

    def signal_group(self, number: signal.Signals) -> bool:
        self.observe()
        if not self.owned:
            return False
        try:
            os.killpg(self.child.pid, number)
        except ProcessLookupError:
            return True
        except OSError:
            self.errors.append("group-signal-failed")
            return False
        return True

    def reap(self) -> bool:
        exited = self.observe()
        self.owned = False
        if not exited:
            return False
        try:
            pid, status = os.waitpid(self.child.pid, os.WNOHANG)
        except OSError:
            self.errors.append("leader-reap-failed")
            return False
        if pid != self.child.pid:
            self.errors.append("leader-reap-unconfirmed")
            return False
        self.child.returncode = os.waitstatus_to_exitcode(status)
        self.reaped = True
        return True


class AccountUIRunner:
    """Run the fixed private account workflow with one bounded finalizer."""

    def __init__(
        self,
        root: Path,
        *,
        directory: Path | None = None,
        cleanup_work_seconds: float = 60,
        term_seconds: float = 5,
        kill_seconds: float = 5,
    ) -> None:
        self.root = root
        self.directory = directory
        self.cleanup_work_seconds = cleanup_work_seconds
        self.term_seconds = term_seconds
        self.kill_seconds = kill_seconds
        self.cancelled = 0
        self.process_cleanup_confirmed = True
        self.volume_baseline_complete = False
        self.qualification_complete = False
        self._unresolved: list[subprocess.Popen[bytes]] = []
        self.runtime = os.environ.get("INFRAMELD_CONTAINER_RUNTIME", "docker")
        self.project = ""
        self.recipient_proof = False

    def _stop_phase(self, phase: _Phase) -> bool:
        """Stop and reconcile only the process group retained by this runner."""
        valid = True
        quiescent = False
        term_deadline = time.monotonic() + self.term_seconds

        def check(deadline: float) -> bool:
            nonlocal valid
            if not phase.observe():
                return False
            try:
                return not self._members(phase, deadline)
            except (TimeoutError, subprocess.TimeoutExpired):
                valid = False
                phase.errors.append("group-observation-timeout")
                return False
            except (OSError, ValueError, subprocess.SubprocessError, ExceptionGroup):
                valid = False
                phase.errors.append("group-observation-failed")
                return False

        quiescent = check(term_deadline)
        for number in (signal.SIGTERM, signal.SIGKILL):
            if quiescent or not phase.owned:
                break
            if not phase.signal_group(number):
                valid = False
            deadline = (
                term_deadline if number == signal.SIGTERM else time.monotonic() + self.kill_seconds
            )
            while phase.owned and time.monotonic() < deadline:
                remaining = deadline - time.monotonic()
                grace = self.term_seconds if number == signal.SIGTERM else self.kill_seconds
                if remaining < min(0.05, grace / 4):
                    # Spend the remaining grace without launching an observation that cannot finish.
                    time.sleep(max(0, remaining))
                    break
                quiescent = check(deadline)
                if quiescent or not valid:
                    break
                time.sleep(min(0.02, max(0, deadline - time.monotonic())))

        reaped = phase.reap()
        if not reaped:
            self._unresolved.append(phase.child)
        confirmed = valid and quiescent and reaped and not phase.errors
        if not confirmed:
            self.process_cleanup_confirmed = False
        return confirmed

    def _members(self, phase: _Phase, deadline: float) -> bool:
        """Observe owned process-group members without adopting an unrelated numeric identity."""
        deadline = min(deadline, time.monotonic() + 1)
        if time.monotonic() >= deadline:
            raise TimeoutError
        observer = subprocess.Popen(
            ["ps", "-axo", "pid=,pgid=,stat="],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        stream = None
        failure: Exception | None = None
        try:
            assert observer.stdout is not None
            stream = observer.stdout
            output = bytearray()
            os.set_blocking(stream.fileno(), False)
            while time.monotonic() < deadline:
                readable, _, _ = select.select(
                    [stream], [], [], max(0, deadline - time.monotonic())
                )
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
            code = observer.wait(timeout=max(0, deadline - time.monotonic()))
            if code != 0:
                raise ValueError("Process observation failed.")
            return _executable_members(bytes(output), phase.child.pid)
        except Exception as error:
            failure = error
            raise
        finally:
            cleanup_errors: list[Exception] = []
            try:
                running = observer.poll() is None
            except (OSError, subprocess.SubprocessError) as error:
                cleanup_errors.append(error)
            else:
                if running:
                    # This immediate child has one waiter. A completed poll forbids later signals.
                    try:
                        observer.kill()
                    except (OSError, subprocess.SubprocessError) as error:
                        cleanup_errors.append(error)
                    try:
                        observer.wait(timeout=max(0, deadline - time.monotonic()))
                    except (OSError, subprocess.SubprocessError) as error:
                        cleanup_errors.append(error)
            if stream is not None:
                try:
                    stream.close()
                except OSError as error:
                    cleanup_errors.append(error)
            if cleanup_errors:
                self.process_cleanup_confirmed = False
                if observer.returncode is None:
                    self._unresolved.append(observer)
                cleanup_error = (
                    cleanup_errors[0]
                    if len(cleanup_errors) == 1
                    else ExceptionGroup("Account observer cleanup failed", cleanup_errors)
                )
                if failure is not None:
                    raise failure from cleanup_error
                raise cleanup_error

    def _interrupt(self, number: int, frame: FrameType | None) -> None:
        if not self.cancelled:
            self.cancelled = 128 + number

    @staticmethod
    def _ignore(number: int, frame: FrameType | None) -> None:
        pass

    def _environment(self) -> dict[str, str]:
        """Give the isolated Compose project its own image and proof-context bindings."""
        assert self.directory is not None
        return {
            **os.environ,
            "INFRAMELD_ACCOUNT_BACKEND_IMAGE": f"localhost/{self.project}-backend:check",
            "INFRAMELD_ACCOUNT_WEB_IMAGE": f"localhost/{self.project}-web:check",
            "INFRAMELD_ACCOUNT_WEB_CONTEXT": str(self.directory / "web-context"),
            "INFRAMELD_ACCOUNT_PROOF_IMAGE": f"localhost/{self.project}-proof:check",
            "INFRAMELD_ACCOUNT_PROOF_CONTEXT": str(self.directory / "proof-context"),
            "INFRAMELD_ACCOUNT_PROOF_MODE": "1" if self.recipient_proof else "0",
        }

    def _run_phase(
        self,
        name: str,
        arguments: list[str],
        work_seconds: float,
        *,
        cleanup: bool = False,
    ) -> int:
        """Bound one owned command while preserving its original failure and cleanup result."""
        if self.cancelled and not cleanup:
            return self.cancelled
        deadline = time.monotonic() + work_seconds
        output = None
        try:
            if cleanup:
                assert self.directory is not None
                output = (self.directory / "cleanup.log").open("wb")
            child = subprocess.Popen(
                arguments,
                cwd=self.root,
                env=self._environment(),
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=subprocess.STDOUT if cleanup else None,
                start_new_session=True,
            )
        except OSError:
            if output is not None:
                output.close()
            print("Unable to start the account qualification phase.", file=sys.stderr)
            return 1
        phase = _Phase(child)
        timed_out = False
        try:
            while not phase.observe() and phase.owned:
                if self.cancelled and not cleanup:
                    break
                if time.monotonic() >= deadline:
                    timed_out = True
                    label = "cleanup" if cleanup else "qualification phase"
                    print(
                        f"Account {label} exceeded its {work_seconds:g}-second work budget.",
                        file=sys.stderr,
                    )
                    break
                time.sleep(0.02)
            stopped = self._stop_phase(phase)
            if not stopped:
                reasons = ",".join(dict.fromkeys(phase.errors)) or "group-or-reap-unconfirmed"
                print(
                    f"Account {name} process shutdown is unconfirmed ({reasons}). Cleanup may be incomplete.",
                    file=sys.stderr,
                )
            if timed_out:
                return 1 if cleanup else 124
            status = self.cancelled if self.cancelled and not cleanup else phase.status
            return status if status else (0 if stopped and status == 0 else 1)
        finally:
            if output is not None:
                output.close()

    def _shell(self, name: str) -> list[str]:
        """Run a shell phase under the same process ownership and deadline rules."""
        if name not in {
            "runtime_preflight",
            "startup_stack",
            "cleanup_stack",
            "recipient_proof_stack",
            "prepare_contexts",
            "build_stack",
            "account_browser_stack",
        }:
            raise ValueError("Unknown private account phase.")
        assert self.directory is not None
        program = """source "$1"
set -euo pipefail
set +m
account_directory="$2"
account_project="$3"
account_runtime="$4"
account_compose_file="$5"
volume_baseline_complete="$6"
account_python="$8"
account_root="$9"
account_compose=("$account_runtime" compose -p "$account_project" -f "$account_compose_file")
"$7"
"""
        return [
            "bash",
            "-c",
            program,
            "account-phase",
            str(self.root / "scripts/test-account-ui.sh"),
            str(self.directory),
            self.project,
            self.runtime,
            str(self.root / "compose.account-ui.test.yaml"),
            str(self.volume_baseline_complete).lower(),
            name,
            sys.executable,
            str(self.root),
        ]

    def _work(self) -> int:
        """Run the selected account journey while retaining the owner needed for cleanup."""
        assert self.directory is not None
        commands = [
            (
                "prepare",
                self._shell("prepare_contexts")
                if self.recipient_proof
                else [
                    sys.executable,
                    str(self.root / "apps/web/tests/fixtures/prepare_build_context.py"),
                    str(self.root),
                    str(self.directory / "web-context"),
                    "--invitation-guide",
                ],
                30,
            ),
            ("preflight", self._shell("runtime_preflight"), 30),
            ("compose-version", [self.runtime, "compose", "version"], 30),
            (
                "build",
                self._shell("build_stack")
                if self.recipient_proof
                else [
                    self.runtime,
                    "compose",
                    "-p",
                    self.project,
                    "-f",
                    str(self.root / "compose.account-ui.test.yaml"),
                    "build",
                    "backend",
                    "web",
                ],
                600,
            ),
            ("startup", self._shell("startup_stack"), 180),
            (
                "browser",
                self._shell("recipient_proof_stack")
                if self.recipient_proof
                else self._shell("account_browser_stack"),
                300,
            ),
        ]
        for name, arguments, seconds in commands:
            status = self._run_phase(name, arguments, seconds)
            if status:
                return status
            if name == "preflight":
                self.volume_baseline_complete = True
        self.qualification_complete = True
        return 0

    def _write_context(self, cleanup_state: str) -> None:
        """Prepare the isolated build context without modifying the ordinary application checkout."""
        assert self.directory is not None
        environment = self._environment()
        values = {
            "project": self.project,
            "runtime": self.runtime,
            "compose_file": str(self.root / "compose.account-ui.test.yaml"),
            "backend_image": environment["INFRAMELD_ACCOUNT_BACKEND_IMAGE"],
            "web_image": environment["INFRAMELD_ACCOUNT_WEB_IMAGE"],
            "web_context": environment["INFRAMELD_ACCOUNT_WEB_CONTEXT"],
            "volume_baseline_complete": str(self.volume_baseline_complete).lower(),
            "cleanup": cleanup_state,
        }
        if self.recipient_proof:
            values.update(
                proof_image=environment["INFRAMELD_ACCOUNT_PROOF_IMAGE"],
                proof_context=environment["INFRAMELD_ACCOUNT_PROOF_CONTEXT"],
            )
        (self.directory / "context.txt").write_text(
            "".join(f"{key}={value}\n" for key, value in values.items())
        )

    def run(self, arguments: list[str]) -> int:
        if arguments not in (["--login-only"], ["--recipient-proof"]):
            print(
                "Usage: scripts/test-account-ui.sh --login-only | --recipient-proof",
                file=sys.stderr,
            )
            return 2
        self.recipient_proof = arguments == ["--recipient-proof"]
        supported = sys.version_info >= (3, 13) and all(
            hasattr(os, name)
            for name in ("waitid", "WNOWAIT", "P_PID", "WEXITED", "WNOHANG", "killpg")
        )
        if (
            not supported
            or not shutil.which("ps")
            or self.runtime not in {"docker", "podman"}
            or not shutil.which(self.runtime)
        ):
            print(
                "Use the pinned Python 3.13 waitid/WNOWAIT toolchain, ps and docker or podman.",
                file=sys.stderr,
            )
            return 2
        previous = {
            number: signal.getsignal(number)
            for number in (signal.SIGCHLD, signal.SIGINT, signal.SIGTERM)
        }
        previous_umask = os.umask(0o077)
        signal.signal(signal.SIGCHLD, signal.SIG_DFL)
        signal.signal(signal.SIGINT, self._interrupt)
        signal.signal(signal.SIGTERM, self._interrupt)
        status = 1
        try:
            if self.directory is None:
                self.directory = Path(tempfile.mkdtemp(prefix="inframeld-account-ui-"))
            else:
                self.directory.mkdir(mode=0o700)
            self.project = self.directory.name.lower().replace("_", "-")
            try:
                self._write_context("incomplete")
                status = self._work()
            except OSError:
                print(
                    "Account qualification could not complete its private file operation.",
                    file=sys.stderr,
                )
                status = status or 1
            finally:
                signal.signal(signal.SIGINT, self._ignore)
                signal.signal(signal.SIGTERM, self._ignore)
                cleanup_state = "incomplete"
                if (
                    self._run_phase(
                        "cleanup",
                        self._shell("cleanup_stack"),
                        self.cleanup_work_seconds,
                        cleanup=True,
                    )
                    == 0
                    and self.process_cleanup_confirmed
                ):
                    cleanup_state = "confirmed"
                else:
                    status = status or 1
                    print(
                        f"Account fixture cleanup is incomplete. Resources may remain for project: {self.project}",
                        file=sys.stderr,
                    )
                try:
                    self._write_context(cleanup_state)
                except OSError:
                    status = status or 1
                if not self.qualification_complete:
                    status = status or 1
                if status == 0:
                    try:
                        shutil.rmtree(self.directory)
                    except OSError:
                        status = 1
                    else:
                        print(
                            "Native recipient-proof checks passed. Cleanup confirmed."
                            if self.recipient_proof
                            else "Native account navigation checks passed. Cleanup confirmed. "
                            "Combined Rust recipient-proof qualification is still pending."
                        )
                if status:
                    print(
                        f"Account qualification exited {status}. Cleanup {cleanup_state}. "
                        f"Private diagnostics: {self.directory}",
                        file=sys.stderr,
                    )
        finally:
            os.umask(previous_umask)
            for number, handler in previous.items():
                signal.signal(number, handler)
        return status


def _executable_members(payload: bytes, group: int) -> bool:
    """Identify executable group members separately from exited processes awaiting reaping."""
    if not payload.strip():
        raise ValueError("Missing process observation.")
    running = False
    for line in payload.decode("ascii", errors="strict").splitlines():
        fields = line.split()
        if len(fields) != 3:
            raise ValueError("Incomplete process observation.")
        pid, pgid = int(fields[0]), int(fields[1])
        if pid < 0 or pgid < 0:
            raise ValueError("Invalid process observation.")
        if pgid == group and not fields[2].startswith("Z"):
            running = True
    return running


if __name__ == "__main__":
    raise SystemExit(AccountUIRunner(Path(__file__).resolve().parents[1]).run(sys.argv[1:]))
