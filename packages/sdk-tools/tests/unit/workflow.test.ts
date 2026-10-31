import assert from "node:assert/strict";
import test from "node:test";
import {
  stage,
  describeError,
  type Stage,
} from "../../src/workflows/stages.ts";
import {
  ProcessFailure,
  hasConfirmedCleanup,
} from "../../src/system/process.ts";
import { setupSdk } from "../../src/workflows/setup.ts";
import { testSdk } from "../../src/workflows/test.ts";
import { verifyPackage } from "../../src/workflows/verify.ts";
import { argumentsFor } from "../../src/arguments.ts";

test("a failed SDK stage cannot prevent independent checks from running", async () => {
  const stages: Stage[] = [];
  const visited: string[] = [];
  for (const language of ["rust", "python"])
    await stage(stages, language, async () => {
      visited.push(language);
      if (language === "rust") throw new Error("compile failed");
    });
  assert.deepEqual(visited, ["rust", "python"]);
  assert.deepEqual(
    stages.map((entry) => entry.status),
    ["failed", "passed"],
  );
});
test("local filters are explicit, validated and forbidden on full verification", () => {
  assert.deepEqual(
    argumentsFor([
      "test",
      "--profile",
      "python-sync",
      "--case",
      "consent-decide",
    ]).selected,
    ["python"],
  );
  assert.equal(
    argumentsFor(["test", "--profile", "python-sync"]).partial,
    true,
  );
  for (const argv of [
    ["verify", "--case", "health"],
    ["test", "rust", "--profile", "python-sync"],
    ["test", "rust", "rust"],
    ["test", "other"],
  ])
    assert.throws(() => argumentsFor(argv));
});

test("stage admission requires explicit confirmed cleanup rather than a rendered message", async () => {
  for (const [error, allowed] of [
    [new ProcessFailure("compiler failed", true), true],
    [new ProcessFailure("cleanup unknown", false), false],
    [new Error("cleanup confirmed"), false],
    [{ cleanupConfirmed: true }, false],
  ] as const) {
    const stages: Stage[] = [];
    assert.deepEqual(
      await stage(stages, "controlled", async () => {
        throw error;
      }),
      {
        passed: false,
        mayStartProcess: allowed,
      },
    );
    assert.equal(stages[0]?.status, "failed");
  }
});

test("nested error publication is bounded, cycle safe and does not reveal arbitrary text", () => {
  const original = new Error("secret ws://private.example/capability");
  const aggregate = new AggregateError([original], "private command argv");
  Object.defineProperty(original, "cause", { value: aggregate });
  const detail = describeError(aggregate);
  assert.ok(Buffer.byteLength(detail) <= 4096);
  assert.ok(!detail.includes("secret") && !detail.includes("private"));
  assert.ok(detail.includes("cycle"));
  const hostile = new AggregateError([], "sensitive");
  Object.defineProperty(hostile, "errors", {
    get() {
      throw new Error("must not invoke");
    },
  });
  assert.doesNotThrow(() => describeError(hostile));
  assert.ok(!describeError(hostile).includes("sensitive"));
});

test("error publication retains only actual own allowlisted cause properties", () => {
  const original = Object.assign(new Error("private endpoint and argv"), {
    code: "ECONNRESET",
    syscall: "read",
  });
  const owner = new ProcessFailure("private", false, undefined, {
    cause: original,
  });
  const aggregate = new AggregateError(
    [new Error("timeout"), owner],
    "private",
  );
  assert.deepEqual(JSON.parse(describeError(aggregate)), {
    kind: "aggregate",
    code: "unknown",
    syscall: "unknown",
    errors: [
      { kind: "error", code: "unknown", syscall: "unknown" },
      {
        kind: "cleanup-unconfirmed",
        code: "unknown",
        syscall: "unknown",
        cause: { kind: "error", code: "ECONNRESET", syscall: "read" },
      },
    ],
  });
  assert.equal(owner.cause, original);
  assert.equal(hasConfirmedCleanup(owner), false);
  let touched = false;
  const hostile = new Error("private");
  for (const property of ["code", "syscall"])
    Object.defineProperty(hostile, property, {
      get() {
        touched = true;
        return "private";
      },
    });
  assert.deepEqual(JSON.parse(describeError(hostile)), {
    kind: "error",
    code: "unknown",
    syscall: "unknown",
  });
  assert.equal(touched, false);
  assert.deepEqual(
    JSON.parse(
      describeError(
        Object.assign(new Error("private"), {
          code: "private",
          syscall: "private",
        }),
      ),
    ),
    { kind: "error", code: "unknown", syscall: "unknown" },
  );
});

test("error publication retains only fixed observer tags within its existing bounds", () => {
  const owner = new ProcessFailure("private", false, {
    helperCode: 1,
    helperClosed: true,
    streamsEnded: true,
    terminal: {
      status: 0,
      reason: "target-exit",
      leaderReaped: true,
      groupState: "unknown",
      errors: [
        "group-observation-failed",
        "ps-term-read-timeout",
        "ps-term-read-timeout-private",
        "ps-TERM-read-timeout",
        "private-data",
      ],
    },
  });
  assert.deepEqual(
    JSON.parse(describeError(new Error("timeout", { cause: owner }))),
    {
      kind: "error",
      code: "unknown",
      syscall: "unknown",
      cause: {
        kind: "cleanup-unconfirmed",
        code: "unknown",
        syscall: "unknown",
        helperCode: 1,
        helperClosed: true,
        streamsEnded: true,
        leaderReaped: true,
        groupState: "unknown",
        errors: [
          "group-observation-failed",
          "ps-term-read-timeout",
          "unknown",
          "unknown",
          "unknown",
        ],
      },
    },
  );
  const aggregate = new AggregateError(
    Array.from({ length: 8 }, () => owner),
    "private",
  );
  const published = describeError(aggregate);
  assert.ok(Buffer.byteLength(published) <= 4096);
  assert.ok(!published.includes("private"));
  assert.equal(owner.state?.terminal?.errors[1], "ps-term-read-timeout");
  assert.equal(hasConfirmedCleanup(owner), false);
});

test("blocked stages cannot invoke dependent runtime callbacks and preserve independent reports", async () => {
  const stages: Stage[] = [];
  const prerequisite = await stage(stages, "harness", async () => {
    throw new Error("unknown cleanup");
  });
  let invoked = false;
  await stage(
    stages,
    "browser",
    async () => {
      invoked = true;
    },
    prerequisite.passed && prerequisite.mayStartProcess,
  );
  assert.equal(invoked, false);
  assert.deepEqual(
    stages.map((entry) => entry.status),
    ["failed", "failed"],
  );
  assert.equal(
    stages[1]?.detail && (stages[1].detail as { blocked: boolean }).blocked,
    true,
  );
});

test("setup, test and package callers record blocked work without starting their subprocess tasks", async () => {
  const denied = { passed: false, mayStartProcess: false };
  const setup: Stage[] = [],
    tested: Stage[] = [],
    packaged: Stage[] = [];
  assert.equal(
    (await setupSdk("typescript", setup, denied)).mayStartProcess,
    false,
  );
  assert.equal(
    (await testSdk("typescript", "/not-admitted", tested, {}, denied))
      .mayStartProcess,
    false,
  );
  assert.equal(
    (await verifyPackage("typescript", "/not-admitted", packaged, denied))
      .mayStartProcess,
    false,
  );
  for (const recorded of [setup, tested, packaged]) {
    assert.ok(recorded.length > 0);
    assert.ok(
      recorded.every(
        (entry) =>
          entry.status === "failed" &&
          entry.error === "Blocked by failed prerequisite",
      ),
    );
  }
});

test("forged error shapes cannot authorize process admission", () => {
  const forged: unknown = Object.create(ProcessFailure.prototype, {
    cleanupConfirmed: { value: true },
  });
  assert.equal(hasConfirmedCleanup(forged), false);
});

test("nested diagnostic traversal does not invoke array accessors", () => {
  let accessed = false;
  const nested: unknown[] = [];
  Object.defineProperty(nested, "0", {
    get() {
      accessed = true;
      throw new Error("private");
    },
  });
  const aggregate = new AggregateError([], "private");
  Object.defineProperty(aggregate, "errors", { value: nested });
  assert.doesNotThrow(() => describeError(aggregate));
  assert.equal(accessed, false);
});

test("a failed nested native stage denies HTTP and later callers despite confirmed outer cleanup", async () => {
  const visited: string[] = [],
    stages: Stage[] = [];
  const scripted: typeof stage = (records, name, _task, admitted = true) =>
    stage(
      records,
      name,
      async () => {
        visited.push(name);
        if (name === "native-regressions")
          throw new ProcessFailure("outer launcher exited", true);
      },
      admitted,
    );
  const result = await testSdk(
    "typescript",
    "/not-launched",
    stages,
    {},
    undefined,
    scripted,
  );
  assert.equal(result.mayStartProcess, false);
  assert.ok(!visited.includes("http"));
  assert.equal(
    stages.find((entry) => entry.name === "compilation")?.status,
    "passed",
  );
  assert.equal(
    stages.find((entry) => entry.name === "native-regressions")?.status,
    "failed",
  );
  const consumer: Stage[] = [],
    later: Stage[] = [];
  await verifyPackage("typescript", "/not-launched", consumer, result);
  await testSdk("typescript", "/not-launched", later, {}, result);
  assert.ok(
    [...consumer, ...later].every(
      (entry) => (entry.detail as { blocked?: boolean } | undefined)?.blocked,
    ),
  );
});

test("confirmed independent compilation failure still permits later independent work", async () => {
  const visited: string[] = [],
    stages: Stage[] = [];
  const scripted: typeof stage = (records, name, _task, admitted = true) =>
    stage(
      records,
      name,
      async () => {
        visited.push(name);
        if (name === "compilation")
          throw new ProcessFailure("independent compiler exited", true);
      },
      admitted,
    );
  const result = await testSdk(
    "typescript",
    "/not-launched",
    stages,
    {},
    undefined,
    scripted,
  );
  assert.equal(result.mayStartProcess, true);
  assert.ok(visited.includes("native-typing"));
  assert.ok(
    !visited.includes("native-regressions") && !visited.includes("http"),
  );
  let independent = false;
  await stage(
    stages,
    "other-compilation",
    async () => {
      independent = true;
    },
    result.mayStartProcess,
  );
  assert.equal(independent, true);
});
