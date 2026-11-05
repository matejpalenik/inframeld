import assert from "node:assert/strict";
import {
  mkdtemp,
  mkdir,
  rm,
  writeFile,
  lstat,
  realpath,
  readFile,
} from "node:fs/promises";
import { tmpdir } from "node:os";
import { basename, join, sep } from "node:path";
import test from "node:test";
import type { TestEvent } from "node:test/reporters";
import { artifacts, home } from "../../src/config.ts";
import {
  command,
  hasConfirmedCleanup,
  ProcessFailure,
  withResources,
} from "../../src/system/process.ts";
import {
  publishFixtureDiagnostics,
  type FixtureClock,
} from "../native/fixtures/browser-owner.ts";
import {
  fixtureDiagnostic,
  fixtureCaptureMetadata,
  FixtureDiagnostics,
  prepareFixtureCapture,
  observeFixtureController,
  acquireProtectedFixtureDirectory,
} from "../native/fixtures/fixture-diagnostics.ts";
import nativeTestReporter from "../native/fixtures/fixture-diagnostics.ts";
import {
  describeError,
  stage,
  type Stage,
} from "../../src/workflows/stages.ts";

const nativeCases = [
  [
    "driver.test.ts",
    "the TypeScript driver rejects another runtime profile before SDK invocation",
    "driver-profile",
  ],
  [
    "lifecycle.test.ts",
    "cancelling an active native Fetch call permits a subsequent client request",
    "fetch-cancel",
  ],
  [
    "lifecycle.test.ts",
    "the same generated client is reusable after supported operation cancellation",
    "client-reuse",
  ],
  [
    "profile-resources.test.ts",
    "startup cancellation closes a browser acquired before the fixture returns",
    "startup-cancel",
  ],
  [
    "profile-resources.test.ts",
    "a stalled browser close is force-killed and remains a cleanup failure",
    "stalled-close",
  ],
  [
    "profile-resources.test.ts",
    "an enclosing test-runner timeout drains a profile before killing survivors",
    "profile-timeout",
  ],
  [
    "profile-resources.test.ts",
    "denied termination still permits bounded nonzero CLI exit",
    "denied-exit",
  ],
] as const;

const deniedCheckCodes = [
  "SDK_DENIED_COMMAND_EXIT",
  "SDK_DENIED_RECEIPT",
  "SDK_DENIED_ORIGINAL_ERRORS",
  "SDK_DENIED_CLOCK_BUDGET",
  "SDK_DENIED_PS_OBSERVATION",
  "SDK_DENIED_TARGET_LIVE",
  "SDK_DENIED_INDEPENDENT_RECOVERY",
] as const;

test("denied receipt checkpoints distinguish operations without publishing receipt contents", () => {
  for (const code of [
    ...deniedCheckCodes,
    "SDK_DENIED_UNCERTAIN_READ",
    "SDK_DENIED_UNCERTAIN_JSON",
    "SDK_DENIED_UNCERTAIN_SCHEMA",
    "SDK_DENIED_MARKER_READ",
    "SDK_DENIED_FAILURE_READ",
    "SDK_DENIED_FAILURE_JSON",
    "SDK_DENIED_FAILURE_SCHEMA",
    "SDK_DENIED_TARGET_MATCH",
  ]) {
    const error = Object.assign(
      new Error("fake-private-marker", {
        cause: new Error("fake-private-receipt"),
      }),
      { code },
    );
    const bytes = describeError(error);
    assert.equal(JSON.parse(bytes).code, code);
    assert.ok(!bytes.includes("fake-private"));
    assert.equal(hasConfirmedCleanup(JSON.parse(bytes)), false);
  }
});

const commandOutcomes = [
  {
    settlement: "rejected",
    status: 2,
    reason: "target-exit",
    stopReason: "target-exit",
    leaderReaped: true,
    groupState: "quiescent",
    closeResult: "resolved",
    reportedCleanupConfirmed: true,
  },
  {
    settlement: "fulfilled",
    status: 0,
    reason: "target-exit",
    stopReason: "target-exit",
    leaderReaped: true,
    groupState: "quiescent",
    closeResult: "resolved",
    reportedCleanupConfirmed: true,
  },
  {
    settlement: "rejected",
    status: null,
    reason: "timeout",
    stopReason: "timeout",
    groupState: "unknown",
    closeResult: "rejected",
    reportedCleanupConfirmed: false,
  },
] as const;

function nativeFailure(
  file: string,
  name: string,
  error = new Error("fake-private-marker"),
): Extract<TestEvent, { type: "test:fail" }> {
  return {
    type: "test:fail",
    data: {
      file,
      entryFile: file,
      name,
      nesting: 0,
      parentId: undefined,
      tags: [],
      testId: 1,
      testNumber: 1,
      details: {
        duration_ms: 0,
        error: Object.assign(new Error("fake-private-marker"), {
          cause: error,
        }),
      },
    },
  };
}

async function nativeReport(events: readonly TestEvent[]): Promise<string> {
  let bytes = "";
  for await (const part of nativeTestReporter(
    (async function* () {
      yield* events;
    })(),
  ))
    bytes += part;
  return bytes;
}

test("native reporter identifies the seven fixed cases without forwarding names or paths", async () => {
  const bytes = await nativeReport(
    nativeCases.map(([file, name]) =>
      nativeFailure(join("/private/fake-private-marker", file), name),
    ),
  );
  assert.deepEqual(
    JSON.parse(bytes).map((row: { caseId: string }) => row.caseId),
    nativeCases.map((row) => row[2]),
  );
  assert.ok(
    !bytes.includes("fake-private-marker") && !bytes.includes(".test.ts"),
  );
});

test("native reporter uses three fixed file fallbacks and a fixed unknown identity", async () => {
  const bytes = await nativeReport(
    [
      "driver.test.ts",
      "lifecycle.test.ts",
      "profile-resources.test.ts",
      "fake-private-marker.ts",
    ].map((file) => nativeFailure(file, "fake-private-marker")),
  );
  assert.deepEqual(
    JSON.parse(bytes).map((row: { caseId: string }) => row.caseId),
    ["driver-file", "lifecycle-file", "profile-file", "native-unknown"],
  );
  assert.ok(!bytes.includes("fake-private-marker"));
});

test("native reporter ignores output and preserves wrapped error privacy without invoking getters", async () => {
  let getters = 0;
  const error = new AggregateError(
    [new Error("fake-private-marker")],
    "fake-private-marker",
  );
  Object.defineProperty(error, "cause", {
    get() {
      getters++;
      throw new Error("fake-private-marker");
    },
  });
  const bytes = await nativeReport([
    nativeFailure("driver.test.ts", nativeCases[0][1], error),
  ]);
  assert.equal(JSON.parse(bytes)[0]?.category, "failed");
  assert.equal(getters, 0);
  assert.ok(!bytes.includes("fake-private-marker"));
  assert.equal(
    await nativeReport([
      {
        type: "test:stdout",
        data: { file: "fake-private-marker", message: "fake-private-marker" },
      },
    ]),
    "[]\n",
  );
});

test("native reporter preserves iterator failure after publishing its bounded snapshot", async () => {
  const failure = new Error("controlled iterator failure");
  const iterator = nativeTestReporter(
    (async function* (): AsyncGenerator<TestEvent> {
      yield nativeFailure("driver.test.ts", nativeCases[0][1]);
      throw failure;
    })(),
  );
  const first = await iterator.next();
  assert.equal(JSON.parse(first.value!)[0]?.caseId, "driver-profile");
  await assert.rejects(iterator.next(), (error) => error === failure);
});

test("native reporter rejects unrecognized messages, getters and unwrapped class tokens", async () => {
  const token = "SDK_DENIED_ORIGINAL_ERRORS";
  let getters = 0;
  const accessor = new Error("fake-private-marker");
  Object.defineProperty(accessor, "message", {
    get() {
      getters++;
      throw new Error("fake-private-marker");
    },
  });
  for (const [error, wrapped] of [
    [new Error(token), false],
    [new Error("fake-private-marker"), true],
    [Object.assign(new Error(token), { code: "fake-private-marker" }), true],
    [accessor, true],
  ] as const) {
    const failure = wrapped
      ? Object.assign(new Error("fake-private-marker"), {
          code: "ERR_TEST_FAILURE",
          failureType: "testCodeFailure",
          cause: error,
        })
      : error;
    const bytes = await nativeReport([
      nativeFailure("profile-resources.test.ts", nativeCases[6][1], failure),
    ]);
    assert.ok(!bytes.includes(token) && !bytes.includes("fake-private-marker"));
  }
  assert.equal(getters, 0);
});

test("native reporter retains original failure when the existing byte or record bound refuses encoding", async () => {
  const event = nativeFailure("driver.test.ts", nativeCases[0][1]);
  const original = event.data.details.error;
  const iterator = nativeTestReporter(
    (async function* () {
      for (let n = 0; n < 40; n++) yield event;
    })(),
  );
  const first = await iterator.next();
  assert.ok(Buffer.byteLength(first.value!) <= 4096);
  assert.ok(
    JSON.parse(first.value!).length > 0 &&
      JSON.parse(first.value!).length <= 32,
  );
  await assert.rejects(
    iterator.next(),
    (error) =>
      error instanceof AggregateError &&
      error.errors[0] === original &&
      error.errors.length === 2,
  );
});

test(
  "native reporter paired Node CLI produces private current evidence for pass and failure",
  { timeout: 95000 },
  async (context) => {
    const work = await mkdtemp(join(tmpdir(), "sdk-native-reporter-"));
    let cleanupConfirmed = true;
    await withResources(
      async () => {
        for (const fails of [false, true]) {
          const input = join(work, "profile-resources.test.ts"),
            destination = join(work, "controller-status.json"),
            log = join(work, "controller.raw.log");
          const testName = JSON.stringify(nativeCases[6][1]);
          const checks = deniedCheckCodes.map((code) =>
            code === "SDK_DENIED_COMMAND_EXIT"
              ? `test(${testName}, async () => { try { await assert.rejects(Promise.reject(new Error("fake-private-marker")), /exited 1/); } catch (error) { throw Object.assign(new Error(${JSON.stringify(code)}, { cause: { command: ${JSON.stringify(commandOutcomes[0])}, cause: error } }), { code: ${JSON.stringify(code)} }); } });`
              : `test(${testName}, () => { try { assert.equal(1, 0, "fake-private-marker"); } catch (error) { throw Object.assign(new Error(${JSON.stringify(code)}, { cause: error }), { code: ${JSON.stringify(code)} }); } });`,
          );
          await writeFile(
            input,
            [
              'import test from "node:test"; import assert from "node:assert/strict"; console.log("fake-private-marker");',
              ...(fails
                ? [
                    ...checks,
                    `test(${testName}, () => { throw Object.assign(new Error("fake-private-marker"), { code: "fake-private-marker" }); });`,
                    `test(${testName}, () => { throw new AggregateError([Object.assign(new Error("SDK_DENIED_ORIGINAL_ERRORS", { cause: new Error("fake-private-marker") }), { code: "SDK_DENIED_ORIGINAL_ERRORS" }), Object.assign(new Error("SDK_DENIED_INDEPENDENT_RECOVERY", { cause: new Error("fake-private-marker") }), { code: "SDK_DENIED_INDEPENDENT_RECOVERY" })], "fake-private-marker"); });`,
                    ...commandOutcomes
                      .slice(1)
                      .map(
                        (outcome, index) =>
                          `test(${testName}, async () => { try { await assert.rejects(${index === 0 ? "Promise.resolve()" : 'Promise.reject(new Error("fake-private-marker"))'}, /exited 1/); } catch (error) { throw Object.assign(new Error("SDK_DENIED_COMMAND_EXIT", { cause: { command: ${JSON.stringify(outcome)}, cause: error } }), { code: "SDK_DENIED_COMMAND_EXIT" }); } });`,
                      ),
                  ]
                : [
                    `test(${testName}, () => { assert.equal(0, 0, "fake-private-marker"); });`,
                  ]),
              "",
            ].join("\n"),
            { mode: 0o600 },
          );
          await writeFile(destination, "stale", { mode: 0o600 });
          await writeFile(log, "", { mode: 0o600 });
          const began = performance.now();
          let nonzero = false;
          cleanupConfirmed = false;
          try {
            await command(
              process.execPath,
              [
                "--require",
                join(home, "node_modules/tsx/dist/loader.mjs"),
                "--test",
                "--test-reporter=spec",
                "--test-reporter=" +
                  join(home, "tests/native/fixtures/fixture-diagnostics.ts"),
                "--test-reporter-destination=stdout",
                "--test-reporter-destination=" + destination,
                input,
              ],
              {
                timeout: 30000,
                cleanupTimeout: 15000,
                env: { NODE_TEST_CONTEXT: undefined },
                log,
              },
            );
            cleanupConfirmed = true;
          } catch (error) {
            cleanupConfirmed = hasConfirmedCleanup(error);
            if (!fails) throw error;
            assert.ok(error instanceof ProcessFailure && cleanupConfirmed);
            assert.match(error.message, /exited [1-9]/);
            nonzero = true;
          }
          assert.equal(nonzero, fails);
          context.diagnostic(
            JSON.stringify({
              expected: fails ? "nonzero" : "zero",
              cleanupConfirmed,
              milliseconds: performance.now() - began,
            }),
          );
          const info = await lstat(destination),
            bytes = await readFile(destination, "utf8"),
            rows = JSON.parse(bytes);
          assert.ok(info.isFile() && !info.isSymbolicLink());
          assert.equal(info.mode & 0o777, 0o600);
          assert.ok(
            Buffer.byteLength(bytes) <= 4096 &&
              !bytes.includes("fake-private-marker") &&
              !bytes.includes(work) &&
              !bytes.includes(".test.ts"),
          );
          assert.equal(
            rows.length,
            fails ? deniedCheckCodes.length + 1 + commandOutcomes.length : 0,
          );
          assert.ok(rows.length <= 32);
          if (fails) {
            assert.ok(
              rows.every(
                (row: { caseId: string }) => row.caseId === "denied-exit",
              ),
            );
            for (const [index, code] of deniedCheckCodes.entries()) {
              const failure = rows[index]?.failure;
              const chain = [
                failure,
                failure?.cause,
                failure?.cause?.cause,
                failure?.cause?.cause?.cause,
                failure?.cause?.cause?.cause?.cause,
              ];
              assert.ok(
                chain.some((error) => error?.code === code),
                code,
              );
            }

            const unknown = JSON.stringify(
              rows[deniedCheckCodes.length]?.failure,
            );
            assert.ok(unknown.includes('"unknown"'));
            assert.ok(!unknown.includes("SDK_DENIED_"));

            const failure = rows[deniedCheckCodes.length + 1]?.failure;
            const aggregate = [
              failure,
              failure?.cause,
              failure?.cause?.cause,
              failure?.cause?.cause?.cause,
              failure?.cause?.cause?.cause?.cause,
            ].find((error) => error?.kind === "aggregate");
            assert.equal(aggregate?.errors?.length, 2);
            assert.equal(
              aggregate.errors[0]?.code,
              "SDK_DENIED_ORIGINAL_ERRORS",
            );
            assert.equal(
              aggregate.errors[1]?.code,
              "SDK_DENIED_INDEPENDENT_RECOVERY",
            );
            for (const [index, outcome] of commandOutcomes.entries()) {
              const failure =
                rows[index === 0 ? 0 : deniedCheckCodes.length + 1 + index]
                  ?.failure;
              const projected = [
                failure,
                failure?.cause,
                failure?.cause?.cause,
                failure?.cause?.cause?.cause,
              ].find((error) => error?.code === "SDK_DENIED_COMMAND_EXIT");
              assert.deepEqual(projected?.command, outcome);
              assert.equal(hasConfirmedCleanup(projected), false);
            }
          }
        }
      },
      async () => {
        assert.ok(
          cleanupConfirmed,
          "Retain temporary evidence when owned CLI cleanup is unconfirmed",
        );
        await rm(work, { recursive: true, force: true });
      },
    );
  },
);

test("command outcome carrier is exact, private and never grants admission", async () => {
  const original = new Error("fake-private-marker");
  const carrier = { command: commandOutcomes[0], cause: original };
  const failure = Object.assign(
    new Error("SDK_DENIED_COMMAND_EXIT", { cause: carrier }),
    { code: "SDK_DENIED_COMMAND_EXIT" },
  );
  const projected = JSON.parse(describeError(failure));
  assert.deepEqual(projected.command, commandOutcomes[0]);
  assert.ok(
    projected.cause &&
      !JSON.stringify(projected).includes("fake-private-marker"),
  );
  assert.equal(hasConfirmedCleanup(structuredClone(projected)), false);
  const stages: Stage[] = [];
  const result = await stage(stages, "reported-command", async () => {
    throw failure;
  });
  assert.equal(result.mayStartProcess, false);
  let getters = 0;
  const hostile = { ...commandOutcomes[0] };
  Object.defineProperty(hostile, "status", {
    get() {
      getters++;
      throw original;
    },
  });
  for (const [code, cause] of [
    ["SDK_DENIED_RECEIPT", carrier],
    ["SDK_DENIED_COMMAND_EXIT", { ...carrier, extra: "fake-private-marker" }],
    [
      "SDK_DENIED_COMMAND_EXIT",
      {
        command: { ...commandOutcomes[0], extra: "fake-private-marker" },
        cause: original,
      },
    ],
    ["SDK_DENIED_COMMAND_EXIT", { command: hostile, cause: original }],
  ] as const) {
    const error = Object.assign(new Error(code, { cause }), { code });
    const bytes = describeError(error);
    assert.equal(JSON.parse(bytes).command, undefined);
    assert.ok(!bytes.includes("fake-private-marker"));
  }
  assert.equal(getters, 0);
  const cycle = Object.assign(new Error("SDK_DENIED_COMMAND_EXIT"), {
    code: "SDK_DENIED_COMMAND_EXIT",
  });
  Object.defineProperty(cycle, "cause", {
    value: { command: commandOutcomes[0], cause: cycle },
  });
  assert.ok(describeError(cycle).includes("cycle"));
  for (const [status, reason, expectedStatus, expectedReason] of [
    [-15, "timeout", -15, "timeout"],
    [9999, "fake-private-marker", null, "unknown"],
  ] as const) {
    const error = Object.assign(
      new Error("SDK_DENIED_COMMAND_EXIT", {
        cause: {
          command: { ...commandOutcomes[0], status, reason },
          cause: original,
        },
      }),
      { code: "SDK_DENIED_COMMAND_EXIT" },
    );
    const detail = JSON.parse(describeError(error));
    assert.equal(detail.command.status, expectedStatus);
    assert.equal(detail.command.reason, expectedReason);
    assert.ok(
      Buffer.byteLength(describeError(error)) <= 4096 &&
        !describeError(error).includes("fake-private-marker"),
    );
  }
});

test("native command diagnostics retain owner failure alongside the failed assertion", async () => {
  const owner = new ProcessFailure("fake-private-owner", false, {
    terminal: {
      status: 1,
      reason: "target-exit",
      leaderReaped: true,
      groupState: "unknown",
      errors: ["group-shutdown-unconfirmed"],
    },
    helperCode: 1,
    helperClosed: true,
    streamsEnded: true,
  });
  const failure = Object.assign(new Error("SDK_DENIED_COMMAND_EXIT"), {
    code: "SDK_DENIED_COMMAND_EXIT",
    cause: {
      command: {
        ...commandOutcomes[0],
        status: 1,
        groupState: "unknown",
        closeResult: "rejected",
        reportedCleanupConfirmed: false,
      },
      cause: new AggregateError(
        [owner, new Error("fake-private-assertion")],
        "fake-private-message",
      ),
    },
  });
  const bytes = await nativeReport([
    nativeFailure(nativeCases[6][0], nativeCases[6][1], failure),
  ]);
  const detail = JSON.parse(bytes)[0].failure.cause;
  assert.equal(detail.cause.kind, "aggregate");
  assert.equal(detail.cause.errors[0].kind, "cleanup-unconfirmed");
  assert.deepEqual(detail.cause.errors[0].errors, [
    "group-shutdown-unconfirmed",
  ]);
  assert.equal(detail.cause.errors[1].kind, "error");
  assert.ok(!bytes.includes("fake-private"));
  assert.equal(hasConfirmedCleanup(JSON.parse(bytes)), false);
});

function publicationClock() {
  let time = 100;
  const clock: FixtureClock = {
    now: () => time,
    set: () => 0,
    clear() {},
  };
  return { clock, expire: () => (time = 200) };
}

test("owner diagnostics publishes both safe destinations", async (context) => {
  const diagnostics = new FixtureDiagnostics("broker"),
    { clock } = publicationClock(),
    destinations: string[] = [];
  diagnostics.note({
    phase: "native-controller",
    category: "failed",
    status: 1,
  });
  context.mock.method(diagnostics, "write", async (folder: string) => {
    destinations.push(folder);
  });
  await publishFixtureDiagnostics(diagnostics, "/private/status", 200, clock);
  assert.deepEqual(destinations, ["/private/status", artifacts]);
});

test("owner diagnostics refuses expired writes before their effects", async (context) => {
  for (const deadline of [99, 100]) {
    const diagnostics = new FixtureDiagnostics("assertion"),
      { clock } = publicationClock();
    let writes = 0;
    context.mock.method(diagnostics, "write", async () => {
      writes++;
    });
    await assert.rejects(
      publishFixtureDiagnostics(
        diagnostics,
        "/private/status",
        deadline,
        clock,
      ),
      (error) => {
        assert.ok(error instanceof AggregateError);
        assert.equal(error.errors.length, 2);
        for (const failure of error.errors)
          assert.match(String(failure), /report-deadline/);
        return true;
      },
    );
    assert.equal(writes, 0);
  }
});

test("owner diagnostics still publishes ordinary status after private failure", async (context) => {
  const diagnostics = new FixtureDiagnostics("assertion"),
    { clock } = publicationClock(),
    destinations: string[] = [],
    failure = new Error("controlled private publication failure");
  context.mock.method(diagnostics, "write", async (folder: string) => {
    destinations.push(folder);
    if (folder === "/private/status") throw failure;
  });
  await assert.rejects(
    publishFixtureDiagnostics(diagnostics, "/private/status", 200, clock),
    (error) => error === failure,
  );
  assert.deepEqual(destinations, ["/private/status", artifacts]);
});

test("owner diagnostics retains both destination failures", async (context) => {
  const diagnostics = new FixtureDiagnostics("worker"),
    { clock } = publicationClock(),
    privateFailure = new Error("controlled private publication failure"),
    ordinaryFailure = new Error("controlled ordinary publication failure");
  context.mock.method(diagnostics, "write", async (folder: string) => {
    throw folder === "/private/status" ? privateFailure : ordinaryFailure;
  });
  await assert.rejects(
    publishFixtureDiagnostics(diagnostics, "/private/status", 200, clock),
    (error) => {
      assert.ok(error instanceof AggregateError);
      assert.deepEqual(error.errors, [privateFailure, ordinaryFailure]);
      return true;
    },
  );
});

test("owner diagnostics never starts its second write after allowance exhaustion", async (context) => {
  const diagnostics = new FixtureDiagnostics("worker"),
    { clock, expire } = publicationClock(),
    destinations: string[] = [];
  context.mock.method(diagnostics, "write", async (folder: string) => {
    destinations.push(folder);
    expire();
  });
  await assert.rejects(
    publishFixtureDiagnostics(diagnostics, "/private/status", 200, clock),
    (error) => {
      assert.ok(error instanceof AggregateError);
      for (const failure of error.errors)
        assert.match(String(failure), /report-deadline/);
      return true;
    },
  );
  assert.deepEqual(destinations, ["/private/status"]);
});

test("owner diagnostics preserves an initiating error alongside publication failure", async (context) => {
  const diagnostics = new FixtureDiagnostics("worker"),
    { clock } = publicationClock(),
    primary = new Error("controlled initiating failure"),
    publication = new Error("controlled publication failure");
  context.mock.method(diagnostics, "write", async (folder: string) => {
    if (folder === "/private/status") throw publication;
  });
  await assert.rejects(
    withResources(
      async () => {
        throw primary;
      },
      () =>
        publishFixtureDiagnostics(diagnostics, "/private/status", 200, clock),
    ),
    (error) => {
      assert.ok(error instanceof AggregateError);
      assert.deepEqual(error.errors, [primary, publication]);
      return true;
    },
  );
});

test("fixed native failure details never forward original messages or nested secrets", () => {
  const original = new Error("secret ws://capability/private");
  const error = new AggregateError([original], "argv nonce");
  Object.defineProperty(original, "cause", { value: error });
  const output = fixtureDiagnostic({
    phase: "fixture-terminal",
    category: "failed",
    status: null,
    failure: error,
  });
  assert.ok(
    !output.includes("secret") &&
      !output.includes("capability") &&
      !output.includes("nonce"),
  );
  assert.ok(output.includes("cycle"));
  assert.ok(Buffer.byteLength(output) < 8192);
});

test(
  "pure fixture diagnostics publishes only fixed records on success and failure",
  { timeout: 5000 },
  () => {
    for (const category of ["passed", "failed", "capture-unproved"]) {
      const output = fixtureDiagnostic({
        phase: "native-controller",
        category,
        status: null,
      });
      assert.ok(
        output.startsWith("{"),
        "A fixed status record must be published",
      );
      assert.deepEqual(JSON.parse(output), {
        phase: "native-controller",
        category,
        status: null,
      });
    }
  },
);

test(
  "pure fixture diagnostics rejects raw clipped errors and free-form success fields",
  { timeout: 5000 },
  () => {
    for (const unsafe of [
      new Error("nonce-fragment"),
      new AggregateError([new Error("ws-fragment")], "clipped", {
        cause: new Error("private-cause"),
      }),
      {
        phase: "native-controller",
        category: "passed",
        status: null,
        output: "nonce-fragment",
      },
      { phase: "native-controller", category: "failed", cause: "ws-fragment" },
      { phase: "private-phase", category: "failed" },
      { phase: "peer-lost", category: "failed", peer: "nonce-fragment" },
    ])
      assert.throws(
        () => fixtureDiagnostic(unsafe),
        /Invalid fixture diagnostic/,
      );
  },
);

test(
  "pure fixture diagnostics bounds encoded metadata without decoding protected text",
  { timeout: 5000 },
  () => {
    const initial = { bytes: 0, device: 1, inode: 2 };
    assert.deepEqual(
      fixtureCaptureMetadata(initial, { ...initial, bytes: 3 }),
      { ...initial, bytes: 3 },
    );
    assert.equal(Buffer.byteLength("\uFFFD\uFFFD"), 6);
    for (const current of [
      { ...initial, bytes: 64 * 1024 * 1024 + 1 },
      { ...initial, bytes: -1 },
      { ...initial, inode: 3 },
      { ...initial, device: 2 },
    ])
      assert.throws(
        () => fixtureCaptureMetadata(initial, current),
        /Invalid protected capture/,
      );
  },
);

test(
  "pure fixture diagnostics retains a private capture and checks its identity",
  { timeout: 5000 },
  async () => {
    const work = await mkdtemp(join(tmpdir(), "sdk-diagnostic-capture-"));
    let folder: string | undefined;
    try {
      const publication = join(work, "artifacts");
      await mkdir(publication);
      const report = join(publication, "sdk-diagnostic-capture.json");
      folder = await acquireProtectedFixtureDirectory(report);
      const canonicalArtifacts = await realpath(publication);
      const canonicalFolder = await realpath(folder);
      assert.equal((await lstat(folder)).mode & 0o777, 0o700);
      assert.ok(basename(folder).startsWith(basename(report) + ".protected-"));
      assert.notEqual(canonicalFolder, canonicalArtifacts);
      assert.ok(!canonicalFolder.startsWith(canonicalArtifacts + sep));
      const capture = await prepareFixtureCapture(folder, "timeout");
      assert.equal((await lstat(capture.path)).mode & 0o777, 0o600);
      await writeFile(capture.path, "nonce-fragment\uFFFD");
      const metadata = await capture.check();
      assert.equal(metadata.bytes, Buffer.byteLength("nonce-fragment\uFFFD"));
      assert.ok(metadata.device >= 0 && metadata.inode > 0);
    } finally {
      if (folder) await rm(folder, { recursive: true, force: true });
      await rm(work, { recursive: true, force: true });
    }
  },
);

test(
  "pure fixture diagnostics preserves cancellation identity and independent recording failure",
  { timeout: 5000 },
  async () => {
    const diagnostics = new FixtureDiagnostics("broker"),
      cancellation = new Error("controlled cancellation");
    await assert.rejects(
      observeFixtureController(diagnostics, "probe-controller", async () => {
        throw cancellation;
      }),
      (error) => error === cancellation,
    );
    assert.notEqual(
      diagnostics.snapshot(),
      "",
      "The controlled failure category must be retained",
    );
    assert.equal(JSON.parse(diagnostics.snapshot())[0].category, "failed");
    const full = new FixtureDiagnostics("broker");
    for (let n = 0; n < 32; n++)
      full.note({ phase: "startup", category: "started", status: null });
    await assert.rejects(
      observeFixtureController(full, "probe-controller", async () => {
        throw cancellation;
      }),
      (error) => {
        assert.ok(error instanceof AggregateError);
        assert.equal(error.errors[0], cancellation);
        assert.equal(error.errors.length, 2);
        return true;
      },
    );
  },
);

test(
  "pure fixture diagnostics retains unknown status and bounded phase records",
  { timeout: 5000 },
  () => {
    const diagnostics = new FixtureDiagnostics("worker");
    for (let n = 0; n < 32; n++)
      diagnostics.note({
        phase: "shutdown-observed",
        category: "capture-unproved",
        status: null,
      });
    assert.notEqual(
      diagnostics.snapshot(),
      "",
      "The phase records must be retained",
    );
    assert.equal(JSON.parse(diagnostics.snapshot()).length, 32);
    assert.ok(Buffer.byteLength(diagnostics.snapshot()) <= 4096);
    assert.throws(
      () =>
        diagnostics.note({ phase: "ready", category: "started", status: null }),
      /Fixture diagnostic limit/,
    );
  },
);
