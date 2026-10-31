"""Prove wait ownership at a syscall boundary without real process signals."""

import signal
import subprocess
import unittest
from types import SimpleNamespace
from typing import cast
from unittest.mock import ANY, Mock, call, patch

from src.system.process_owner import (
    Control,
    OwnedTarget,
    decode_document,
    executable_members,
    main,
    parse_start,
    stop_target,
)


class RetainedOwnershipTests(unittest.TestCase):
    def target(self, *, owned: bool = True) -> OwnedTarget:
        child = cast("subprocess.Popen[bytes]", SimpleNamespace(pid=123))
        return OwnedTarget(child, owned=owned)

    def test_owned_target_observes_before_signalling(self) -> None:
        target = self.target()
        calls: list[str] = []

        def observe(*_arguments: object) -> None:
            calls.append("observe")

        def send(*_arguments: object) -> None:
            calls.append("signal")

        with (
            patch("os.waitid", side_effect=observe),
            patch("os.killpg", side_effect=send),
        ):
            self.assertTrue(target.signal_group(signal.SIGTERM))

        self.assertEqual(calls, ["observe", "signal"])

    def test_reaped_or_lost_target_never_signals(self) -> None:
        target = self.target(owned=False)
        with patch("os.waitid") as observe, patch("os.killpg") as send:
            self.assertFalse(target.signal_group(signal.SIGKILL))

        observe.assert_not_called()
        send.assert_not_called()

    def test_wait_ownership_loss_disables_later_signals(self) -> None:
        target = self.target()
        with (
            patch("os.waitid", side_effect=ChildProcessError),
            patch("os.killpg") as send,
        ):
            self.assertFalse(target.signal_group(signal.SIGTERM))
            self.assertFalse(target.signal_group(signal.SIGKILL))

        self.assertFalse(target.owned)
        send.assert_not_called()

    def test_denied_owned_group_signal_remains_a_failure(self) -> None:
        target = self.target()
        with patch("os.waitid", return_value=None), patch("os.killpg", side_effect=PermissionError):
            self.assertFalse(target.signal_group(signal.SIGTERM))
        self.assertIn("group-signal-failed", target.errors)

    def test_already_quiescent_group_needs_no_denied_signal(self) -> None:
        target = self.target()
        with (
            patch("os.waitid", return_value=SimpleNamespace(si_status=0, si_code=1)),
            patch("os.waitpid", return_value=(123, 0)),
            patch("os.killpg", side_effect=PermissionError) as send,
            patch("src.system.process_owner._members", return_value=False),
            patch("src.system.process_owner._clock", return_value=0),
        ):
            self.assertEqual(stop_target(target, 1000, 100, "command"), "quiescent")
        send.assert_not_called()
        self.assertTrue(target.reaped)
        self.assertEqual(target.errors, [])

    def test_reap_revokes_authority_before_waitpid(self) -> None:
        target = self.target()
        target.status = 0

        def reap(pid: int, flags: int) -> tuple[int, int]:
            self.assertFalse(target.owned)
            return pid, 0

        with (
            patch("os.waitid", return_value=SimpleNamespace(si_status=0, si_code=1)),
            patch("os.waitpid", side_effect=reap),
            patch("os.killpg") as send,
        ):
            self.assertTrue(target.reap())
            self.assertFalse(target.signal_group(signal.SIGKILL))

        send.assert_not_called()


class ControlDocumentTests(unittest.TestCase):
    def test_missing_platform_capabilities_refuse_without_startup(self) -> None:
        control = Mock()
        unsupported_signal = SimpleNamespace()
        with (
            patch("src.system.process_owner.Control", return_value=control),
            patch("src.system.process_owner.signal", unsupported_signal),
            patch("os.name", "nt"),
            patch("subprocess.Popen") as spawn,
        ):
            self.assertEqual(main(), 2)
        spawn.assert_not_called()
        control.send.assert_called_once_with(
            {"type": "refused", "reason": "python-3.13-waitid-ps-required"},
            ANY,
        )

    def test_pending_stop_is_observed_before_an_expired_local_deadline(self) -> None:
        payload = b'{"version":1,"type":"stop","reason":"cancel","deadline":9}\n'
        with (
            patch("os.set_blocking"),
            patch("src.system.process_owner._clock", return_value=10),
            patch("select.select", return_value=([123], [], [])),
            patch("os.read", return_value=payload),
        ):
            received = Control(123).receive(9, 16384)
        self.assertEqual(
            received, {"version": 1, "type": "stop", "reason": "cancel", "deadline": 9}
        )

    def start(self) -> dict[str, object]:
        return {
            "version": 1,
            "type": "start",
            "argv": ["program", "argument"],
            "cwd": None,
            "env": {"EXAMPLE": "value"},
            "executionDeadline": 5000,
            "startupDeadline": 2000,
            "cleanupMs": 100,
            "mode": "command",
        }

    def test_start_preserves_target_and_fixed_deadlines(self) -> None:
        request = parse_start(self.start())
        self.assertEqual(request.argv, ("program", "argument"))
        self.assertEqual(request.execution_deadline, 5000)
        self.assertEqual(request.startup_deadline, 2000)
        self.assertEqual(request.cleanup_ms, 100)

    def test_invalid_start_cannot_launch_a_target(self) -> None:
        for key, value in (
            ("version", True),
            ("version", 2),
            ("argv", []),
            ("argv", ["program", "bad\x00argument"]),
            ("env", {"BAD": "nul\x00value"}),
            ("cleanupMs", 0),
            ("executionDeadline", 1.5),
            ("unknown", "field"),
        ):
            document = self.start()
            document[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                parse_start(document)

    def test_complete_control_document_preserves_fields(self) -> None:
        self.assertEqual(
            decode_document(b'{"version":1,"type":"stop","reason":"cancel","deadline":42}'),
            {"version": 1, "type": "stop", "reason": "cancel", "deadline": 42},
        )

    def test_malformed_documents_never_become_a_request(self) -> None:
        for payload in (
            b"\xff",
            b'{"version":1,"version":1}',
            b"[]",
            b'{"value":NaN}',
            b"x" * (1024 * 1024 + 1),
        ):
            with self.subTest(payload=payload[:32]), self.assertRaises(ValueError):
                decode_document(payload)


class GroupObservationTests(unittest.TestCase):
    def test_executable_descendant_is_distinct_from_retained_zombie(self) -> None:
        self.assertTrue(executable_members(b"123 123 Z\n124 123 S\n", 123))
        self.assertFalse(executable_members(b"123 123 Z\n124 999 S\n", 123))

    def test_zero_group_rows_preserve_exact_target_membership(self) -> None:
        payload = b"2 0 S\n99 1234 R\n123 123 Z+\n"
        self.assertFalse(executable_members(payload, 123))
        self.assertTrue(executable_members(payload + b"124 123 S\n", 123))

    def test_invalid_observation_is_not_an_empty_group(self) -> None:
        for payload in (
            b"incomplete\n",
            b"123 123 S extra\n",
            b"0 123 S\n",
            b"-1 123 S\n",
            b"123 -1 S\n",
        ):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                executable_members(payload, 123)

    def test_observer_setup_failure_reaps_and_closes_without_claiming_quiescence(self) -> None:
        target = OwnedTarget(cast("subprocess.Popen[bytes]", SimpleNamespace(pid=123)))
        observation = Mock()
        stream = observation.stdout
        stream.fileno.return_value = 456
        observation.poll.return_value = None
        observation.wait.return_value = 0
        cleanup = Mock()
        cleanup.attach_mock(observation.kill, "kill")
        cleanup.attach_mock(observation.wait, "wait")
        cleanup.attach_mock(stream.close, "close")
        clock = Mock(return_value=0)
        failure = OSError("Observation setup unavailable")

        def fail_setup(_fd: int, _blocking: bool) -> None:
            # Expire the original stop window without permitting another observation.
            clock.return_value = 1000
            raise failure

        with (
            patch("subprocess.Popen", return_value=observation) as spawn,
            patch("os.set_blocking", side_effect=fail_setup) as configure,
            patch("src.system.process_owner._clock", clock),
            patch("os.waitid", return_value=SimpleNamespace(si_status=0, si_code=1)),
            patch("os.waitpid", return_value=(123, 0)),
            patch("os.killpg") as send,
        ):
            result = stop_target(target, 1000, 100, "command")

        spawn.assert_called_once()
        configure.assert_called_once_with(456, False)
        self.assertEqual(result, "unknown")
        self.assertEqual(target.errors, ["group-observation-failed", "group-shutdown-unconfirmed"])
        self.assertTrue(target.reaped)
        self.assertFalse(target.owned)
        send.assert_not_called()
        self.assertEqual(cleanup.mock_calls, [call.kill(), call.wait(timeout=0), call.close()])

    def test_successful_observation_reaps_and_closes_without_killing(self) -> None:
        target = OwnedTarget(cast("subprocess.Popen[bytes]", SimpleNamespace(pid=123)))
        observation = Mock()
        stream = observation.stdout
        stream.fileno.return_value = 456
        observation.poll.return_value = 0
        observation.wait.return_value = 0

        with (
            patch("subprocess.Popen", return_value=observation) as spawn,
            patch("os.set_blocking") as configure,
            patch("src.system.process_owner._clock", return_value=0),
            patch("select.select", return_value=([stream], [], [])),
            patch("os.read", side_effect=[b"123 123 Z\n", b""]),
            patch("os.waitid", return_value=SimpleNamespace(si_status=0, si_code=1)),
            patch("os.waitpid", return_value=(123, 0)),
            patch("os.killpg") as send,
        ):
            result = stop_target(target, 1000, 100, "command")

        spawn.assert_called_once()
        configure.assert_called_once_with(456, False)
        spawn.assert_called_once_with(
            ["ps", "-A", "-o", "pid=,pgid=,stat="],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        observation.wait.assert_called_once_with(timeout=1)
        observation.kill.assert_not_called()
        stream.close.assert_called_once()
        self.assertEqual(result, "quiescent")
        self.assertEqual(target.errors, [])
        self.assertTrue(target.reaped)
        self.assertFalse(target.owned)
        send.assert_not_called()


class QueuedStopTests(unittest.TestCase):
    """A queued close cannot hide a leader that already exited."""

    def outcome(self, status: int | None) -> tuple[dict[str, object], list[signal.Signals]]:
        control = Mock()
        control.fd = 3
        start = ControlDocumentTests().start()
        stop = {"version": 1, "type": "stop", "reason": "close", "deadline": 170}
        control.receive.side_effect = [start, stop]
        sends: list[dict[str, object]] = []

        def record(value: dict[str, object], _deadline: int) -> None:
            sends.append(value)

        control.send.side_effect = record
        signals: list[signal.Signals] = []
        child = SimpleNamespace(pid=123, returncode=None)

        def observe(*_arguments: object) -> SimpleNamespace | None:
            if status is not None:
                return SimpleNamespace(si_status=status, si_code=1)
            if signals:
                return SimpleNamespace(si_status=signal.SIGTERM, si_code=2)
            return None

        def send(_group: int, number: signal.Signals) -> None:
            signals.append(number)

        raw_status = status << 8 if status is not None else int(signal.SIGTERM)
        with (
            patch("src.system.process_owner.Control", return_value=control),
            patch("src.system.process_owner._clock", return_value=100),
            patch("src.system.process_owner._members", return_value=False),
            patch("shutil.which", return_value="recording-ps"),
            patch("subprocess.Popen", return_value=child),
            patch("signal.signal"),
            patch("os.close"),
            patch("os.waitid", side_effect=observe),
            patch("os.waitpid", return_value=(123, raw_status)),
            patch("os.killpg", side_effect=send),
        ):
            self.assertEqual(main(), 0)
        terminal = sends[-1]
        self.assertEqual(terminal["type"], "finished")
        self.assertEqual(terminal["groupState"], "quiescent")
        self.assertTrue(terminal["leaderReaped"])
        return terminal, signals

    def test_queued_close_preserves_already_exited_failure(self) -> None:
        terminal, signals = self.outcome(2)
        self.assertEqual(terminal["status"], 2)
        self.assertEqual(terminal["reason"], "target-exit")
        self.assertEqual(signals, [])

    def test_queued_close_preserves_already_exited_success(self) -> None:
        terminal, signals = self.outcome(0)
        self.assertEqual(terminal["status"], 0)
        self.assertEqual(terminal["reason"], "target-exit")
        self.assertEqual(signals, [])

    def test_healthy_intentional_stop_is_not_an_earlier_crash(self) -> None:
        terminal, signals = self.outcome(None)
        self.assertEqual(terminal["status"], 128 + signal.SIGTERM)
        self.assertEqual(terminal["reason"], "close")
        self.assertEqual(signals, [signal.SIGTERM])


if __name__ == "__main__":
    unittest.main()
