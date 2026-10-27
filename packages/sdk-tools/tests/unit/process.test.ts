import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import test from "node:test";
import { mkdtemp, rm } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import {
  command,
  kill,
  stopProcess,
  withResources,
} from "../../src/system/process.ts";

test("a log-write error retains the command failure rather than replacing it", async () => {
  const directory = await mkdtemp(join(tmpdir(), "sdk-log-failure-"));
  try {
    await assert.rejects(
      command(process.execPath, ["-e", "process.exit(2)"], { log: directory }),
      (error) => {
        assert.ok(error instanceof AggregateError);
        assert.match(String(error.errors[0]), /exited 2/);
        assert.match(String(error.errors[1]), /EISDIR/);
        return true;
      },
    );
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

test("commands preserve stdin/stdout and reject nonzero or timed-out processes", async () => {
  const result = await command(
    process.execPath,
    ["-e", "process.stdin.pipe(process.stdout)"],
    { input: "hello" },
  );
  assert.equal(result.stdout, "hello");
  await assert.rejects(
    command(process.execPath, ["-e", "process.exit(2)"]),
    /exited 2/,
  );
  await assert.rejects(
    command(process.execPath, ["-e", "setInterval(()=>{},1000)"], {
      timeout: 60,
    }),
    /timed out/,
  );
});

test("cancellation terminates a running process instead of leaving it detached", async () => {
  const controller = new AbortController();
  const running = command(
    process.execPath,
    ["-e", "setInterval(()=>{},1000)"],
    { signal: controller.signal },
  );
  setTimeout(() => controller.abort(new Error("review interrupted")), 50);
  await assert.rejects(running, /interrupted|abort/i);
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
      assert.match(error.message, /cleanup/);
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

test("a crashed backend is not successful cleanup", async () => {
  const child = spawn(process.execPath, ["-e", "process.exit(2)"], {
    stdio: "ignore",
  });
  await new Promise<void>((resolve) => child.once("close", () => resolve()));
  await assert.rejects(stopProcess(child), /exited 2/);
});

test("cancellation removes same-group descendants even after the leader exits", async () => {
  const directory = await mkdtemp(join(tmpdir(), "sdk-descendant-proof-"));
  const marker = join(directory, "pid");
  const { readFile } = await import("node:fs/promises");
  const controller = new AbortController();
  const descendant =
    "process.on('SIGTERM',()=>{}); require('node:fs').writeFileSync(process.argv[1], String(process.pid)); setInterval(()=>{},1000)";
  const leader = `require('node:child_process').spawn(process.execPath,['-e',${JSON.stringify(descendant)},process.argv[1]],{stdio:'ignore'}); setInterval(()=>{},1000)`;
  let pid: number | undefined;
  try {
    const running = command(process.execPath, ["-e", leader, marker], {
      signal: controller.signal,
    });
    for (let attempt = 0; attempt < 100; attempt++) {
      try {
        pid = Number(await readFile(marker, "utf8"));
        break;
      } catch {
        await new Promise((resolve) => setTimeout(resolve, 10));
      }
    }
    assert.ok(pid, "Descendant did not announce readiness");
    controller.abort(new Error("cancel descendants"));
    await assert.rejects(running, /cancel descendants/);
    // Allow the OS to reap a descendant killed during command cleanup.
    for (let attempt = 0; attempt < 100; attempt++) {
      try {
        process.kill(pid, 0);
      } catch {
        return;
      }
      await new Promise((resolve) => setTimeout(resolve, 10));
    }
    assert.fail("Descendant outlived cancelled command");
  } finally {
    if (pid) {
      try {
        process.kill(pid, "SIGKILL");
      } catch {}
    }
    await rm(directory, { recursive: true, force: true });
  }
});

test("a noisy command fails within a bounded output budget", async () => {
  await assert.rejects(
    command(
      process.execPath,
      [
        "-e",
        "process.stdout.write('x'.repeat(1000000)); setInterval(()=>{},1000)",
      ],
      { maxOutputBytes: 1024 },
    ),
    /output budget/,
  );
});

test("protocol stdout preserves UTF-8 characters split across pipe chunks", async () => {
  const result = await command(process.execPath, [
    "-e",
    "process.stdout.write(Buffer.from([0xc3])); setTimeout(()=>process.stdout.write(Buffer.from([0xa9])),30)",
  ]);
  assert.equal(result.stdout, "é");
});

test("an uninspectable already-empty process group does not replace successful execution", async (context) => {
  const original = process.kill.bind(process);
  context.mock.method(
    process,
    "kill",
    (pid: number, signal?: number | NodeJS.Signals) => {
      if (pid < 0)
        throw Object.assign(new Error("empty group denied by OS"), {
          code: "EPERM",
        });
      return original(pid, signal);
    },
  );
  const result = await command(process.execPath, [
    "-e",
    "process.stdout.write('done')",
  ]);
  assert.equal(result.stdout, "done");
});

test("a denied signal to a live owned group remains a cleanup failure", async (context) => {
  const child = spawn(process.execPath, ["-e", "setInterval(()=>{},1000)"], {
    detached: true,
    stdio: "ignore",
  });
  await new Promise<void>((resolve, reject) => {
    child.once("spawn", resolve);
    child.once("error", reject);
  });
  const pid = child.pid;
  assert.ok(pid);
  const original = process.kill.bind(process);
  context.mock.method(
    process,
    "kill",
    (target: number, signal?: number | NodeJS.Signals) => {
      if (target === -pid)
        throw Object.assign(new Error("live group denied"), { code: "EPERM" });
      return original(target, signal);
    },
  );
  try {
    assert.throws(() => kill(child), /live group denied/);
  } finally {
    context.mock.restoreAll();
    const ended = new Promise<void>((resolve) =>
      child.once("close", () => resolve()),
    );
    original(-pid, "SIGKILL");
    await ended;
  }
});

test("denied cancellation rejects normally and preserves cleanup failures", async (context) => {
  const { readFile } = await import("node:fs/promises");
  const directory = await mkdtemp(join(tmpdir(), "sdk-denied-cancel-"));
  const marker = join(directory, "pid");
  const controller = new AbortController();
  const original = process.kill.bind(process);
  let pid: number | undefined;
  let deadlineTimer: ReturnType<typeof setTimeout> | undefined;
  const running = command(
    process.execPath,
    [
      "-e",
      "require('node:fs').writeFileSync(process.argv[1],String(process.pid));setInterval(()=>{},1000)",
      marker,
    ],
    { signal: controller.signal, cleanupTimeout: 20 },
  );
  void running.catch(() => {});
  try {
    for (let attempt = 0; attempt < 100; attempt++) {
      try {
        pid = Number(await readFile(marker, "utf8"));
        break;
      } catch {
        await new Promise((resolve) => setTimeout(resolve, 10));
      }
    }
    assert.ok(pid);
    const target = pid;
    context.mock.method(
      process,
      "kill",
      (value: number, signal?: number | NodeJS.Signals) => {
        if (value === -target && signal !== 0)
          throw Object.assign(new Error("owned group denied"), {
            code: "EPERM",
          });
        return original(value, signal);
      },
    );
    controller.abort(new Error("cancel denied group"));
    const deadline = new Promise<never>((_resolve, reject) => {
      deadlineTimer = setTimeout(
        () => reject(new Error("Denied cancellation did not settle")),
        2000,
      );
    });
    await assert.rejects(
      Promise.race([running, deadline]),
      (error: unknown) => {
        assert.ok(error instanceof AggregateError);
        assert.match(String(error.errors[0]), /cancel denied group/);
        assert.match(String(error.errors[1]), /cleanup|denied/i);
        return true;
      },
    );
  } finally {
    clearTimeout(deadlineTimer);
    context.mock.restoreAll();
    if (pid) {
      try {
        original(-pid, "SIGKILL");
      } catch {}
    }
    await rm(directory, { recursive: true, force: true });
  }
});

test("an empty denied group still falls back to the live attached child", async (context) => {
  const child = spawn(process.execPath, ["-e", "setInterval(()=>{},1000)"], {
    detached: false,
    stdio: "ignore",
  });
  await new Promise<void>((resolve, reject) => {
    child.once("spawn", resolve);
    child.once("error", reject);
  });
  const pid = child.pid;
  assert.ok(pid);
  const original = process.kill.bind(process);
  context.mock.method(
    process,
    "kill",
    (target: number, signal?: NodeJS.Signals | number) => {
      if (target === -pid)
        throw Object.assign(new Error("empty attached group denied"), {
          code: "EPERM",
        });
      return original(target, signal);
    },
  );
  try {
    await stopProcess(child);
    assert.ok(child.signalCode);
  } finally {
    context.mock.restoreAll();
    try {
      original(pid, "SIGKILL");
    } catch {}
  }
});
