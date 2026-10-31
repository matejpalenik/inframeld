import assert from "node:assert/strict";
import test, { type TestContext } from "node:test";
import childProcess, { type SpawnOptions } from "node:child_process";
import { syncBuiltinESMExports } from "node:module";
import {
  command,
  startProcess,
  stopProcess,
  withResources,
  type OwnedProcess,
} from "../../src/system/process.ts";
import { fileURLToPath, pathToFileURL } from "node:url";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { setTimeout as delay } from "node:timers/promises";
import { EventEmitter } from "node:events";
import { Duplex, PassThrough, Writable } from "node:stream";

const finiteFixture = fileURLToPath(
  new URL("./fixtures/process_tree.py", import.meta.url),
);

/** Deliver valid owner evidence and flushed bytes before acquisition resumes. */
async function pureHelper(
  context: TestContext,
  scenario: {
    chunks?: [number, Buffer][];
    lateChunks?: [number, Buffer][];
    stopChunks?: [number, Buffer][];
    waitForStop?: boolean;
    terminalDelay?: number;
    exitDelay?: number;
    errors?: string[];
    acquired?: () => void;
  },
  run: (stops: { deadline: number; at: number }[]) => Promise<void>,
): Promise<void> {
  const stops: { deadline: number; at: number }[] = [];
  const timers = new Set<ReturnType<typeof setTimeout>>();
  const stdout = new PassThrough();
  const stderr = new PassThrough();
  const stdin = new Writable({
    write(_chunk, _encoding, callback) {
      callback();
    },
  });
  const helper = new EventEmitter();
  let finished = false;
  const frame = (value: object) =>
    control.push(JSON.stringify({ version: 1, ...value }) + "\n");
  const finish = () => {
    if (finished) return;
    finished = true;
    frame({
      type: "finished",
      status: 0,
      reason: "target-exit",
      leaderReaped: true,
      groupState: "quiescent",
      errors: scenario.errors ?? [],
    });
    helper.emit("exit", 0, null);
    helper.emit("close", 0, null);
  };
  const later = (action: () => void, milliseconds: number) => {
    const timer = setTimeout(action, milliseconds);
    timers.add(timer);
  };
  let pending = "";
  const control = new Duplex({
    read() {},
    write(chunk: Buffer, _encoding, callback) {
      pending += chunk.toString("utf8");
      let boundary: number;
      while ((boundary = pending.indexOf("\n")) >= 0) {
        const value = JSON.parse(pending.slice(0, boundary)) as {
          type: string;
          deadline: number;
        };
        pending = pending.slice(boundary + 1);
        if (value.type === "start")
          process.nextTick(() => {
            frame({ type: "started", pid: 123 });
            // Model Node's exit-time resume/drain before the await continuation.
            stdout.resume();
            stderr.resume();
            for (const [index, bytes] of scenario.chunks ?? [])
              (index === 0 ? stdout : stderr).emit("data", bytes);
            if (scenario.lateChunks)
              later(() => {
                for (const [index, bytes] of scenario.lateChunks!)
                  (index === 0 ? stdout : stderr).emit("data", bytes);
                stdout.emit("end");
                stderr.emit("end");
              }, 0);
            else if (!scenario.stopChunks) {
              stdout.emit("end");
              stderr.emit("end");
            }
            scenario.acquired?.();
            if (!scenario.waitForStop) finish();
          });
        else if (value.type === "stop") {
          stops.push({ deadline: value.deadline, at: performance.now() });
          if (scenario.stopChunks) {
            for (const [index, bytes] of scenario.stopChunks)
              (index === 0 ? stdout : stderr).emit("data", bytes);
            stdout.emit("end");
            stderr.emit("end");
          }
          if (scenario.exitDelay !== undefined)
            later(
              () => frame({ type: "exited", status: 0 }),
              scenario.exitDelay,
            );
          later(finish, scenario.terminalDelay ?? 0);
        }
      }
      callback();
    },
  });
  const fake = Object.assign(helper, {
    stdout,
    stderr,
    stdin,
    stdio: [stdin, stdout, stderr, control],
    unref() {},
  });
  context.mock.method(childProcess, "spawn", () => {
    queueMicrotask(() =>
      frame({ type: "ready", clock: 10000, python: "3.13.12" }),
    );
    return fake as unknown as ReturnType<typeof childProcess.spawn>;
  });
  const signals: unknown[][] = [];
  context.mock.method(process, "kill", (...args: unknown[]) => {
    signals.push(args);
    return true;
  });
  syncBuiltinESMExports();
  try {
    await run(stops);
    assert.deepEqual(signals, []);
  } finally {
    for (const timer of timers) clearTimeout(timer);
    for (const stream of [stdin, stdout, stderr, control]) stream.destroy();
    context.mock.restoreAll();
    syncBuiltinESMExports();
  }
}

test("pure stub early owner output preserves stdout, stderr, split UTF-8 and log", async (context) => {
  const work = await mkdtemp(join(tmpdir(), "sdk-pure-output-"));
  const log = join(work, "output.log");
  try {
    await pureHelper(
      context,
      {
        chunks: [
          [0, Buffer.from("A")],
          [0, Buffer.from([0xc3])],
          [1, Buffer.from("B")],
          [0, Buffer.from([0xa9])],
          [1, Buffer.from([0xce])],
          [1, Buffer.from([0xbb])],
        ],
      },
      async () => {
        const result = await command("unused", [], { log });
        assert.equal(result.stdout, "Aé");
        assert.equal(result.output, "ABéλ");
        assert.equal(await readFile(log, "utf8"), result.output);
      },
    );
  } finally {
    await rm(work, { recursive: true, force: true });
  }
});

test("pure stub early raw-byte overflow retains cleanup and log errors", async (context) => {
  const work = await mkdtemp(join(tmpdir(), "sdk-pure-overflow-"));
  try {
    await pureHelper(
      context,
      {
        chunks: [
          [0, Buffer.from("é")],
          [1, Buffer.from("λ")],
        ],
        errors: ["group-observation-failed"],
      },
      async () => {
        await assert.rejects(
          command("unused", [], { log: work, maxOutputBytes: 3 }),
          (error: unknown) => {
            assert.ok(error instanceof AggregateError);
            assert.match(String(error.errors[0]), /3-byte output budget/);
            assert.match(
              String(error.errors[1]),
              /cleanup could not be confirmed/,
            );
            assert.match(String(error.errors[2]), /EISDIR/);
            return true;
          },
        );
      },
    );
  } finally {
    await rm(work, { recursive: true, force: true });
  }
});

test("pure stub first primary failure survives successful and late target-exit evidence", async (context) => {
  for (const first of ["timeout", "cancel", "overflow"] as const) {
    for (const late of [false, true])
      await context.test(
        `${first}-${late ? "late" : "complete"}`,
        async (nested) => {
          const controller = new AbortController();
          const reason = new Error("original pure cancellation");
          const pattern =
            first === "timeout"
              ? /timed out/
              : first === "cancel"
                ? /original pure cancellation/
                : /3-byte output budget/;
          await pureHelper(
            nested,
            {
              waitForStop: true,
              terminalDelay: late ? 280 : 10,
              ...(late ? { exitDelay: 150 } : {}),
              ...(first === "overflow"
                ? { lateChunks: [[0, Buffer.from("éλ")]] as [number, Buffer][] }
                : {
                    stopChunks: [[0, Buffer.from("éλ")]] as [number, Buffer][],
                  }),
              acquired: () => {
                if (first === "cancel")
                  setTimeout(() => controller.abort(reason), 0);
              },
            },
            async (stops) => {
              const began = performance.now();
              await assert.rejects(
                command("unused", [], {
                  timeout: first === "timeout" ? 20 : 1000,
                  cleanupTimeout: 200,
                  maxOutputBytes: 3,
                  signal: controller.signal,
                }),
                (error: unknown) => {
                  const primary =
                    error instanceof AggregateError ? error.errors[0] : error;
                  assert.match(String(primary), pattern);
                  return true;
                },
              );
              assert.equal(stops.length, 1);
              assert.ok(
                stops[0]!.deadline > 10000 && stops[0]!.deadline <= 10230,
              );
              if (late)
                assert.ok(
                  performance.now() - began < 260,
                  "A later exit must not restart the first 200ms stop allowance",
                );
            },
          );
        },
      );
  }
});

async function controlledOwner(
  context: TestContext,
  scenario: string,
  run: (trace: string) => Promise<void>,
): Promise<void> {
  const work = await mkdtemp(join(tmpdir(), "sdk-owner-protocol-"));
  const trace = join(work, "trace");
  const owner = fileURLToPath(
    new URL("../../src/system/process_owner.py", import.meta.url),
  );
  const spawn = childProcess.spawn;
  context.mock.method(childProcess, "spawn", ((
    program: string,
    args: readonly string[],
    options: SpawnOptions,
  ) =>
    spawn(
      program,
      args.at(-1) === owner
        ? [
            ...args.slice(0, -1),
            finiteFixture,
            "protocol-owner",
            scenario,
            trace,
          ]
        : [...args],
      options,
    )) as typeof spawn);
  syncBuiltinESMExports();
  let complete = false;
  try {
    await run(trace);
    complete = true;
  } finally {
    context.mock.restoreAll();
    syncBuiltinESMExports();
    if (complete) await rm(work, { recursive: true, force: true });
    else console.error(`Controlled owner evidence retained at ${work}`);
  }
}

test("helper startup consumes the original command deadline and never starts after it", async (context) => {
  await controlledOwner(context, "late-ready", async (trace) => {
    const began = performance.now();
    await assert.rejects(
      startProcess("unused", [], { timeout: 40, cleanupTimeout: 250 }),
      /startup timed out/,
    );
    assert.equal(await readFile(trace, "utf8"), "");
    assert.ok(performance.now() - began < 290);
  });
});

test("control transit consumes the first stop budget and repeated failure is cached", async (context) => {
  await controlledOwner(context, "stop-budget", async (trace) => {
    const child = await startProcess("unused", [], {
      timeout: 1000,
      cleanupTimeout: 200,
    });
    const began = performance.now();
    const stopped = child.close();
    assert.equal(child.close(), stopped);
    await assert.rejects(stopped, /cleanup could not be confirmed/);
    assert.equal(child.close(), stopped);
    const observation = JSON.parse(await readFile(trace, "utf8")) as {
      remaining: number;
    };
    assert.ok(
      observation.remaining < 160,
      "Control transit must consume the original 200 ms",
    );
    assert.ok(performance.now() - began < 200);
  });
});

test("cancellation before helper readiness never submits a target", async (context) => {
  await controlledOwner(context, "late-ready", async (trace) => {
    const controller = new AbortController();
    const reason = new Error("cancel before readiness");
    const timer = setTimeout(() => controller.abort(reason), 20);
    try {
      await assert.rejects(
        startProcess("unused", [], {
          signal: controller.signal,
          timeout: 500,
          cleanupTimeout: 250,
        }),
        (error: unknown) => error === reason,
      );
      assert.equal(await readFile(trace, "utf8"), "");
    } finally {
      clearTimeout(timer);
    }
  });
});

test("cancellation during handoff rejects construction and retains cleanup failure", async (context) => {
  await controlledOwner(context, "handoff-abort", async (trace) => {
    const controller = new AbortController();
    const reason = new Error("cancel during handoff");
    const starting = startProcess("unused", [], {
      signal: controller.signal,
      timeout: 1000,
      cleanupTimeout: 250,
    });
    void starting.catch(() => {});
    try {
      const deadline = performance.now() + 500;
      let submitted = false;
      while (performance.now() < deadline) {
        try {
          await readFile(trace);
          submitted = true;
          break;
        } catch {
          await delay(5);
        }
      }
      assert.ok(submitted, "Controlled owner did not receive START");
      controller.abort(reason);
      await assert.rejects(starting, (error: unknown) => {
        assert.ok(error instanceof AggregateError);
        assert.equal(error.errors[0], reason);
        assert.match(String(error.errors[1]), /cleanup could not be confirmed/);
        return true;
      });
    } finally {
      controller.abort(reason);
      await starting
        .then(
          (child) => child.close(),
          () => {},
        )
        .catch(() => {});
    }
  });
});

test("missing capabilities and malformed control refuse without a target", async (context) => {
  await controlledOwner(context, "refuse", async () => {
    await assert.rejects(startProcess("unused", []), /pinned Python 3.13/);
  });
  await controlledOwner(context, "invalid-utf8", async () => {
    await assert.rejects(startProcess("unused", []), /encoded data|UTF/);
  });
});

test(
  "lost control fails within cleanup budget while unconfirmed resources stay held",
  { timeout: 7000 },
  async (context) => {
    await controlledOwner(context, "lost-control", async (trace) => {
      const child = await startProcess("unused", [], {
        timeout: 2000,
        cleanupTimeout: 200,
      });
      context.mock.restoreAll();
      syncBuiltinESMExports();
      const began = performance.now();
      await withResources(
        async () => {
          await assert.rejects(child.result, /control|cleanup/i);
          assert.ok(
            performance.now() - began < 350,
            "Lost control must not wait for a fresh execution timeout",
          );
          const metadata = JSON.parse(await readFile(trace, "utf8")) as {
            target: number;
          };
          const observation = await command("ps", ["-axo", "pid=,stat="]);
          assert.ok(
            observation.stdout.split("\n").some((line) => {
              const [pid, state] = line.trim().split(/\s+/);
              return (
                Number(pid) === metadata.target &&
                state &&
                !state.startsWith("Z")
              );
            }),
            "Missing control evidence must not be represented as released resources",
          );
        },
        async () => {
          const deadline = performance.now() + 6000;
          while (performance.now() < deadline) {
            try {
              await readFile(trace + ".recovered");
              return;
            } catch {
              await delay(10);
            }
          }
          throw new Error(
            "Independent fixture waiter did not confirm recovery",
          );
        },
      );
    });
  },
);

test(
  "Node controller death leaves missing owner evidence while the helper stops its target",
  { timeout: 5000 },
  async () => {
    const work = await mkdtemp(join(tmpdir(), "sdk-owner-node-death-"));
    const controller = join(work, "controller.mts");
    const ready = join(work, "ready.json");
    const receipt = join(work, "owner-receipt.json");
    const source = pathToFileURL(
      fileURLToPath(new URL("../../src/system/process.ts", import.meta.url)),
    ).href;
    const loader = fileURLToPath(
      new URL("../../node_modules/tsx/dist/loader.mjs", import.meta.url),
    );
    await writeFile(
      controller,
      [
        `import {startProcess, command} from ${JSON.stringify(source)};`,
        'import {writeFile} from "node:fs/promises";',
        `const child = await startProcess("python3", ["-B", ${JSON.stringify(finiteFixture)}, "wait"], {timeout:3000,cleanupTimeout:500});`,
        'const parent = await command("ps", ["-p", String(child.pid), "-o", "ppid="], {timeout:500});',
        `await writeFile(${JSON.stringify(ready)}, JSON.stringify({target:child.pid,helper:Number(parent.stdout.trim())}));`,
        "await child.result;",
        `await writeFile(${JSON.stringify(receipt)}, "complete");`,
      ].join("\n"),
    );
    let observed = false;
    try {
      await assert.rejects(
        command(process.execPath, ["--import", loader, controller], {
          timeout: 1000,
          cleanupTimeout: 500,
          env: { NODE_TEST_CONTEXT: undefined },
        }),
        /timed out/,
      );
      const processes = JSON.parse(await readFile(ready, "utf8")) as {
        target: number;
        helper: number;
      };
      await assert.rejects(readFile(receipt), { code: "ENOENT" });
      const deadline = performance.now() + 1000;
      while (performance.now() < deadline) {
        const state = await command("ps", ["-axo", "pid=,stat="]);
        const live = state.stdout.split("\n").some((line) => {
          const [pid, status] = line.trim().split(/\s+/);
          return (
            [processes.target, processes.helper].includes(Number(pid)) &&
            status &&
            !status.startsWith("Z")
          );
        });
        if (!live) {
          observed = true;
          break;
        }
        await delay(10);
      }
      assert.ok(
        observed,
        "EOF cleanup must stop executable work before the four-second fuse",
      );
      // Observation reconciles the physical fixture. It does not create the lost
      // controller's missing owner-completion receipt or make its timeout green.
    } finally {
      if (observed) await rm(work, { recursive: true, force: true });
      else console.error(`Node-death fixture remains unresolved at ${work}`);
    }
  },
);

test("an owned finite target starts and closes before its safety fuse", async () => {
  const child = await startProcess("python3", ["-B", finiteFixture, "wait"], {
    timeout: 1000,
    cleanupTimeout: 300,
  });
  try {
    assert.ok(child.pid > 0);
  } finally {
    await child.close();
  }
});

test("a reaped child never authorizes a numeric signal", async (context) => {
  const signals: unknown[][] = [];
  context.mock.method(process, "kill", (...args: unknown[]) => {
    signals.push(args);
    return true;
  });
  const reaped = {
    pid: 123,
    exitCode: 0,
    signalCode: null,
  } as unknown as OwnedProcess;

  await assert.rejects(stopProcess(reaped), /not an owned process/);

  assert.deepEqual(signals, []);
});

test("commands preserve stdin, split UTF-8 and a nonzero target result", async () => {
  assert.equal(
    (
      await command("python3", ["-B", finiteFixture, "echo"], {
        input: "hello é",
      })
    ).stdout,
    "hello é",
  );
  assert.equal(
    (await command("python3", ["-B", finiteFixture, "split-utf8"])).stdout,
    "é",
  );
  await assert.rejects(
    command("python3", ["-c", "raise SystemExit(2)"]),
    /exited 2/,
  );
});

test("log failure retains a nonzero command result", async () => {
  const work = await mkdtemp(join(tmpdir(), "sdk-owner-log-"));
  try {
    await assert.rejects(
      command("python3", ["-c", "raise SystemExit(2)"], { log: work }),
      (error: unknown) => {
        assert.ok(error instanceof AggregateError);
        assert.match(String(error.errors[0]), /exited 2/);
        assert.match(String(error.errors[1]), /EISDIR/);
        return true;
      },
    );
  } finally {
    await rm(work, { recursive: true, force: true });
  }
});

test("timeouts and output overflow stop finite targets before their fuse", async () => {
  await assert.rejects(
    command("python3", ["-B", finiteFixture, "wait"], {
      timeout: 150,
      cleanupTimeout: 500,
    }),
    /timed out/,
  );
  await assert.rejects(
    command("python3", ["-B", finiteFixture, "noisy"], {
      maxOutputBytes: 1024,
      cleanupTimeout: 500,
    }),
    /output budget/,
  );
});

test("same-group descendants stop after an early leader exit with open or closed pipes", async () => {
  const work = await mkdtemp(join(tmpdir(), "sdk-owner-tree-"));
  try {
    for (const pipes of ["open", "closed"]) {
      const began = performance.now();
      const marker = join(work, pipes);
      await command("python3", ["-B", finiteFixture, "leader", marker, pipes], {
        timeout: 2000,
        cleanupTimeout: 600,
      });
      assert.ok(Number(await readFile(marker, "utf8")) > 0);
      assert.ok(
        performance.now() - began < 2000,
        "Owner cleanup must finish before the four-second fuse",
      );
    }
  } finally {
    await rm(work, { recursive: true, force: true });
  }
});

test("cancellation of an acquired target retains its reason and cached cleanup", async () => {
  const work = await mkdtemp(join(tmpdir(), "sdk-owner-cancel-"));
  const marker = join(work, "ready");
  const controller = new AbortController();
  const running = command("python3", ["-B", finiteFixture, "wait", marker], {
    signal: controller.signal,
    cleanupTimeout: 500,
  });
  void running.catch(() => {});
  try {
    const deadline = performance.now() + 1000;
    let ready = false;
    while (performance.now() < deadline) {
      try {
        await readFile(marker);
        ready = true;
        break;
      } catch {
        await delay(5);
      }
    }
    assert.ok(ready, "Finite target did not announce acquisition");
    controller.abort(new Error("cancel acquired target"));
    await assert.rejects(running, /cancel acquired target/);
  } finally {
    controller.abort();
    await running.catch(() => {});
    await rm(work, { recursive: true, force: true });
  }
  const child = await startProcess("python3", ["-B", finiteFixture, "wait"], {
    cleanupTimeout: 500,
  });
  const first = child.close();
  assert.equal(child.close(), first);
  await first;
});

test("cancellation still finishes descendants after their leader has exited", async () => {
  const work = await mkdtemp(join(tmpdir(), "sdk-owner-orphan-cancel-"));
  const marker = join(work, "descendant");
  const controller = new AbortController();
  const running = command(
    "python3",
    ["-B", finiteFixture, "leader", marker, "closed"],
    {
      signal: controller.signal,
      timeout: 2000,
      cleanupTimeout: 1000,
    },
  );
  void running.catch(() => {});
  let complete = false;
  try {
    let exited = false;
    const deadline = performance.now() + 1000;
    while (performance.now() < deadline) {
      try {
        await readFile(marker + ".orphaned");
        exited = true;
        break;
      } catch {
        await delay(5);
      }
    }
    assert.ok(
      exited,
      "Descendant must observe the leader's exit before cancellation",
    );
    controller.abort(new Error("cancel orphaned descendant"));
    await assert.rejects(running, /cancel orphaned descendant/);
    complete = true;
  } finally {
    controller.abort();
    await running.catch(() => {});
    if (complete) await rm(work, { recursive: true, force: true });
    else console.error(`Orphan cancellation evidence retained at ${work}`);
  }
});

test("a crashed backend target remains a failure after confirmed resource cleanup", async () => {
  const child = await startProcess("python3", ["-c", "raise SystemExit(2)"]);
  await child.result;
  await assert.rejects(stopProcess(child), /exited 2/);
});

test(
  "queued close preserves a real already-exited target before the helper observes it",
  { timeout: 3000 },
  async (context) => {
    const work = await mkdtemp(join(tmpdir(), "sdk-owner-ordered-exit-"));
    const trace = join(work, "ordering.json");
    const owner = fileURLToPath(
      new URL("../../src/system/process_owner.py", import.meta.url),
    );
    const spawn = childProcess.spawn;
    context.mock.method(childProcess, "spawn", ((
      program: string,
      args: readonly string[],
      options: SpawnOptions,
    ) =>
      spawn(
        program,
        args.at(-1) === owner
          ? [
              ...args.slice(0, -1),
              finiteFixture,
              "ordered-exit-owner",
              owner,
              trace,
            ]
          : [...args],
        options,
      )) as typeof spawn);
    syncBuiltinESMExports();
    let child: OwnedProcess | undefined;
    let confirmed = false;
    const began = performance.now();
    try {
      child = await startProcess("python3", ["-B", finiteFixture, "exit-two"], {
        timeout: 1000,
        cleanupTimeout: 500,
      });
      // Do not await result: STOP must win the helper's normal observation turn.
      await assert.rejects(stopProcess(child), /exited 2/);
      const outcome = await child.result;
      assert.deepEqual(outcome, {
        status: 2,
        reason: "target-exit",
        leaderReaped: true,
        groupState: "quiescent",
        errors: [],
      });
      const ordering = JSON.parse(await readFile(trace, "utf8")) as {
        queuedStop: string;
        observedExit: number;
        stopDeadline: number;
        observedAt: number;
        ownerResult: number;
        returncodes: number[];
      };
      assert.equal(ordering.queuedStop, "close");
      assert.equal(ordering.observedExit, 2);
      assert.ok(ordering.observedAt < ordering.stopDeadline);
      assert.equal(ordering.ownerResult, 0);
      assert.deepEqual(ordering.returncodes, [2]);
      assert.ok(
        performance.now() - began < 1000,
        "Production ownership evidence must precede both four-second fixture fuses",
      );
      confirmed = true;
    } finally {
      try {
        await child?.close();
      } finally {
        context.mock.restoreAll();
        syncBuiltinESMExports();
        if (confirmed) await rm(work, { recursive: true, force: true });
        else console.error(`Ordered-exit fixture evidence remains at ${work}`);
      }
    }
  },
);

test("the Python owner syscall and control regressions pass independently", async () => {
  const home = fileURLToPath(new URL("../..", import.meta.url));
  const result = await command(
    "python3",
    ["-B", "-m", "unittest", "tests.unit.process_owner_test"],
    {
      cwd: home,
      timeout: 5000,
    },
  );
  assert.match(result.output, /\bOK\b/);
});

test("cleanup preserves the original failure and the cleanup failure", async () => {
  await assert.rejects(
    withResources(
      async () => {
        throw new Error("assertion failed");
      },
      async () => {
        throw new Error("cleanup failed");
      },
    ),
    (error: unknown) => {
      assert.ok(error instanceof AggregateError);
      assert.deepEqual(error.errors.map(String), [
        "Error: assertion failed",
        "Error: cleanup failed",
      ]);
      return true;
    },
  );
});

test("cleanup failure cannot turn a successful run green", async () => {
  await assert.rejects(
    withResources(
      async () => "passed",
      async () => {
        throw new Error("cleanup failed");
      },
    ),
    /cleanup failed/,
  );
});
