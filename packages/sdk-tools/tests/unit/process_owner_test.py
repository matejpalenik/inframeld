"""Prove wait ownership at a syscall boundary without real process signals."""

import json
import os
import signal
import socket
import subprocess
import time
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
    observe_members,
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
            patch("src.system.process_owner.observe_members", return_value=False),
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
    def test_finish_consumes_only_the_remaining_stop_then_clean_eof(self) -> None:
        stop = b'{"version":1,"type":"stop","reason":"cancel","deadline":9}\n'
        for received in (False, True):
            with self.subTest(received=received), patch("os.set_blocking"):
                control = Control(123)
                control.buffer = bytearray(b"" if received else stop)
                with (
                    patch("src.system.process_owner._clock", return_value=0),
                    patch("select.select", return_value=([123], [], [])),
                    patch("os.read", return_value=b""),
                    patch.object(control, "receive", wraps=control.receive) as receive,
                ):
                    control.finish(500, received)
                self.assertEqual(
                    receive.call_args_list, [call(500, 16384)] * (1 if received else 2)
                )
                self.assertEqual(control.buffer, bytearray())

    def test_finish_rejects_partial_malformed_duplicate_and_oversize_frames(self) -> None:
        stop = b'{"version":1,"type":"stop","reason":"cancel","deadline":9}\n'
        for payload, received in (
            (b'{"version":1', False),
            (b'{"version":1,"type":"unexpected"}\n', False),
            (stop + stop, False),
            (stop, True),
            (b"x" * 16385, False),
        ):
            with self.subTest(size=len(payload), received=received), patch("os.set_blocking"):
                control = Control(123)
                control.buffer = bytearray(payload)
                with (
                    patch("src.system.process_owner._clock", return_value=0),
                    patch("select.select", return_value=([123], [], [])),
                    patch("os.read", return_value=b""),
                    self.assertRaises(ValueError),
                ):
                    control.finish(500, received)

    def test_finish_preserves_transport_failure_and_the_original_deadline(self) -> None:
        with patch("os.set_blocking"):
            control = Control(123)
        failure = OSError("private transport failure")
        with (
            patch("src.system.process_owner._clock", return_value=0),
            patch("select.select", return_value=([123], [], [])),
            patch("os.read", side_effect=failure),
            self.assertRaises(OSError) as raised,
        ):
            control.finish(500, False)
        self.assertIs(raised.exception, failure)
        for expired in (False, True):
            with (
                self.subTest(expired=expired),
                patch("src.system.process_owner._clock", return_value=500 if expired else 0),
                patch("select.select", return_value=([], [], [])),
                self.assertRaises(TimeoutError),
            ):
                control.finish(500, False)
        clock = Mock(return_value=0)

        def late_eof(_fd: int, _maximum: int) -> bytes:
            clock.return_value = 500
            return b""

        with (
            patch("src.system.process_owner._clock", clock),
            patch("select.select", return_value=([123], [], [])),
            patch("os.read", side_effect=late_eof),
            self.assertRaises(TimeoutError),
        ):
            control.finish(500, False)

    def test_socketpair_unread_and_drained_stop_close(self) -> None:
        terminal: dict[str, object] = {
            "type": "finished",
            "status": 0,
            "reason": "target-exit",
            "leaderReaped": True,
            "groupState": "quiescent",
            "errors": [],
        }
        for order in ("queued-before-terminal", "preconsumed-stop", "stop-after-terminal"):
            caller_socket, helper_socket = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
            with self.subTest(order=order), caller_socket, helper_socket:
                caller = Control(caller_socket.fileno())
                helper = Control(helper_socket.fileno())
                deadline = time.monotonic_ns() // 1_000_000 + 500
                stop: dict[str, object] = {"type": "stop", "reason": "close", "deadline": deadline}
                if order != "stop-after-terminal":
                    caller.send(stop, deadline)
                if order == "preconsumed-stop":
                    self.assertEqual(helper.receive(deadline, 16384), {"version": 1, **stop})
                helper.send(terminal, deadline)
                self.assertEqual(caller.receive(deadline, 16384), {"version": 1, **terminal})
                if order == "stop-after-terminal":
                    caller.send(stop, deadline)
                caller_socket.shutdown(socket.SHUT_WR)
                helper.finish(deadline, order == "preconsumed-stop")
                helper_socket.close()
                with self.assertRaises(EOFError):
                    caller.receive(deadline, 16384)
                print(json.dumps({"order": order, "terminalReceived": True, "ending": "eof"}))

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
    def test_first_observer_diagnostic_identifies_step_without_replacing_exception(self) -> None:
        for step, failure, category in (
            ("spawn", OSError("private"), "os"),
            ("read", TimeoutError("private"), "timeout"),
            ("wait", subprocess.TimeoutExpired("private", 0.5), "timeout"),
            ("parse", ValueError("private"), "malformed"),
        ):
            with self.subTest(step=step):
                target = OwnedTarget(cast("subprocess.Popen[bytes]", SimpleNamespace(pid=123)))
                observation = Mock()
                observation.stdout.fileno.return_value = 456
                observation.poll.return_value = 0
                observation.wait.return_value = 0
                if step == "wait":
                    observation.wait.side_effect = failure
                with (
                    patch(
                        "subprocess.Popen",
                        return_value=observation,
                        side_effect=failure if step == "spawn" else None,
                    ),
                    patch("src.system.process_owner._clock", return_value=0),
                    patch("os.set_blocking"),
                    patch(
                        "select.select",
                        return_value=([observation.stdout], [], []),
                        side_effect=failure if step == "read" else None,
                    ),
                    patch("os.read", side_effect=[b"123 123 Z\n", b""]),
                    patch(
                        "src.system.process_owner.executable_members",
                        return_value=False,
                        side_effect=failure if step == "parse" else None,
                    ),
                    self.assertRaises(type(failure)) as raised,
                ):
                    observe_members(target, 500, "term")
                self.assertIs(raised.exception, failure)
                self.assertEqual(target.errors, [f"ps-term-{step}-{category}"])

    def test_first_observer_diagnostic_distinguishes_nonzero_and_reap_failure(self) -> None:
        for nonzero in (True, False):
            with self.subTest(nonzero=nonzero):
                target = OwnedTarget(cast("subprocess.Popen[bytes]", SimpleNamespace(pid=123)))
                observation = Mock()
                observation.stdout.fileno.return_value = 456
                observation.wait.return_value = 1 if nonzero else 0
                observation.poll.side_effect = None if nonzero else OSError("private")
                observation.poll.return_value = 1
                with (
                    patch("subprocess.Popen", return_value=observation),
                    patch("src.system.process_owner._clock", return_value=0),
                    patch("os.set_blocking"),
                    patch("select.select", return_value=([observation.stdout], [], [])),
                    patch("os.read", side_effect=[b"123 123 Z\n", b""]),
                    self.assertRaises(ValueError if nonzero else OSError),
                ):
                    observe_members(target, 500, "kill")
                self.assertEqual(
                    target.errors, ["ps-kill-wait-nonzero" if nonzero else "ps-kill-reap-os"]
                )

    def test_first_observer_diagnostic_stays_first_and_leaves_cleanup_error_capacity(self) -> None:
        for existing in ([], ["retained"] * 12):
            with self.subTest(existing=len(existing)):
                target = OwnedTarget(cast("subprocess.Popen[bytes]", SimpleNamespace(pid=123)))
                target.errors.extend(existing)
                for phase in ("initial", "kill"):
                    with (
                        patch("subprocess.Popen", side_effect=OSError("private")),
                        patch("src.system.process_owner._clock", return_value=0),
                        self.assertRaises(OSError),
                    ):
                        observe_members(target, 500, phase)
                self.assertEqual(target.errors, existing or ["ps-initial-spawn-os"])

    def test_observer_timeout_keeps_its_own_termination_and_wait_inside_the_phase(self) -> None:
        target = OwnedTarget(cast("subprocess.Popen[bytes]", SimpleNamespace(pid=123)))
        observation = Mock()
        observation.stdout.fileno.return_value = 456
        observation.poll.return_value = None
        observation.wait.return_value = 0
        clock = Mock(return_value=0)

        def timeout(
            _read: object, _write: object, _error: object, seconds: float
        ) -> tuple[list[object], list[object], list[object]]:
            clock.return_value = round(seconds * 1000)
            return [], [], []

        with (
            patch("src.system.process_owner._clock", clock),
            patch("subprocess.Popen", return_value=observation),
            patch("os.set_blocking"),
            patch("select.select", side_effect=timeout),
            self.assertRaises(TimeoutError),
        ):
            observe_members(target, 500)
        observation.kill.assert_called_once()
        observation.wait.assert_called_once_with(timeout=0.05)
        observation.stdout.close.assert_called_once()
        self.assertEqual(clock(), 450)

    def test_one_early_term_probe_avoids_a_slower_optional_tail_query(self) -> None:
        target = OwnedTarget(cast("subprocess.Popen[bytes]", SimpleNamespace(pid=123)))
        clock = Mock(return_value=0)
        signals: list[tuple[signal.Signals, int]] = []
        observations: list[tuple[str, int]] = []

        def observe(_target: OwnedTarget, cutoff: int, phase: str) -> bool:
            observations.append((phase, clock()))
            cost = 100 if phase == "kill" or phase == "term" and clock() >= 200 else 5
            allowance = min(cutoff - clock(), 1000)
            read_ms = allowance - min(50, max(1, allowance // 4))
            if read_ms < cost:
                clock.return_value += read_ms
                raise TimeoutError
            clock.return_value += cost
            return phase != "kill" or sum(item[0] == "kill" for item in observations) == 1

        def sleep(seconds: float) -> None:
            clock.return_value += round(seconds * 1000)

        def send(_pid: int, number: signal.Signals) -> None:
            signals.append((number, clock()))

        with (
            patch("src.system.process_owner._clock", clock),
            patch("src.system.process_owner.observe_members", side_effect=observe),
            patch("time.sleep", side_effect=sleep),
            patch("os.waitid", return_value=SimpleNamespace(si_status=0, si_code=1)),
            patch("os.waitpid", return_value=(123, 0)),
            patch("os.killpg", side_effect=send),
        ):
            self.assertEqual(stop_target(target, 600, 600, "command"), "quiescent")
        self.assertEqual(signals, [(signal.SIGTERM, 5), (signal.SIGKILL, 300)])
        self.assertEqual(observations, [("initial", 0), ("term", 5), ("kill", 300), ("kill", 410)])
        self.assertEqual(clock(), 510)
        self.assertEqual(target.errors, [])
        self.assertTrue(target.reaped)
        self.assertFalse(target.owned)

    def test_graceful_leader_exit_after_term_avoids_an_unnecessary_kill(self) -> None:
        target = OwnedTarget(cast("subprocess.Popen[bytes]", SimpleNamespace(pid=123)))
        clock = Mock(return_value=0)
        signals: list[tuple[signal.Signals, int]] = []
        observations: list[tuple[str, int]] = []

        def wait(*_arguments: object) -> SimpleNamespace | None:
            return SimpleNamespace(si_status=0, si_code=1) if clock() >= 20 else None

        def observe(_target: OwnedTarget, _cutoff: int, phase: str) -> bool:
            observations.append((phase, clock()))
            return False

        def sleep(seconds: float) -> None:
            clock.return_value += round(seconds * 1000)

        def send(_pid: int, number: signal.Signals) -> None:
            signals.append((number, clock()))
            if number == signal.SIGKILL:
                raise PermissionError

        with (
            patch("src.system.process_owner._clock", clock),
            patch("src.system.process_owner.observe_members", side_effect=observe),
            patch("time.sleep", side_effect=sleep),
            patch("os.waitid", side_effect=wait),
            patch("os.waitpid", return_value=(123, 0)),
            patch("os.killpg", side_effect=send),
        ):
            self.assertEqual(stop_target(target, 600, 600, "command"), "quiescent")
        self.assertEqual(signals, [(signal.SIGTERM, 0)])
        self.assertEqual(observations, [("term", 20)])
        self.assertEqual(target.errors, [])
        self.assertTrue(target.reaped)

    def test_ownership_loss_during_term_wait_prevents_kill(self) -> None:
        target = OwnedTarget(cast("subprocess.Popen[bytes]", SimpleNamespace(pid=123)))
        clock = Mock(return_value=0)

        def wait(*_arguments: object) -> None:
            if clock() >= 100:
                raise ChildProcessError

        def sleep(seconds: float) -> None:
            clock.return_value += round(seconds * 1000)

        with (
            patch("src.system.process_owner._clock", clock),
            patch("src.system.process_owner.observe_members") as observe,
            patch("time.sleep", side_effect=sleep),
            patch("os.waitid", side_effect=wait),
            patch("os.waitpid") as reap,
            patch("os.killpg") as send,
        ):
            self.assertEqual(stop_target(target, 600, 600, "command"), "unknown")
        send.assert_called_once_with(123, signal.SIGTERM)
        observe.assert_not_called()
        reap.assert_not_called()
        self.assertFalse(target.owned)
        self.assertIn("wait-ownership-lost", target.errors)

    def test_genuine_early_term_error_stays_unknown_after_later_quiescence(self) -> None:
        target = OwnedTarget(cast("subprocess.Popen[bytes]", SimpleNamespace(pid=123)))
        clock = Mock(return_value=0)
        observations: list[str] = []

        def observe(_target: OwnedTarget, cutoff: int, phase: str) -> bool:
            observations.append(phase)
            if phase == "term":
                self.assertGreater(cutoff - clock(), 200)
                raise TimeoutError
            return phase == "initial"

        def sleep(seconds: float) -> None:
            clock.return_value += round(seconds * 1000)

        with (
            patch("src.system.process_owner._clock", clock),
            patch("src.system.process_owner.observe_members", side_effect=observe),
            patch("time.sleep", side_effect=sleep),
            patch("os.waitid", return_value=SimpleNamespace(si_status=0, si_code=1)),
            patch("os.waitpid", return_value=(123, 0)),
            patch("os.killpg"),
        ):
            self.assertEqual(stop_target(target, 600, 600, "command"), "unknown")
        self.assertEqual(observations, ["initial", "term", "kill"])
        self.assertEqual(target.errors, ["group-observation-failed"])
        self.assertTrue(target.reaped)

    def test_observation_without_its_reap_slice_is_skipped_before_owned_escalation(self) -> None:
        target = OwnedTarget(cast("subprocess.Popen[bytes]", SimpleNamespace(pid=123)))
        clock = Mock(return_value=480)
        signals: list[tuple[signal.Signals, int]] = []

        def observe(_target: OwnedTarget, cutoff: int, _phase: str) -> bool:
            self.assertGreater(
                cutoff - clock(), 50, "Do not admit an observer without its own slice"
            )
            return False

        def sleep(seconds: float) -> None:
            clock.return_value += round(seconds * 1000)

        def send(_pid: int, number: signal.Signals) -> None:
            signals.append((number, clock()))

        with (
            patch("src.system.process_owner._clock", clock),
            patch("src.system.process_owner.observe_members", side_effect=observe),
            patch("time.sleep", side_effect=sleep),
            patch("os.waitid", return_value=SimpleNamespace(si_status=0, si_code=1)),
            patch("os.waitpid", return_value=(123, 0)),
            patch("os.killpg", side_effect=send),
        ):
            self.assertEqual(stop_target(target, 1000, 1000, "command"), "quiescent")
        self.assertIn((signal.SIGKILL, 500), signals)
        self.assertEqual(target.errors, [])

    def test_slow_observation_preserves_owned_escalation_and_finalization(self) -> None:
        target = OwnedTarget(cast("subprocess.Popen[bytes]", SimpleNamespace(pid=123)))
        clock = Mock(return_value=0)
        signals: list[tuple[signal.Signals, int]] = []

        def observe(_target: OwnedTarget, cutoff: int, phase: str) -> bool:
            if phase == "initial":
                clock.return_value = cutoff
                raise TimeoutError
            return False

        def send(_pid: int, number: signal.Signals) -> None:
            signals.append((number, clock()))

        with (
            patch("src.system.process_owner._clock", clock),
            patch("src.system.process_owner.observe_members", side_effect=observe),
            patch("os.waitid", return_value=SimpleNamespace(si_status=0, si_code=1)),
            patch("os.waitpid", return_value=(123, 0)),
            patch("os.killpg", side_effect=send),
        ):
            self.assertEqual(stop_target(target, 1000, 1000, "command"), "unknown")

        self.assertIn((signal.SIGKILL, 500), signals)
        self.assertLess(clock(), 1000)
        self.assertTrue(target.reaped)
        self.assertFalse(target.owned)
        self.assertIn("group-observation-failed", target.errors)
        self.assertNotIn("group-shutdown-unconfirmed", target.errors)

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
        self.assertEqual(
            target.errors,
            ["ps-initial-read-os", "group-observation-failed", "group-shutdown-unconfirmed"],
        )
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
            patch.dict(
                os.environ,
                {
                    "PS_PERSONALITY": "bsd",
                    "CMD_ENV": "sco",
                    "I_WANT_A_BROKEN_PS": "1",
                    "LC_ALL": "hostile",
                    "SENTINEL": "preserved",
                },
                clear=True,
            ),
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
        observer_env = {"LC_ALL": "C", "SENTINEL": "preserved"}
        spawn.assert_called_once_with(
            ["ps", "-A", "-o", "pid=,pgid=,stat="],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=observer_env,
        )
        self.assertGreater(observation.wait.call_args.kwargs["timeout"], 0)
        self.assertLess(observation.wait.call_args.kwargs["timeout"], 1)
        observation.kill.assert_not_called()
        stream.close.assert_called_once()
        self.assertEqual(result, "quiescent")
        self.assertEqual(target.errors, [])
        self.assertTrue(target.reaped)
        self.assertFalse(target.owned)
        send.assert_not_called()


class QueuedStopTests(unittest.TestCase):
    """A queued close cannot hide a leader that already exited."""

    def outcome(
        self, status: int | None, *, queued: bool = True, finish_error: Exception | None = None
    ) -> tuple[dict[str, object], list[signal.Signals]]:
        control = Mock()
        control.fd = 3
        start = ControlDocumentTests().start()
        stop = {"version": 1, "type": "stop", "reason": "close", "deadline": 170}
        control.receive.side_effect = [start, stop if queued else None]
        control.finish.side_effect = finish_error
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
            patch("src.system.process_owner.observe_members", return_value=False),
            patch("shutil.which", return_value="recording-ps"),
            patch("subprocess.Popen", return_value=child),
            patch("signal.signal"),
            patch("os.close") as close,
            patch("os.waitid", side_effect=observe),
            patch("os.waitpid", return_value=(123, raw_status)),
            patch("os.killpg", side_effect=send),
        ):
            self.assertEqual(main(), 1 if finish_error else 0)
        control.finish.assert_called_once_with(170 if queued else 200, queued)
        self.assertEqual(control.method_calls[-1], call.finish(170 if queued else 200, queued))
        self.assertEqual(close.call_args, call(3))
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

    def test_autonomous_exit_allows_only_the_remaining_stop_at_finish(self) -> None:
        self.outcome(0, queued=False)

    def test_failed_control_finish_keeps_successful_target_cleanup_a_helper_failure(self) -> None:
        self.outcome(0, finish_error=TimeoutError())


if __name__ == "__main__":
    unittest.main()
