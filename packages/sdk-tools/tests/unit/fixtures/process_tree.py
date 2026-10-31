"""Finite target trees whose safety fuse cannot satisfy an earlier cleanup assertion."""

import importlib.util
import json
import os
import signal
import subprocess
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path


def _ignore_term(_number: int, _frame: object) -> None:
    pass


def main() -> None:
    mode = sys.argv[1]
    # Tests assert cleanup before two seconds. This fuse only bounds failed fixtures.
    signal.alarm(4)
    if mode == "protocol-owner":
        scenario, trace = sys.argv[2:4]

        def send(value: dict[str, object]) -> None:
            os.write(3, json.dumps({"version": 1, **value}, separators=(",", ":")).encode() + b"\n")

        def read_document() -> bytes:
            data = bytearray()
            while not data.endswith(b"\n"):
                chunk = os.read(3, 65536)
                if not chunk:
                    break
                data.extend(chunk)
            return bytes(data)

        if scenario == "refuse":
            send({"type": "refused", "reason": "python-3.13-waitid-ps-required"})
            return
        if scenario == "late-ready":
            time.sleep(0.08)
            send({"type": "ready", "clock": time.monotonic_ns() // 1_000_000, "python": "3.13.12"})
            Path(trace).write_bytes(read_document())
            send({"type": "refused", "reason": "expired-before-start"})
            return
        if scenario == "invalid-utf8":
            os.write(3, b"\xff\n")
            read_document()
            return
        send({"type": "ready", "clock": time.monotonic_ns() // 1_000_000, "python": "3.13.12"})
        read_document()
        if scenario == "handoff-abort":
            Path(trace).write_text(json.dumps({"submitted": True}))
            time.sleep(0.075)
        if scenario == "lost-control":
            signal.alarm(8)
            child = subprocess.Popen(
                [sys.executable, "-B", __file__, "wait"],
                stdin=subprocess.DEVNULL,
                close_fds=True,
                start_new_session=True,
            )
            send({"type": "started", "pid": child.pid})
            os.close(3)
            Path(trace).write_text(json.dumps({"target": child.pid, "helper": os.getpid()}))
            child.wait(timeout=6)
            Path(trace + ".recovered").write_text(json.dumps({"reaped": True}))
            return
        send({"type": "started", "pid": os.getpid()})
        time.sleep(0.075)
        stop = json.loads(read_document())
        Path(trace).write_text(
            json.dumps({"remaining": stop["deadline"] - time.monotonic_ns() // 1_000_000})
        )
        send(
            {
                "type": "finished",
                "status": None,
                "reason": "close",
                "leaderReaped": False,
                "groupState": "unknown",
                "errors": ["controlled-missing-proof"],
            }
        )
        return
    if mode in ("backend-owner", "denied-owner", "ordered-exit-owner"):
        owner_path, marker = sys.argv[2:4]
        if mode == "denied-owner":
            signal.alarm(8)
        spec = importlib.util.spec_from_file_location("controlled_owner", owner_path)
        assert spec is not None and spec.loader is not None
        owner = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = owner
        spec.loader.exec_module(owner)
        if mode == "backend-owner":
            parse = owner.parse_start

            def controlled_start(value: dict[str, object]) -> object:
                request = parse(value)
                return replace(
                    request,
                    argv=(sys.executable, "-B", __file__, "wait", marker),
                    cwd=None,
                )

            owner.__dict__["parse_start"] = controlled_start
            raise SystemExit(owner.main())
        children: list[subprocess.Popen[bytes]] = []
        popen = subprocess.Popen

        def record_child(
            args: Sequence[str],
            *,
            stdin: int | None = None,
            stdout: int | None = None,
            stderr: int | None = None,
            cwd: str | None = None,
            env: Mapping[str, str] | None = None,
            close_fds: bool = True,
            start_new_session: bool = False,
        ) -> subprocess.Popen[bytes]:
            child = popen(
                args,
                stdin=stdin,
                stdout=stdout,
                stderr=stderr,
                cwd=cwd,
                env=env,
                close_fds=close_fds,
                start_new_session=start_new_session,
            )
            if args and args[0] != "ps":
                children.append(child)
            return child

        owner.subprocess.Popen = record_child
        if mode == "ordered-exit-owner":
            receive = owner.Control.receive
            execution_deadline = 0
            observed: dict[str, object] = {}

            def ordered_receive(
                control: object, deadline: int, maximum: int
            ) -> dict[str, object] | None:
                nonlocal execution_deadline
                if not execution_deadline:
                    document: dict[str, object] | None = receive(control, deadline, maximum)
                    if document is not None:
                        value = document.get("executionDeadline")
                        if type(value) is not int:
                            raise ValueError("Missing controlled execution deadline.")
                        execution_deadline = value
                    return document
                # Hold this receive turn until STOP is queued. The real helper
                # has not called OwnedTarget.observe yet, and retains its child.
                document = receive(
                    control,
                    min(execution_deadline, time.monotonic_ns() // 1_000_000 + 500),
                    maximum,
                )
                if document is None or document.get("type") != "stop" or len(children) != 1:
                    raise ValueError("Controlled STOP did not arrive.")
                stop_deadline = document.get("deadline")
                if type(stop_deadline) is not int:
                    raise ValueError("Missing controlled stop deadline.")
                while time.monotonic_ns() // 1_000_000 < stop_deadline:
                    status = os.waitid(
                        os.P_PID, children[0].pid, os.WEXITED | os.WNOHANG | os.WNOWAIT
                    )
                    if status is not None:
                        if status.si_code != os.CLD_EXITED or status.si_status != 2:
                            raise ValueError("Controlled target did not exit two.")
                        observed.update(
                            queuedStop=document.get("reason"),
                            observedExit=2,
                            stopDeadline=stop_deadline,
                            observedAt=time.monotonic_ns() // 1_000_000,
                        )
                        return document
                    time.sleep(0.001)
                raise TimeoutError("Controlled target exit exceeded the existing stop deadline.")

            owner.Control.receive = ordered_receive
            code = owner.main()
            Path(marker).write_text(
                json.dumps(
                    {
                        **observed,
                        "ownerResult": code,
                        "returncodes": [c.returncode for c in children],
                    }
                )
            )
            raise SystemExit(code)

        def deny_signal(group: int, number: int) -> None:
            raise PermissionError("Controlled owned-signal denial.")

        owner.os.killpg = deny_signal
        code = owner.main()
        work = Path(marker).parent
        (work / "uncertain.json").write_text(
            json.dumps(
                {
                    "unknown": True,
                    "ownerResult": code,
                    "helper": os.getpid(),
                    "targets": [child.pid for child in children],
                }
            )
        )
        # Production signalling has ended. This fixture remains the sole waiter,
        # and reaps its finite child after the later safety fuse without signals.
        for child in children:
            child.wait(timeout=6)
        (work / "fixture-recovered.json").write_text(json.dumps({"reaped": True}))
        raise SystemExit(code)
    if mode == "exit-two":
        raise SystemExit(2)
    if mode == "echo":
        sys.stdout.buffer.write(sys.stdin.buffer.read())
        return
    if mode == "split-utf8":
        sys.stdout.buffer.write(b"\xc3")
        sys.stdout.buffer.flush()
        time.sleep(0.02)
        sys.stdout.buffer.write(b"\xa9")
        return
    if mode == "noisy":
        sys.stdout.buffer.write(b"x" * 100_000)
        sys.stdout.buffer.flush()
    if mode == "leader":
        marker, pipes = sys.argv[2:4]
        subprocess.Popen(
            [sys.executable, "-B", __file__, "descendant", marker],
            stdin=subprocess.DEVNULL,
            stdout=None if pipes == "open" else subprocess.DEVNULL,
            stderr=None if pipes == "open" else subprocess.DEVNULL,
        )
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline and not Path(marker).exists():
            time.sleep(0.005)
        if not Path(marker).exists():
            raise RuntimeError("Descendant did not become ready.")
        return
    parent = os.getppid()
    orphan_reported = False
    if mode == "descendant":
        signal.signal(signal.SIGTERM, _ignore_term)
        Path(sys.argv[2]).write_text(str(os.getpid()))
    if mode == "wait" and len(sys.argv) > 2:
        Path(sys.argv[2]).write_text(str(os.getpid()))
    if mode not in ("wait", "noisy", "descendant"):
        raise ValueError("Unknown finite fixture.")
    while True:
        if mode == "descendant" and not orphan_reported and os.getppid() != parent:
            Path(sys.argv[2] + ".orphaned").write_text("leader-exited")
            orphan_reported = True
        time.sleep(0.01)


if __name__ == "__main__":
    main()
