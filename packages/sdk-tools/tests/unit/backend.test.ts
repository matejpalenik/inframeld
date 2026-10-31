import assert from "node:assert/strict";
import { createServer } from "node:http";
import test, { type TestContext } from "node:test";
import {
  controlJson,
  startBackend,
  type Backend,
} from "../../src/conformance/backend.ts";
import childProcess, { type SpawnOptions } from "node:child_process";
import { syncBuiltinESMExports } from "node:module";
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { setTimeout as delay } from "node:timers/promises";
import { EventEmitter } from "node:events";
import { Duplex, PassThrough, Writable } from "node:stream";

/** A ready backend produces its only output in response to the first STOP. */
async function shutdownOutput(
  context: TestContext,
  scenario: { overflow: boolean; cleanupError: boolean; logError: boolean },
  run: (backend: Backend, work: string) => Promise<void>,
): Promise<void> {
  const work = await mkdtemp(join(tmpdir(), "sdk-pure-backend-close-"));
  const stdout = new PassThrough();
  const stderr = new PassThrough();
  const stdin = new Writable({
    write(_chunk, _encoding, callback) {
      callback();
    },
  });
  const helper = new EventEmitter();
  let pending = "";
  let stops = 0;
  const frame = (value: object) =>
    control.push(JSON.stringify({ version: 1, ...value }) + "\n");
  const control = new Duplex({
    read() {},
    write(chunk: Buffer, _encoding, callback) {
      pending += chunk.toString("utf8");
      let boundary: number;
      while ((boundary = pending.indexOf("\n")) >= 0) {
        const value = JSON.parse(pending.slice(0, boundary)) as {
          type: string;
        };
        pending = pending.slice(boundary + 1);
        if (value.type === "start")
          process.nextTick(() => frame({ type: "started", pid: 123 }));
        else if (value.type === "stop") {
          stops++;
          stdout.emit(
            "data",
            scenario.overflow
              ? Buffer.alloc(4 * 1024 * 1024 + 1, 120)
              : Buffer.from("stopped"),
          );
          stdout.emit("end");
          stderr.emit("end");
          frame({
            type: "finished",
            status: 0,
            reason: "close",
            leaderReaped: true,
            groupState: scenario.cleanupError ? "unknown" : "quiescent",
            errors: scenario.cleanupError ? ["group-observation-failed"] : [],
          });
          helper.emit("exit", scenario.cleanupError ? 1 : 0, null);
          helper.emit("close", scenario.cleanupError ? 1 : 0, null);
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
  context.mock.method(globalThis, "fetch", async () =>
    Response.json({ ready: true }),
  );
  const signals: unknown[][] = [];
  context.mock.method(process, "kill", (...args: unknown[]) => {
    signals.push(args);
    return true;
  });
  syncBuiltinESMExports();
  let backend: Backend | undefined;
  try {
    await writeFile(join(work, "address"), "http://controlled.invalid");
    if (scenario.logError) await mkdir(join(work, "backend.log"));
    backend = await startBackend(work, undefined, undefined, 500);
    assert.equal(stops, 0);
    await run(backend, work);
    assert.equal(stops, 1);
    assert.deepEqual(signals, []);
  } finally {
    try {
      await backend?.close().catch(() => {});
    } finally {
      for (const stream of [stdin, stdout, stderr, control]) stream.destroy();
      context.mock.restoreAll();
      syncBuiltinESMExports();
      await rm(work, { recursive: true, force: true });
    }
  }
}

test("pure stub backend close retains STOP-time overflow and independent failures", async (context) => {
  for (const scenario of [
    {
      name: "healthy stop",
      overflow: false,
      cleanupError: false,
      logError: false,
    },
    {
      name: "overflow with successful cleanup",
      overflow: true,
      cleanupError: false,
      logError: false,
    },
    {
      name: "overflow and cleanup failure",
      overflow: true,
      cleanupError: true,
      logError: false,
    },
    {
      name: "overflow, cleanup and log failures",
      overflow: true,
      cleanupError: true,
      logError: true,
    },
  ])
    await context.test(scenario.name, async (nested) => {
      await shutdownOutput(nested, scenario, async (backend, work) => {
        const closing = backend.close();
        assert.equal(backend.close(), closing);
        if (!scenario.overflow) await closing;
        else
          await assert.rejects(closing, (error: unknown) => {
            const details = (value: unknown): string =>
              value instanceof AggregateError
                ? value.errors.map(details).join("\n")
                : String(value);
            const message = details(error);
            assert.match(message, /Backend exceeded its 4 MiB output budget/);
            if (scenario.cleanupError)
              assert.match(message, /cleanup could not be confirmed/);
            if (scenario.logError) assert.match(message, /EISDIR/);
            return true;
          });
        assert.equal(backend.close(), closing);
        if (!scenario.logError) {
          const log = await readFile(join(work, "backend.log"), "utf8");
          if (scenario.overflow)
            assert.ok(Buffer.byteLength(log) <= 4 * 1024 * 1024 + 64);
          else assert.equal(log, "stopped");
        }
      });
    });
});

test("pure stub backend retains early output and raw-byte overflow before acquisition", async (context) => {
  for (const overflow of [false, true])
    await context.test(
      overflow ? "overflow" : "UTF-8 diagnostics",
      async (nested) => {
        const work = await mkdtemp(join(tmpdir(), "sdk-pure-backend-"));
        const stdout = new PassThrough();
        const stderr = new PassThrough();
        const stdin = new Writable({
          write(_chunk, _encoding, callback) {
            callback();
          },
        });
        const helper = new EventEmitter();
        let pending = "";
        const frame = (value: object) =>
          control.push(JSON.stringify({ version: 1, ...value }) + "\n");
        const control = new Duplex({
          read() {},
          write(chunk: Buffer, _encoding, callback) {
            pending += chunk.toString("utf8");
            if (pending.includes("\n")) {
              const value = JSON.parse(pending.trim()) as { type: string };
              pending = "";
              if (value.type === "start")
                process.nextTick(() => {
                  frame({ type: "started", pid: 123 });
                  stdout.resume();
                  stderr.resume();
                  for (const bytes of overflow
                    ? [Buffer.alloc(4 * 1024 * 1024 + 1, 120)]
                    : [
                        Buffer.from("B"),
                        Buffer.from([0xc3]),
                        Buffer.from([0xa9]),
                      ])
                    stdout.emit("data", bytes);
                  for (const bytes of [
                    Buffer.from("E"),
                    Buffer.from([0xce]),
                    Buffer.from([0xbb]),
                  ])
                    stderr.emit("data", bytes);
                  stdout.emit("end");
                  stderr.emit("end");
                  frame({
                    type: "finished",
                    status: 2,
                    reason: "target-exit",
                    leaderReaped: true,
                    groupState: "quiescent",
                    errors: [],
                  });
                  helper.emit("exit", 0, null);
                  helper.emit("close", 0, null);
                });
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
        nested.mock.method(childProcess, "spawn", () => {
          queueMicrotask(() =>
            frame({ type: "ready", clock: 10000, python: "3.13.12" }),
          );
          return fake as unknown as ReturnType<typeof childProcess.spawn>;
        });
        const signals: unknown[][] = [];
        nested.mock.method(process, "kill", (...args: unknown[]) => {
          signals.push(args);
          return true;
        });
        syncBuiltinESMExports();
        try {
          await assert.rejects(
            startBackend(work, undefined, undefined, 500),
            (error: unknown) => {
              assert.ok(error instanceof AggregateError);
              assert.match(
                String(error.errors[0]),
                overflow
                  ? /Backend exceeded its 4 MiB output budget/
                  : /Backend exited before readiness: BéEλ/,
              );
              const details = (value: unknown): string =>
                value instanceof AggregateError
                  ? value.errors.map(details).join("\n")
                  : String(value);
              assert.match(details(error.errors[1]), /Backend exited 2/);
              return true;
            },
          );
          const log = await readFile(join(work, "backend.log"), "utf8");
          if (overflow)
            assert.ok(Buffer.byteLength(log) <= 4 * 1024 * 1024 + 64);
          else assert.equal(log, "BéEλ");
          assert.deepEqual(signals, []);
        } finally {
          for (const stream of [stdin, stdout, stderr, control])
            stream.destroy();
          nested.mock.restoreAll();
          syncBuiltinESMExports();
          await rm(work, { recursive: true, force: true });
        }
      },
    );
});

test("backend ownership rejects cancellation before acquiring a target", async () => {
  const controller = new AbortController();
  controller.abort(new Error("cancel before backend acquisition"));
  await assert.rejects(
    startBackend("unused", undefined, controller.signal),
    /cancel before backend acquisition/,
  );
});

test("backend ownership preserves fractional remaining readiness deadlines", async (context) => {
  context.mock.method(globalThis, "fetch", async () =>
    Response.json({ ready: true }),
  );
  assert.deepEqual(await controlJson("http://controlled.invalid", {}, 1.5), {
    ready: true,
  });
});

test("backend ownership closes an acquired finite target on startup cancellation", async (context) => {
  const work = await mkdtemp(join(tmpdir(), "sdk-backend-owner-"));
  const marker = join(work, "target-ready");
  const fixture = fileURLToPath(
    new URL("./fixtures/process_tree.py", import.meta.url),
  );
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
        ? [...args.slice(0, -1), fixture, "backend-owner", owner, marker]
        : [...args],
      options,
    )) as typeof spawn);
  syncBuiltinESMExports();
  const controller = new AbortController();
  const starting = startBackend(work, undefined, controller.signal, 1000);
  void starting.catch(() => {});
  try {
    let acquired = false;
    const deadline = performance.now() + 1000;
    while (performance.now() < deadline) {
      try {
        await readFile(marker);
        acquired = true;
        break;
      } catch {
        await delay(5);
      }
    }
    assert.ok(acquired, "Finite backend target was not acquired");
    const stoppedAt = performance.now();
    controller.abort(new Error("cancel acquired backend"));
    await assert.rejects(starting, /cancel acquired backend/);
    assert.ok(
      performance.now() - stoppedAt < 1000,
      "Backend must close before its four-second fuse",
    );
  } finally {
    controller.abort();
    await starting.catch(() => {});
    context.mock.restoreAll();
    syncBuiltinESMExports();
    await rm(work, { recursive: true, force: true });
  }
});

test("a stalled control response has a deadline and does not hang readiness", async () => {
  const server = createServer(() => {});
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  assert.ok(address && typeof address !== "string");
  try {
    await assert.rejects(
      controlJson(`http://127.0.0.1:${address.port}`, {}, 50),
      /timeout/i,
    );
  } finally {
    server.closeAllConnections();
    await new Promise<void>((resolve) => server.close(() => resolve()));
  }
});
