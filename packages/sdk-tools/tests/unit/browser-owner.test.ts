import assert from "node:assert/strict";
import { mkdtemp, rm, writeFile, readFile, lstat } from "node:fs/promises";
import { tmpdir } from "node:os";
import { isAbsolute, join } from "node:path";
import test from "node:test";
import { createHash } from "node:crypto";
import {
  BrowserFixtureOwner,
  connectBrowserCase,
  superviseBrowserWorker,
  expectedStalledCloseFailure,
  acquireBrowserFixtureDirectory,
  type BrowserLease,
  type FixtureChannel,
  type FixtureClock,
} from "../native/fixtures/browser-owner.ts";
import { FixtureDiagnostics } from "../native/fixtures/fixture-diagnostics.ts";

function pending<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  void promise.catch(() => {});
  return { promise, resolve, reject };
}

test(
  "pure fixture diagnostics starts recovery before blocked publication and retains both failures",
  { timeout: 5000 },
  async (context) => {
    const h = browserHarness(),
      diagnostics = new FixtureDiagnostics("broker"),
      blocked = pending<void>();
    const order: string[] = [],
      primary = new Error("controlled worker failure"),
      publication = new Error("controlled publication failure");
    context.mock.method(h.owner, "stop", async () => {
      order.push("recovery");
    });
    const result = superviseBrowserWorker(
      h.owner,
      async () => {
        throw primary;
      },
      () =>
        diagnostics.write("/unused", async () => {
          order.push("diagnostic");
          await blocked.promise;
        }),
      h.clock,
    );
    void result.catch(() => {});
    try {
      await browserTicks();
      assert.deepEqual(order, ["recovery", "diagnostic"]);
      blocked.reject(publication);
      await assert.rejects(result, (error) => {
        assert.ok(error instanceof AggregateError);
        assert.deepEqual(error.errors, [primary, publication]);
        return true;
      });
    } finally {
      blocked.resolve();
      await result.catch(() => {});
    }
  },
);

class ManualBrowserClock implements FixtureClock {
  time = 100;
  next = 0;
  timers = new Map<number, { at: number; action: () => void }>();
  now() {
    return this.time;
  }
  set(milliseconds: number, action: () => void) {
    const id = ++this.next;
    this.timers.set(id, { at: this.time + milliseconds, action });
    return id;
  }
  clear(timer: unknown) {
    if (typeof timer === "number") this.timers.delete(timer);
  }
  advance(milliseconds: number) {
    const end = this.time + milliseconds;
    while (true) {
      const next = [...this.timers]
        .filter(([, timer]) => timer.at <= end)
        .sort((a, b) => a[1].at - b[1].at)[0];
      if (!next) break;
      this.time = next[1].at;
      this.timers.delete(next[0]);
      next[1].action();
    }
    this.time = end;
  }
}

async function browserTicks() {
  for (let n = 0; n < 12; n++) await Promise.resolve();
}

function browserHarness(
  caseId = "startup-cancel",
  blocked = false,
  diagnostics?: FixtureDiagnostics,
) {
  const clock = new ManualBrowserClock();
  const messages: Record<string, unknown>[] = [];
  const calls: {
    method: string;
    channel?: "chromium";
    headless?: true;
    timeout?: number;
  }[] = [];
  const launched = pending<BrowserLease>();
  const close = pending<void>(),
    kill = pending<void>(),
    closed = pending<void>();
  const lease: BrowserLease = {
    api: {
      wsEndpoint: () => "ws://owned.invalid/browser",
      close: () => {
        calls.push({ method: "close" });
        return close.promise;
      },
      kill: () => {
        calls.push({ method: "kill" });
        return kill.promise;
      },
    },
    closed: closed.promise,
  };
  let input: (bytes: Uint8Array) => void = () => {};
  let ended: () => void = () => {};
  let disconnected = false;
  let output: (bytes: Uint8Array) => void = () => {};
  const owner = new BrowserFixtureOwner({
    diagnostics,
    nonce: "owned-run",
    caseNonce: () => "owned-case",
    clock,
    launch: async (options) => {
      calls.push({ method: "launch", ...options });
      return launched.promise;
    },
  });
  const channel: FixtureChannel = {
    onData(callback) {
      input = callback;
    },
    onEnd(callback) {
      ended = callback;
    },
    async write(bytes) {
      messages.push(JSON.parse(new TextDecoder().decode(bytes)));
      output(bytes);
      if (blocked) await new Promise<void>(() => {});
    },
    end() {
      disconnected = true;
    },
  };
  owner.accept(channel);
  const send = (frame: object) =>
    input(Buffer.from(JSON.stringify({ version: 1, ...frame }) + "\n"));
  return {
    owner,
    clock,
    messages,
    calls,
    launched,
    lease,
    close,
    kill,
    closed,
    send,
    input,
    output(callback: (bytes: Uint8Array) => void) {
      output = callback;
    },
    deliver(bytes: Uint8Array) {
      output(bytes);
    },
    end: () => ended(),
    disconnected: () => disconnected,
    async prepare() {
      send({ type: "hello", nonce: "owned-run", role: "supervisor", caseId });
      await browserTicks();
      send({
        type: "arm",
        readyAt: 50,
        sent: 50,
        workDeadline: 1050,
        assertDeadline: 2050,
      });
      await browserTicks();
    },
    request(op: string, id: number, deadline = 2050) {
      send({
        type: "request",
        id,
        op,
        nonce: "owned-case",
        deadline,
        ...(op === "launch"
          ? { options: { channel: "chromium", headless: true, timeout: 5000 } }
          : {}),
      });
    },
  };
}

function clientLink(h: ReturnType<typeof browserHarness>, splitUtf8 = false) {
  let lost: () => void = () => {};
  const channel: FixtureChannel = {
    onData(callback) {
      h.output((bytes) => {
        const boundary = splitUtf8 ? bytes.indexOf(0xc3) + 1 : 0;
        if (boundary) {
          callback(bytes.subarray(0, boundary));
          callback(bytes.subarray(boundary));
        } else callback(bytes);
      });
    },
    onEnd(callback) {
      lost = callback;
    },
    async write(bytes) {
      h.input(bytes);
    },
    end() {
      h.end();
    },
  };
  return { channel, lost: () => lost() };
}

test(
  "pure fixture diagnostics records the first validated peer before recovery",
  { timeout: 5000 },
  async () => {
    for (const role of ["supervisor", "profile"] as const) {
      const diagnostics = new FixtureDiagnostics("broker"),
        h = browserHarness("startup-cancel", false, diagnostics);
      await h.prepare();
      h.request("launch", 1);
      await browserTicks();
      h.launched.resolve(h.lease);
      await browserTicks();
      try {
        if (role === "supervisor") h.end();
        else {
          let input: (bytes: Uint8Array) => void = () => {},
            end = () => {};
          h.owner.accept({
            onData(receive) {
              input = receive;
            },
            onEnd(receive) {
              end = receive;
            },
            async write() {},
            end() {},
          });
          input(
            Buffer.from(
              JSON.stringify({
                version: 1,
                type: "hello",
                nonce: "owned-case",
                role: "profile",
                caseId: "startup-cancel",
              }) + "\n",
            ),
          );
          await browserTicks();
          end();
        }
        await browserTicks();
        assert.equal(JSON.parse(diagnostics.snapshot())[0]?.peer, role);
        assert.ok(h.calls.some((call) => call.method === "kill"));
      } finally {
        h.kill.resolve();
        h.closed.resolve();
        await h.owner.stop(h.clock.now() + 1000);
      }
    }
  },
);

test("pure browser owner client forwards only actual owner API completion and caches close", async () => {
  const h = browserHarness();
  h.lease.api.wsEndpoint = () => "ws://owned.invalid/é";
  const link = clientLink(h, true);
  const client = await connectBrowserCase({
    caseId: "startup-cancel",
    nonce: "owned-run",
    clock: h.clock,
    workDeadline: 1100,
    assertDeadline: 2100,
    channel: link.channel,
  });
  const acquiring = client.launch({
    channel: "chromium",
    headless: true,
    timeout: 5000,
  });
  h.launched.resolve(h.lease);
  const api = await acquiring;
  assert.equal(api.wsEndpoint(), "ws://owned.invalid/é");
  const closing = api.close();
  assert.equal(api.close(), closing);
  let complete = false;
  void closing.then(() => {
    complete = true;
  });
  h.close.resolve();
  await browserTicks();
  assert.equal(complete, false);
  h.closed.resolve();
  await closing;
  const receipt = await client.completion;
  assert.equal(receipt.origin, "profile");
  assert.equal(receipt.requestId, 2);
  assert.match(receipt.ownerId, /^[a-f0-9]{64}$/);
  assert.equal(h.calls.filter((c) => c.method === "close").length, 1);
  client.end();
  await browserTicks();
  assert.equal(h.clock.timers.size, 0);
});

test("pure browser owner client loss never supplies successful completion", async () => {
  const h = browserHarness();
  const link = clientLink(h);
  const client = await connectBrowserCase({
    caseId: "startup-cancel",
    nonce: "owned-run",
    clock: h.clock,
    workDeadline: 1100,
    assertDeadline: 2100,
    channel: link.channel,
  });
  const acquiring = client.launch({
    channel: "chromium",
    headless: true,
    timeout: 1000,
  });
  void acquiring.catch(() => {});
  await browserTicks();
  assert.equal(h.calls.filter((c) => c.method === "launch").length, 1);
  link.lost();
  await assert.rejects(acquiring, /owner.*lost|closed/i);
  await assert.rejects(client.completion, /owner.*lost|closed/i);
  h.clock.advance(5001);
  await browserTicks();
  assert.equal(h.owner.snapshot().cases[0]?.held, true);
  assert.equal(h.clock.timers.size, 0);
});

test("pure browser owner rejects stale ids and preserves first control write failure", async () => {
  const h = browserHarness();
  await h.prepare();
  h.request("launch", 1);
  h.launched.resolve(h.lease);
  await browserTicks();
  h.request("launch", 1);
  await browserTicks();
  assert.equal(h.disconnected(), true);
  assert.equal(h.calls.filter((c) => c.method === "launch").length, 1);
  h.kill.resolve();
  h.closed.resolve();
  await browserTicks();
  assert.equal(h.owner.snapshot().cases[0]?.emergency, true);
  const clock = new ManualBrowserClock();
  const owner = new BrowserFixtureOwner({
    nonce: "owned-run",
    caseNonce: () => "owned-case",
    clock,
    launch: async () => {
      throw new Error("unused");
    },
  });
  let receive: (bytes: Uint8Array) => void = () => {};
  owner.accept({
    onData(callback) {
      receive = callback;
    },
    onEnd() {},
    write: async () => {
      throw new Error("controlled write failure");
    },
    end() {},
  });
  receive(
    Buffer.from(
      JSON.stringify({
        version: 1,
        type: "hello",
        nonce: "owned-run",
        role: "supervisor",
        caseId: "startup-cancel",
      }) + "\n",
    ),
  );
  await browserTicks();
  assert.ok(owner.snapshot().errors.includes("control-write-failed"));
});

test("pure browser owner supervisor preserves worker, recovery and report failures", async () => {
  const h = browserHarness();
  await h.prepare();
  h.request("launch", 1);
  h.launched.resolve(h.lease);
  await browserTicks();
  const primary = new Error("controlled worker failure"),
    report = new Error("controlled report failure");
  h.kill.reject(new Error("controlled API kill failure"));
  await assert.rejects(
    superviseBrowserWorker(
      h.owner,
      async () => {
        throw primary;
      },
      async () => {
        throw report;
      },
      h.clock,
    ),
    (error: unknown) => {
      assert.ok(error instanceof AggregateError);
      assert.equal(error.errors[0], primary);
      assert.match(String(error.errors[1]), /unknown/);
      assert.equal(error.errors[2], report);
      return true;
    },
  );
  assert.equal(h.owner.snapshot().cases[0]?.held, true);
  assert.equal(h.clock.timers.size, 0);
});

test("pure browser owner supervisor stops the worker and browser concurrently on cancellation", async () => {
  const h = browserHarness();
  await h.prepare();
  h.request("launch", 1);
  h.launched.resolve(h.lease);
  await browserTicks();
  const controller = new AbortController(),
    worker = pending<void>();
  const primary = new Error("controlled outer cancellation");
  let cancelled = false;
  const supervising = superviseBrowserWorker(
    h.owner,
    (signal) => {
      signal.addEventListener(
        "abort",
        () => {
          cancelled = true;
        },
        { once: true },
      );
      return worker.promise;
    },
    async () => {},
    h.clock,
    controller.signal,
  );
  void supervising.catch(() => {});
  await browserTicks();
  controller.abort(primary);
  await browserTicks();
  assert.equal(cancelled, true);
  assert.equal(h.calls.filter((c) => c.method === "kill").length, 1);
  const firstDeadline = h.owner.snapshot().cases[0]?.recoveryDeadline;
  const later = new Error("later worker exit");
  h.clock.advance(100);
  worker.reject(later);
  h.kill.resolve();
  h.closed.resolve();
  await assert.rejects(
    supervising,
    (error: unknown) =>
      error instanceof AggregateError &&
      error.errors[0] === primary &&
      error.errors[1] === later,
  );
  assert.equal(h.owner.snapshot().cases[0]?.recoveryDeadline, firstDeadline);
  assert.equal(h.owner.snapshot().cases[0]?.emergency, true);
  assert.equal(h.clock.timers.size, 0);
});

test("pure browser owner keeps the original close window usable for profile kill", async () => {
  const h = browserHarness("stalled-close"),
    link = clientLink(h);
  const client = await connectBrowserCase({
    caseId: "stalled-close",
    nonce: "owned-run",
    clock: h.clock,
    workDeadline: 1100,
    assertDeadline: 30100,
    channel: link.channel,
  });
  try {
    const acquiring = client.launch({
      channel: "chromium",
      headless: true,
      timeout: 1000,
    });
    h.launched.resolve(h.lease);
    const api = await acquiring;
    const closing = api.close();
    void closing.catch(() => {});
    await browserTicks();
    h.clock.advance(2500);
    await browserTicks();
    await assert.rejects(closing, /close-deadline/);
    assert.equal(
      h.disconnected(),
      false,
      "A method timeout must permit the production profile's remaining kill phase",
    );
    const killing = api.kill();
    h.kill.resolve();
    h.closed.resolve();
    await killing;
    assert.equal((await client.completion).origin, "profile");
    assert.equal(h.owner.snapshot().cases[0]?.emergency, false);
  } finally {
    h.kill.resolve();
    h.closed.resolve();
    client.end();
    h.clock.advance(5001);
    await browserTicks();
  }
});

test("pure browser owner maps fractional monotonic clocks without early emergency", async () => {
  const h = browserHarness();
  h.clock.time = 100.75;
  h.send({
    type: "hello",
    nonce: "owned-run",
    role: "supervisor",
    caseId: "startup-cancel",
  });
  await browserTicks();
  h.send({
    type: "arm",
    readyAt: 50.875,
    sent: 50.875,
    workDeadline: 1050.625,
    assertDeadline: 2050.625,
  });
  await browserTicks();
  h.request("launch", 1, 1050.625);
  await browserTicks();
  assert.deepEqual(h.calls, [
    { method: "launch", channel: "chromium", headless: true, timeout: 999.75 },
  ]);
  h.clock.advance(1999.74);
  await browserTicks();
  assert.equal(h.owner.snapshot().cases[0]?.emergency, false);
  h.clock.advance(0.02);
  await browserTicks();
  assert.equal(h.owner.snapshot().cases[0]?.emergency, true);
  h.clock.advance(5001);
  await browserTicks();
  assert.equal(h.owner.snapshot().cases[0]?.held, true);
});

test("pure browser owner never admits a profile API call after its original deadline", async () => {
  const h = browserHarness();
  await h.prepare();
  h.request("launch", 1);
  h.launched.resolve(h.lease);
  await browserTicks();
  h.clock.time = 3000;
  try {
    h.request("close", 2);
    await browserTicks();
    assert.equal(h.calls.filter((c) => c.method === "close").length, 0);
  } finally {
    h.kill.resolve();
    h.closed.resolve();
    await h.owner.stop(h.clock.now() + 5000);
  }
});

test("pure browser owner does not start report IO after the worker stop budget expires", async () => {
  const h = browserHarness(),
    worker = pending<void>(),
    controller = new AbortController();
  let reports = 0;
  const running = superviseBrowserWorker(
    h.owner,
    () => worker.promise,
    async () => {
      reports++;
    },
    h.clock,
    controller.signal,
  );
  void running.catch(() => {});
  await browserTicks();
  controller.abort(new Error("first bounded worker stop"));
  await browserTicks();
  h.clock.advance(10001);
  await browserTicks();
  await assert.rejects(running, /cleanup failed/);
  assert.equal(reports, 0);
  assert.equal(h.clock.timers.size, 0);
});

test("pure browser owner refuses acquisition cancelled or expired before API admission", async () => {
  for (const cancelled of [false, true]) {
    const h = browserHarness();
    await h.prepare();
    h.request("launch", 1);
    if (cancelled) h.end();
    else h.clock.time = 3000;
    try {
      await browserTicks();
      assert.equal(h.calls.filter((c) => c.method === "launch").length, 0);
    } finally {
      h.launched.resolve(h.lease);
      h.kill.resolve();
      h.closed.resolve();
      await h.owner.stop(h.clock.now() + 5000);
    }
    assert.equal(h.owner.snapshot().cases[0]?.held, false);
  }
});

test("pure browser owner rejects truncated control and buffers split UTF-8 before validation", async () => {
  const truncated = browserHarness();
  truncated.input(Buffer.from('{"version":1'));
  truncated.end();
  await browserTicks();
  assert.ok(truncated.owner.snapshot().errors.includes("truncated-control"));
  const split = browserHarness();
  const bytes = Buffer.from(
    JSON.stringify({
      version: 1,
      type: "hello",
      nonce: "wrong-é",
      role: "supervisor",
      caseId: "startup-cancel",
    }) + "\n",
  );
  const boundary = bytes.indexOf(0xc3) + 1;
  split.input(bytes.subarray(0, boundary));
  assert.equal(split.disconnected(), false);
  split.input(bytes.subarray(boundary));
  await browserTicks();
  assert.ok(split.owner.snapshot().errors.includes("invalid-capability"));
  assert.deepEqual(split.calls, []);
});

test("pure browser owner client cannot turn emergency or oversized evidence into success", async () => {
  for (const oversized of [false, true]) {
    const h = browserHarness(),
      link = clientLink(h);
    const client = await connectBrowserCase({
      caseId: "startup-cancel",
      nonce: "owned-run",
      clock: h.clock,
      workDeadline: 1100,
      assertDeadline: 2100,
      channel: link.channel,
    });
    if (oversized) h.deliver(Buffer.alloc(8193, 120));
    else
      h.deliver(
        Buffer.from(
          JSON.stringify({
            version: 1,
            type: "receipt",
            receipt: {
              ownerId: createHash("sha256").update("owned-case").digest("hex"),
              requestId: 0,
              caseId: "startup-cancel",
              operation: "kill",
              origin: "emergency",
              fulfilled: true,
              closeObserved: true,
              completed: 100,
            },
          }) + "\n",
        ),
      );
    await assert.rejects(
      client.completion,
      oversized ? /input limit/ : /Unconfirmed/,
    );
    await h.owner.stop(h.clock.now() + 5000);
    assert.equal(h.clock.timers.size, 0);
  }
});

test("pure browser owner validates retired reply fields without reusing late success", async () => {
  const h = browserHarness(),
    link = clientLink(h);
  const client = await connectBrowserCase({
    caseId: "startup-cancel",
    nonce: "owned-run",
    clock: h.clock,
    workDeadline: 1100,
    assertDeadline: 2100,
    channel: link.channel,
  });
  try {
    const acquiring = client.launch({
      channel: "chromium",
      headless: true,
      timeout: 1000,
    });
    h.launched.resolve(h.lease);
    const api = await acquiring;
    const closing = api.close();
    h.close.resolve();
    h.closed.resolve();
    await closing;
    const receipt = await client.completion;
    h.deliver(
      Buffer.from(
        JSON.stringify({
          version: 1,
          type: "reply",
          id: 2,
          op: "close",
          ok: true,
          receipt,
          unexpected: true,
        }) + "\n",
      ),
    );
    const killing = api.kill();
    void killing.catch(() => {});
    await browserTicks();
    h.clock.advance(2001);
    await browserTicks();
    await assert.rejects(killing, /control closed/);
  } finally {
    h.kill.resolve();
    h.closed.resolve();
    client.end();
    await browserTicks();
  }
});

test("pure browser owner refuses completion evidence before the case is armed", async () => {
  const clock = new ManualBrowserClock();
  let receive: (bytes: Uint8Array) => void = () => {};
  const emit = (value: object) =>
    receive(Buffer.from(JSON.stringify({ version: 1, ...value }) + "\n"));
  const channel: FixtureChannel = {
    onData(callback) {
      receive = callback;
    },
    onEnd() {},
    end() {},
    async write(bytes) {
      const value = JSON.parse(new TextDecoder().decode(bytes)) as {
        type: string;
      };
      if (value.type === "hello")
        emit({ type: "ready", clock: 100, caseNonce: "owned-case" });
      else if (value.type === "arm") {
        emit({
          type: "receipt",
          receipt: {
            ownerId: createHash("sha256").update("owned-case").digest("hex"),
            requestId: 2,
            caseId: "startup-cancel",
            operation: "close",
            origin: "profile",
            fulfilled: true,
            closeObserved: true,
            completed: 100,
          },
        });
        emit({ type: "armed" });
      }
    },
  };
  await assert.rejects(
    connectBrowserCase({
      caseId: "startup-cancel",
      nonce: "owned-run",
      clock,
      workDeadline: 1100,
      assertDeadline: 2100,
      channel,
    }),
    /before.*armed/,
  );
  await browserTicks();
  assert.equal(clock.timers.size, 0);
});

test("pure browser owner accepts only the injected close error without hiding other cleanup failures", () => {
  for (const message of [
    "Operation exceeded its 2500ms deadline",
    "close-deadline",
  ]) {
    const expected = new Error(message);
    assert.equal(
      expectedStalledCloseFailure(
        new AggregateError([expected], "Profile cleanup failed"),
      ),
      true,
    );
    for (const extra of [
      "backend failed",
      "Backend exceeded its 4 MiB output budget",
      "listener failed",
      "control-deadline",
      "log write failed",
    ])
      assert.equal(
        expectedStalledCloseFailure(
          new AggregateError(
            [expected, new Error(extra)],
            "Profile cleanup failed",
          ),
        ),
        false,
      );
    assert.equal(
      expectedStalledCloseFailure(
        new AggregateError(
          [new Error(message, { cause: new Error("hidden backend failure") })],
          "Profile cleanup failed",
        ),
      ),
      false,
    );
    assert.equal(
      expectedStalledCloseFailure(
        new AggregateError([expected], "Profile cleanup failed", {
          cause: new Error("independent failure"),
        }),
      ),
      false,
    );
    assert.equal(expectedStalledCloseFailure(expected), false);
  }
  assert.equal(
    expectedStalledCloseFailure(
      new AggregateError(
        [new Error("control-deadline")],
        "Profile cleanup failed",
      ),
    ),
    false,
  );
});

test("pure browser owner rejects malformed capabilities, frames and operations", async () => {
  for (const frame of [
    {
      type: "hello",
      nonce: "wrong",
      role: "supervisor",
      caseId: "startup-cancel",
    },
    {
      type: "hello",
      nonce: "owned-run",
      role: "supervisor",
      caseId: "arbitrary",
    },
    {
      type: "hello",
      nonce: "owned-run",
      role: "supervisor",
      caseId: "startup-cancel",
      unexpected: true,
    },
    { type: "request", id: 1, op: "eval", nonce: "owned-case", deadline: 1000 },
  ]) {
    const h = browserHarness();
    h.send(frame);
    await browserTicks();
    assert.equal(h.disconnected(), true);
    assert.ok(h.owner.snapshot().errors.length);
    assert.deepEqual(h.calls, []);
  }
  for (const bytes of [
    Buffer.from([0xff, 10]),
    Buffer.from('{"version":1,"version":1}\n'),
    Buffer.from(
      JSON.stringify({
        version: 1,
        type: "hello",
        nonce: "x".repeat(4096),
        role: "supervisor",
        caseId: "startup-cancel",
      }) + "\n",
    ),
    Buffer.alloc(8193, 120),
  ]) {
    const h = browserHarness();
    h.input(bytes);
    await browserTicks();
    assert.equal(h.disconnected(), true);
    assert.ok(h.owner.snapshot().errors.length);
    if (bytes.length > 4096)
      assert.ok(h.owner.snapshot().errors.includes("control-size"));
  }
});

test("pure browser owner waits for actual API and close evidence with clipped startup", async () => {
  const h = browserHarness();
  await h.prepare();
  h.request("launch", 1);
  await browserTicks();
  assert.deepEqual(h.calls, [
    { method: "launch", channel: "chromium", headless: true, timeout: 1000 },
  ]);
  assert.ok(!h.messages.some((m) => m.type === "reply"));
  h.launched.resolve(h.lease);
  await browserTicks();
  assert.equal(
    h.messages.find((m) => m.type === "reply")?.endpoint,
    "ws://owned.invalid/browser",
  );
  h.request("close", 2);
  await browserTicks();
  h.close.resolve();
  await browserTicks();
  assert.ok(!h.owner.snapshot().cases[0]?.receipts.length);
  h.closed.resolve();
  await browserTicks();
  assert.deepEqual(
    h.owner
      .snapshot()
      .cases[0]?.receipts.map((r) => [
        r.operation,
        r.origin,
        r.fulfilled,
        r.closeObserved,
      ]),
    [["close", "profile", true, true]],
  );
  assert.equal(h.owner.snapshot().cases[0]?.held, false);
  assert.equal(h.clock.timers.size, 0);
});

test("pure browser owner retains late acquisition and one recovery deadline", async () => {
  for (const expired of [false, true]) {
    const h = browserHarness();
    await h.prepare();
    h.request("launch", 1);
    await browserTicks();
    h.end();
    await browserTicks();
    const deadline = h.owner.snapshot().cases[0]?.recoveryDeadline;
    assert.equal(deadline, 5100);
    h.end();
    const stopping = h.owner.stop(9000);
    void stopping.catch(() => {});
    await browserTicks();
    assert.equal(h.owner.snapshot().cases[0]?.recoveryDeadline, deadline);
    h.clock.advance(expired ? 5001 : 1000);
    await browserTicks();
    h.launched.resolve(h.lease);
    await browserTicks();
    if (expired) {
      assert.equal(h.calls.filter((c) => c.method === "kill").length, 0);
      assert.equal(h.owner.snapshot().cases[0]?.held, true);
      assert.equal(h.owner.snapshot().cases[0]?.state, "unknown");
      await assert.rejects(stopping, /unknown/);
    } else {
      assert.equal(h.calls.filter((c) => c.method === "kill").length, 1);
      h.kill.resolve();
      h.closed.resolve();
      await browserTicks();
      const row = h.owner.snapshot().cases[0];
      assert.equal(row?.state, "closed");
      assert.equal(row?.emergency, true);
      assert.ok(row?.receipts.every((r) => r.origin === "emergency"));
      await stopping;
    }
  }
});

test("pure browser owner permits kill after labelled stalled close and preserves failures", async () => {
  const h = browserHarness("stalled-close");
  await h.prepare();
  h.request("launch", 1);
  h.launched.resolve(h.lease);
  await browserTicks();
  h.request("close", 2);
  await browserTicks();
  assert.equal(
    h.owner.snapshot().cases[0]?.instrumentation,
    "close-injected-stall",
  );
  h.request("kill", 3);
  await browserTicks();
  assert.equal(h.calls.filter((c) => c.method === "kill").length, 1);
  h.kill.reject(new Error("controlled kill failure"));
  await browserTicks();
  assert.ok(h.owner.snapshot().cases[0]?.errors.includes("kill-failed"));
  h.clock.advance(2000);
  await browserTicks();
  assert.ok(h.owner.snapshot().cases[0]?.errors.includes("close-deadline"));
  assert.ok(
    !h.owner.snapshot().cases[0]?.receipts.some((r) => r.origin === "profile"),
  );
});

test("pure browser owner preserves unknown acquisition and bounded control failure", async () => {
  const h = browserHarness();
  await h.prepare();
  h.request("launch", 1);
  await browserTicks();
  h.launched.reject(new Error("controlled partial launch failure"));
  await browserTicks();
  assert.equal(h.owner.snapshot().cases[0]?.held, true);
  assert.ok(h.owner.snapshot().cases[0]?.errors.includes("launch-failed"));
  const blocked = browserHarness("startup-cancel", true);
  blocked.send({
    type: "hello",
    nonce: "owned-run",
    role: "supervisor",
    caseId: "startup-cancel",
  });
  blocked.clock.advance(2001);
  await browserTicks();
  assert.equal(blocked.disconnected(), true);
  assert.ok(blocked.owner.snapshot().errors.includes("control-deadline"));
});

test("pure browser owner report write failure remains a failed fixture", async () => {
  const work = await mkdtemp(join(tmpdir(), "sdk-browser-report-"));
  try {
    const h = browserHarness();
    await assert.rejects(h.owner.writeReport(work), /EISDIR/);
    assert.ok(h.owner.snapshot().errors.includes("report-write-failed"));
  } finally {
    await rm(work, { recursive: true, force: true });
  }
});

async function inspectBrowserDirectory(acquired: {
  folder: string;
  socketPath: string;
}) {
  const status = await lstat(acquired.folder);
  assert.equal(status.isDirectory(), true);
  assert.equal(status.mode & 0o777, 0o700);
  assert.equal(isAbsolute(acquired.socketPath), true);
  assert.ok(Buffer.byteLength(acquired.socketPath) < 100);
  const file = join(acquired.folder, "owned-check");
  await writeFile(file, "owned browser socket directory\n");
  assert.equal(
    await readFile(file, "utf8"),
    "owned browser socket directory\n",
  );
  return {
    mode: status.mode & 0o777,
    socketBytes: Buffer.byteLength(acquired.socketPath),
  };
}

test(
  "pure browser owner acquires a real private socket directory without a Darwin-only parent",
  { timeout: 5000 },
  async (context) => {
    const folders: string[] = [];
    try {
      const acquired = await acquireBrowserFixtureDirectory(async (prefix) => {
        // Emulate Ubuntu's absent ancestor on Mac, while real allocations stay real.
        if (prefix.startsWith("/private/tmp/"))
          throw Object.assign(
            new Error("Emulated missing Darwin-only temporary parent"),
            {
              code: "ENOENT",
              path: prefix,
              syscall: "mkdtemp",
            },
          );
        const folder = await mkdtemp(prefix);
        folders.push(folder);
        return folder;
      });
      const inspected = await inspectBrowserDirectory(acquired);
      context.diagnostic(
        JSON.stringify({ directory: acquired.folder, ...inspected }),
      );
    } finally {
      for (const folder of folders) {
        await rm(folder, { recursive: true, force: true });
        await assert.rejects(lstat(folder), { code: "ENOENT" });
      }
      context.diagnostic(
        JSON.stringify({
          emulatedMissingAncestor: true,
          removedDirectories: folders,
        }),
      );
    }
  },
);

test(
  "pure browser owner keeps real socket acquisition short with long TMPDIR",
  { timeout: 5000 },
  async (context) => {
    const present = Object.hasOwn(process.env, "TMPDIR"),
      previous = process.env.TMPDIR;
    let folder: string | undefined;
    try {
      process.env.TMPDIR = "/tmp/" + "long-browser-temp-root-".repeat(12);
      const acquired = await acquireBrowserFixtureDirectory();
      folder = acquired.folder;
      const inspected = await inspectBrowserDirectory(acquired);
      context.diagnostic(
        JSON.stringify({
          directory: folder,
          ...inspected,
          longTmpdirBytes: Buffer.byteLength(process.env.TMPDIR),
        }),
      );
    } finally {
      if (present) process.env.TMPDIR = previous!;
      else delete process.env.TMPDIR;
      if (folder) {
        await rm(folder, { recursive: true, force: true });
        await assert.rejects(lstat(folder), { code: "ENOENT" });
      }
      assert.equal(Object.hasOwn(process.env, "TMPDIR"), present);
      assert.equal(process.env.TMPDIR, previous);
      context.diagnostic(
        JSON.stringify({
          removedDirectory: folder,
          tmpdirRestored: true,
          tmpdirWasPresent: present,
        }),
      );
    }
  },
);

test("pure browser owner binds a fixed case before accepting browser operations", async () => {
  const messages: Record<string, unknown>[] = [];
  let receive: ((bytes: Uint8Array) => void) | undefined;
  const channel: FixtureChannel = {
    onData(callback) {
      receive = callback;
    },
    onEnd() {},
    async write(bytes) {
      messages.push(JSON.parse(new TextDecoder().decode(bytes)));
    },
    end() {},
  };
  const owner = new BrowserFixtureOwner({
    nonce: "owned-run",
    caseNonce: () => "owned-case",
    clock: { now: () => 100, set: () => 0, clear() {} },
    launch: async () => {
      throw new Error("No browser may launch during HELLO");
    },
  });
  owner.accept(channel);
  receive?.(
    Buffer.from(
      JSON.stringify({
        version: 1,
        type: "hello",
        nonce: "owned-run",
        role: "supervisor",
        caseId: "startup-cancel",
      }) + "\n",
    ),
  );
  await Promise.resolve();
  assert.equal(messages[0]?.type, "ready");
  assert.equal(messages[0]?.caseNonce, "owned-case");
});
