"""Check retained ownership with syscall controls and finite private children."""

import json
import os
import runpy
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import Mock, patch

from run_account_ui import AccountUIRunner, _executable_members, _Phase


class RetainedOwnershipTests(unittest.TestCase):
    def phase(self) -> _Phase:
        return _Phase(cast("subprocess.Popen[bytes]", SimpleNamespace(pid=123, returncode=None)))

    def exited(self) -> SimpleNamespace:
        return SimpleNamespace(si_pid=123, si_code=os.CLD_EXITED, si_status=7)

    def test_owned_signal_observes_before_signalling(self) -> None:
        phase = self.phase()
        calls: list[str] = []
        with (
            patch("os.waitid", side_effect=lambda *_: calls.append("observe")),
            patch("os.killpg", side_effect=lambda *_: calls.append("signal")),
        ):
            self.assertTrue(phase.signal_group(signal.SIGTERM))
        self.assertEqual(calls, ["observe", "signal"])

    def test_natural_exit_retains_leader_and_status(self) -> None:
        phase = self.phase()
        with (
            patch("os.waitid", return_value=self.exited()) as observe,
            patch("os.waitpid") as reap,
        ):
            self.assertTrue(phase.observe())
        observe.assert_called_once_with(os.P_PID, 123, os.WEXITED | os.WNOHANG | os.WNOWAIT)
        reap.assert_not_called()
        self.assertEqual(phase.status, 7)
        self.assertTrue(phase.owned)

    def test_wait_loss_revokes_all_later_signals(self) -> None:
        phase = self.phase()
        with (
            patch("os.waitid", side_effect=ChildProcessError) as observe,
            patch("os.killpg") as send,
        ):
            self.assertFalse(phase.signal_group(signal.SIGTERM))
            self.assertFalse(phase.signal_group(signal.SIGKILL))
        observe.assert_called_once()
        self.assertFalse(phase.owned)
        self.assertIn("wait-ownership-lost", phase.errors)
        send.assert_not_called()

    def test_reap_revokes_before_consuming_status(self) -> None:
        phase = self.phase()

        def consume(pid: int, flags: int) -> tuple[int, int]:
            self.assertFalse(phase.owned)
            return pid, 7 << 8

        with (
            patch("os.waitid", return_value=self.exited()),
            patch("os.waitpid", side_effect=consume),
        ):
            self.assertTrue(phase.reap())
        self.assertEqual(phase.child.returncode, 7)
        self.assertTrue(phase.reaped)

    def test_reaped_phase_cannot_signal_or_reap_again(self) -> None:
        phase = self.phase()
        with (
            patch("os.waitid", return_value=self.exited()),
            patch("os.waitpid", return_value=(123, 7 << 8)) as consume,
            patch("os.killpg") as send,
        ):
            self.assertTrue(phase.reap())
            self.assertFalse(phase.signal_group(signal.SIGKILL))
            self.assertFalse(phase.reap())
        consume.assert_called_once()
        self.assertFalse(phase.owned)
        send.assert_not_called()

    def test_denied_signal_is_a_failure(self) -> None:
        phase = self.phase()
        with (
            patch("os.waitid", return_value=None),
            patch("os.killpg", side_effect=PermissionError),
        ):
            self.assertFalse(phase.signal_group(signal.SIGTERM))
        self.assertIn("group-signal-failed", phase.errors)

    def test_loss_after_term_revokes_kill_escalation(self) -> None:
        phase = self.phase()
        runner = AccountUIRunner(Path("/unused"), term_seconds=0.1, kill_seconds=0.1)
        with (
            patch("os.waitid", side_effect=[None, None, ChildProcessError]),
            patch("os.killpg") as send,
        ):
            self.assertFalse(runner._stop_phase(phase))
        self.assertEqual([call.args[1] for call in send.call_args_list], [signal.SIGTERM])
        self.assertFalse(phase.owned)
        self.assertFalse(runner.process_cleanup_confirmed)

    def test_actual_reaped_child_cannot_be_adopted_from_its_number(self) -> None:
        child = subprocess.Popen(
            [sys.executable, "-c", "raise SystemExit(0)"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.assertEqual(child.wait(timeout=1), 0)
        phase = _Phase(child)
        with patch("os.killpg") as send:
            self.assertFalse(phase.signal_group(signal.SIGTERM))
            self.assertFalse(phase.signal_group(signal.SIGKILL))
        send.assert_not_called()
        self.assertIn("wait-ownership-lost", phase.errors)


class PhaseCompletionTests(unittest.TestCase):
    def runner(self) -> AccountUIRunner:
        return AccountUIRunner(Path("/unused"), term_seconds=0.1, kill_seconds=0.1)

    def exited_phase(self) -> _Phase:
        return RetainedOwnershipTests().phase()

    def test_quiescent_natural_exit_reaps_without_group_signal(self) -> None:
        phase = self.exited_phase()
        runner = self.runner()
        with (
            patch("os.waitid", return_value=RetainedOwnershipTests().exited()),
            patch("os.waitpid", return_value=(123, 7 << 8)),
            patch("os.killpg") as send,
            patch.object(runner, "_members", return_value=False),
        ):
            self.assertTrue(runner._stop_phase(phase))
        send.assert_not_called()
        self.assertFalse(phase.owned)
        self.assertTrue(phase.reaped)
        self.assertEqual(phase.status, 7)

    def test_surviving_descendant_is_signalled_before_leader_reap(self) -> None:
        phase = self.exited_phase()
        runner = self.runner()
        calls: list[str] = []

        def send(*_arguments: object) -> None:
            self.assertTrue(phase.owned)
            self.assertFalse(phase.reaped)
            calls.append("signal")

        def consume(pid: int, flags: int) -> tuple[int, int]:
            self.assertFalse(phase.owned)
            calls.append("reap")
            return pid, 7 << 8

        with (
            patch("os.waitid", return_value=RetainedOwnershipTests().exited()),
            patch("os.waitpid", side_effect=consume),
            patch("os.killpg", side_effect=send),
            patch.object(runner, "_members", side_effect=[True, False]),
        ):
            self.assertTrue(runner._stop_phase(phase))
        self.assertEqual(calls, ["signal", "reap"])

    def test_observation_failure_cannot_become_confirmed_cleanup(self) -> None:
        phase = self.exited_phase()
        runner = self.runner()
        with (
            patch("os.waitid", return_value=RetainedOwnershipTests().exited()),
            patch("os.waitpid", return_value=(123, 7 << 8)),
            patch("os.killpg"),
            patch.object(runner, "_members", side_effect=ValueError("controlled malformed ps")),
        ):
            self.assertFalse(runner._stop_phase(phase))
        self.assertFalse(phase.owned)
        self.assertTrue(phase.reaped)
        self.assertFalse(runner.process_cleanup_confirmed)

    def test_lost_identity_stops_escalation_and_never_confirms_cleanup(self) -> None:
        phase = self.exited_phase()
        runner = self.runner()
        with (
            patch("os.waitid", side_effect=ChildProcessError),
            patch("os.killpg") as send,
        ):
            self.assertFalse(runner._stop_phase(phase))
        send.assert_not_called()
        self.assertFalse(phase.owned)
        self.assertFalse(runner.process_cleanup_confirmed)

    def test_grace_exhaustion_escalates_without_starting_a_late_observer(self) -> None:
        runner = self.runner()
        phase = self.exited_phase()
        clock = [0.0]
        observations = [0]

        def members(_phase: _Phase, deadline: float) -> bool:
            observations[0] += 1
            if observations[0] == 1:
                clock[0] = 0.095
                return True
            if deadline - clock[0] < 0.02:
                raise TimeoutError("A new observer cannot finish in the expiring TERM grace")
            return False

        with (
            patch("time.monotonic", side_effect=lambda: clock[0]),
            patch(
                "time.sleep",
                side_effect=lambda seconds: clock.__setitem__(0, clock[0] + seconds),
            ),
            patch("os.waitid", return_value=RetainedOwnershipTests().exited()),
            patch("os.waitpid", return_value=(123, 7 << 8)),
            patch("os.killpg") as send,
            patch.object(runner, "_members", side_effect=members),
        ):
            self.assertTrue(runner._stop_phase(phase))
        self.assertEqual(
            [call.args[1] for call in send.call_args_list],
            [signal.SIGTERM, signal.SIGKILL],
        )
        self.assertEqual(observations[0], 2)

    def test_cancellation_during_spawn_attaches_child_before_stopping(self) -> None:
        runner = self.runner()
        runner.directory = Path("/unused")
        child = self.exited_phase().child

        def spawn(*_arguments: object, **_options: object):
            runner._interrupt(signal.SIGTERM, None)
            return child

        def stop(phase: _Phase) -> bool:
            self.assertIs(phase.child, child)
            phase.status = 143
            phase.owned = False
            phase.reaped = True
            return True

        with (
            patch("subprocess.Popen", side_effect=spawn),
            patch("os.waitid", return_value=None),
            patch.object(runner, "_stop_phase", side_effect=stop) as stopped,
        ):
            self.assertEqual(runner._run_phase("controlled", ["unused"], 1), 143)
        stopped.assert_called_once()

    def test_parent_finalizer_shield_does_not_make_execed_child_ignore_term(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(prefix="account-default-term-") as name:
            runner = AccountUIRunner(
                Path(name), directory=Path(name), term_seconds=0.2, kill_seconds=0.2
            )
            previous = signal.getsignal(signal.SIGTERM)
            signals: list[signal.Signals] = []
            original = os.killpg

            def send(group: int, number: signal.Signals) -> None:
                signals.append(number)
                original(group, number)

            signal.signal(signal.SIGTERM, runner._ignore)
            try:
                with patch("os.killpg", side_effect=send):
                    status = runner._run_phase(
                        "cleanup",
                        [sys.executable, "-c", "import time; time.sleep(30)"],
                        0.1,
                        cleanup=True,
                    )
            finally:
                signal.signal(signal.SIGTERM, previous)
        self.assertEqual(status, 1)
        self.assertEqual(signals, [signal.SIGTERM])
        self.assertTrue(runner.process_cleanup_confirmed)


class GroupObservationTests(unittest.TestCase):
    def test_closed_stdio_descendant_remains_an_executable_member(self) -> None:
        self.assertTrue(_executable_members(b"123 123 Z\n124 123 S\n", 123))

    def test_zombie_only_group_is_quiescent(self) -> None:
        self.assertFalse(_executable_members(b"123 123 Z\n124 999 S\n", 123))

    def test_missing_or_malformed_observation_is_not_quiescence(self) -> None:
        for payload in (b"", b"incomplete\n", b"x 123 S\n", b"123 123 \xff\n"):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                _executable_members(payload, 123)


class BoundedObservationTests(unittest.TestCase):
    def sample(self, chunks: list[bytes], *, code: int = 0, ready: bool = True) -> bool:
        child = Mock()
        child.stdout.fileno.return_value = 42
        child.wait.return_value = code
        child.poll.return_value = code
        phase = RetainedOwnershipTests().phase()
        runner = AccountUIRunner(Path("/unused"))
        with (
            patch("subprocess.Popen", return_value=child),
            patch("os.set_blocking"),
            patch("os.read", side_effect=chunks),
            patch(
                "select.select",
                return_value=([child.stdout], [], []) if ready else ([], [], []),
            ),
        ):
            return runner._members(phase, time.monotonic() + 1)

    def test_complete_zombie_only_observation_is_quiescent(self) -> None:
        self.assertFalse(self.sample([b"123 123 Z\n", b""]))

    def test_incomplete_or_nonzero_observation_is_unknown(self) -> None:
        for chunks, code in (
            ([b""], 0),
            ([b"broken\n", b""], 0),
            ([b"123 123 Z\n", b""], 3),
        ):
            with self.subTest(chunks=chunks), self.assertRaises(ValueError):
                self.sample(chunks, code=code)

    def test_observation_capture_cannot_exceed_four_mib(self) -> None:
        with self.assertRaises(ValueError):
            self.sample([b"x" * (4 * 1024 * 1024 + 1)])

    def test_blocked_observation_has_no_extra_deadline(self) -> None:
        with self.assertRaises(TimeoutError):
            self.sample([], ready=False)


class ObserverSetupTests(unittest.TestCase):
    def probe(self, *, setup_failure: bool, cleanup_failure: bool = False) -> None:
        with tempfile.TemporaryDirectory(prefix="account-observer-setup-") as name:
            directory = Path(name)
            fuse = directory / "fuse-fired"
            code = (
                "import time; from pathlib import Path; time.sleep(3); "
                f"Path({str(fuse)!r}).write_text('expired')"
                if setup_failure
                else "print('123 123 Z')"
            )
            child = subprocess.Popen(
                [sys.executable, "-c", code],
                cwd=directory,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            runner = AccountUIRunner(directory)
            phase = RetainedOwnershipTests().phase()
            primary = OSError("controlled observer setup failure")
            cleanup = OSError("controlled observer cleanup failure")
            original_kill = child.kill

            def kill() -> None:
                original_kill()
                if cleanup_failure:
                    raise cleanup

            try:
                with (
                    patch("subprocess.Popen", return_value=child),
                    patch.object(child, "kill", side_effect=kill) as stopped,
                ):
                    if setup_failure:
                        with (
                            patch("os.set_blocking", side_effect=primary),
                            self.assertRaises(OSError) as caught,
                        ):
                            runner._members(phase, time.monotonic() + 1)
                        self.assertIs(caught.exception, primary)
                        self.assertIsNotNone(
                            child.returncode,
                            "Setup failure left an admitted observer unreaped",
                        )
                        stopped.assert_called_once()
                        if cleanup_failure:
                            self.assertIs(caught.exception.__cause__, cleanup)
                            self.assertFalse(runner.process_cleanup_confirmed)
                    else:
                        self.assertFalse(runner._members(phase, time.monotonic() + 1))
                        self.assertEqual(child.returncode, 0)
                        stopped.assert_not_called()
                self.assertTrue(child.stdout is not None and child.stdout.closed)
                self.assertFalse(fuse.exists(), "Fixture self-expiry cannot prove owner cleanup")
            finally:
                # The test retains this immediate child handle. No recorded number is adopted.
                if child.returncode is None:
                    original_kill()
                    child.wait(timeout=1)
                if child.stdout is not None:
                    child.stdout.close()

    def test_owned_observer_positive_control(self) -> None:
        self.probe(setup_failure=False)

    def test_actual_setup_oserror_stops_and_reaps_observer_before_fuse(self) -> None:
        self.probe(setup_failure=True)

    def test_setup_error_and_cleanup_error_are_both_preserved(self) -> None:
        self.probe(setup_failure=True, cleanup_failure=True)


class ReapedChildPortabilityTests(unittest.TestCase):
    def check_override(self, *, missing: bool) -> None:
        with (
            tempfile.TemporaryDirectory(prefix="account-portable-reap-") as name,
            patch.dict(os.environ),
        ):
            if missing:
                override = Path(name) / "not-created"
                self.assertFalse(override.exists())
                os.environ["TMPDIR"] = str(override)
            else:
                os.environ.pop("TMPDIR", None)
            try:
                RetainedOwnershipTests().test_actual_reaped_child_cannot_be_adopted_from_its_number()
            except OSError as error:
                self.fail(
                    f"An irrelevant TMPDIR prevented the ownership assertions: {type(error).__name__}"
                )

    def test_missing_tmpdir_override_does_not_choose_child_cwd(self) -> None:
        self.check_override(missing=True)

    def test_absent_tmpdir_does_not_choose_child_cwd(self) -> None:
        self.check_override(missing=False)


class ProofInputTests(unittest.TestCase):
    def test_denial_requires_the_exact_complete_production_error(self):
        validator = self.functions()["validate_denied_result"]
        denied = {
            "schemaVersion": 1,
            "error": {
                "kind": "denied",
                "resourceCleanup": "not-needed",
                "credentialCleanup": "not-needed",
            },
        }
        self.assertIsNone(validator(json.dumps(denied).encode()))
        for key, value in [
            ("kind", "exchange"),
            ("resourceCleanup", "unconfirmed"),
            ("credentialCleanup", "confirmed"),
        ]:
            changed = json.loads(json.dumps(denied))
            changed["error"][key] = value
            with self.assertRaises(ValueError):
                validator(json.dumps(changed).encode())
        for raw in [
            b'{"schemaVersion":1,"error":{"kind":"denied"}}',
            json.dumps(denied).encode() + b"{}",
            b"x" * 65_537,
            b'{"schemaVersion":1,"schemaVersion":1,"error":{"kind":"denied","resourceCleanup":"not-needed","credentialCleanup":"not-needed"}}',
        ]:
            with self.assertRaises(ValueError):
                validator(raw)

    def functions(self):
        return runpy.run_path(
            str(Path(__file__).resolve().parents[1] / "apps/web/tests/fixtures/backend.py")
        )

    def intent(self):
        return {
            "schemaVersion": 1,
            "mode": "repair-stranded-authority",
            "expectedInstallationId": "00000000-0000-0000-0000-000000000001",
            "operationId": "native-recipient-proof",
            "operatorLabel": "Private native fixture",
            "reason": "Restore reviewed metadata authority",
            "expectedAccessRevision": 0,
            "expectedIdentityId": "00000000-0000-0000-0000-000000000002",
            "responsibility": {
                "kind": "action-grantor",
                "target": {
                    "kind": "project",
                    "projectId": "00000000-0000-0000-0000-000000000003",
                },
                "actionId": "edit-project-metadata",
            },
        }

    def result(self):
        request = self.intent()
        receipt = {
            "schemaVersion": 1,
            "mode": request["mode"],
            "operationId": request["operationId"],
            "installationId": request["expectedInstallationId"],
            "principalId": "00000000-0000-0000-0000-000000000004",
            "accessRevision": 1,
            "outcome": "repaired",
            "responsibility": request["responsibility"],
        }
        return {
            "schemaVersion": 1,
            "result": {
                "maintenance": {
                    "effect": {"status": "committed", "receipt": receipt},
                    "processCleanup": "confirmed",
                    "failure": None,
                },
                "credentialCleanup": "confirmed",
            },
        }

    def test_private_inputs_are_proof_free_and_retain_exact_reviewed_intent(self):
        from uuid import UUID

        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "driver-private"
            self.functions()["write_proof_inputs"](
                directory,
                installation_id=UUID(int=1),
                identity_id=UUID(int=2),
                principal_id=UUID(int=4),
                project_id=UUID(int=3),
                certificate_authority="public-fixture-ca",
                environment={"INFRAMELD_DATABASE__PASSWORD": "private-fixture-password"},
            )
            self.assertTrue((directory / "request.json").is_file())
            self.assertEqual(json.loads((directory / "request.json").read_text()), self.intent())
            self.assertEqual(directory.stat().st_mode & 0o777, 0o700)
            for item in directory.iterdir():
                self.assertEqual(item.stat().st_mode & 0o777, 0o600)
                self.assertNotIn("identityProof", item.read_text())
            self.assertNotIn("private-fixture-password", (directory / "host.json").read_text())

    def test_only_original_bound_receipt_with_both_cleanup_facts_can_pass(self):
        from uuid import UUID

        result = self.result()
        validator = self.functions()["validate_proof_result"]
        self.assertEqual(
            validator(json.dumps(result).encode(), self.intent(), UUID(int=4)),
            result["result"]["maintenance"]["effect"]["receipt"],
        )
        for field, value in [
            ("operationId", "replacement"),
            ("accessRevision", 2),
            ("mode", "bootstrap-first-administrator"),
            ("principalId", str(UUID(int=99))),
        ]:
            changed = self.result()
            changed["result"]["maintenance"]["effect"]["receipt"][field] = value
            with self.assertRaises(ValueError):
                validator(json.dumps(changed).encode(), self.intent(), UUID(int=4))
        for field in ["processCleanup", "credentialCleanup"]:
            changed = self.result()
            target = (
                changed["result"]["maintenance"] if field == "processCleanup" else changed["result"]
            )
            target[field] = "unconfirmed"
            with self.assertRaises(ValueError):
                validator(json.dumps(changed).encode(), self.intent(), UUID(int=4))
        changed = self.result()
        changed["accessToken"] = "synthetic-secret"
        with self.assertRaises(ValueError):
            validator(json.dumps(changed).encode(), self.intent(), UUID(int=4))


if __name__ == "__main__":
    unittest.main()
