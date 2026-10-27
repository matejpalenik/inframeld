import assert from "node:assert/strict";
import test from "node:test";
import {
  assertCompleteReports,
  type ProfileReport,
} from "../../src/conformance/report.ts";

const expected = [
  {
    id: "health",
    operation: "getHealth" as const,
    outcome: "success" as const,
  },
];
const report = (): ProfileReport => ({
  version: 2,
  profile: "rust",
  partial: false,
  results: [
    {
      id: "health",
      operation: "getHealth",
      status: "passed",
      calls: [
        {
          observation: {
            kind: "success",
            callId: "one",
            status: 200,
            body: { status: "ok" },
            validation: "generated-model",
            headers: [],
          },
          witness: { count: 1, method: "GET", path: "/health" },
        },
      ],
    },
  ],
});

test("complete native results pass and missing, duplicate or unexpected inventories fail", () => {
  assertCompleteReports([report()], expected, ["rust"]);
  for (const reports of [
    [],
    [report(), report()],
    [{ ...report(), profile: "python-sync" as const }],
    [{ ...report(), results: [] }],
    [{ ...report(), results: [...report().results, ...report().results] }],
  ])
    assert.throws(() => assertCompleteReports(reports, expected, ["rust"]));
});
test("partial, failed and cleanup-failed reports cannot satisfy verification", () => {
  for (const changed of [
    { ...report(), partial: true },
    { ...report(), cleanupError: "close failed" },
    {
      ...report(),
      results: [{ ...report().results[0]!, status: "failed" as const }],
    },
  ])
    assert.throws(() => assertCompleteReports([changed], expected, ["rust"]));
});
test("declared operation coverage requires an actual native call", () => {
  const empty = report();
  empty.results[0]!.calls = [];
  assert.throws(
    () => assertCompleteReports([empty], expected, ["rust"]),
    /call inventory/,
  );
  const wrong = report();
  wrong.results[0]!.operation = "getCurrentSession";
  assert.throws(
    () => assertCompleteReports([wrong], expected, ["rust"]),
    /operation/,
  );
});

test("a success label cannot establish operation coverage after only native failures", () => {
  const failed = report();
  failed.results[0]!.calls[0]!.observation = {
    kind: "sdk-error",
    callId: "one",
    validation: "none",
    headers: [],
    error: "unsupported",
  };
  assert.throws(
    () =>
      assertCompleteReports(
        [failed],
        [{ id: "health", operation: "getHealth", outcome: "success" }],
        ["rust"],
      ),
    /outcome/,
  );
});

test("recovery evidence cannot omit calls, duplicate native identities or lose witnesses", () => {
  const recovered = report();
  recovered.results[0]!.calls.push({
    ...structuredClone(recovered.results[0]!.calls[0]!),
    observation: {
      ...recovered.results[0]!.calls[0]!.observation,
      callId: "two",
    },
  });
  const sequence = [{ ...expected[0]!, expectedCalls: 2 }];
  assertCompleteReports([recovered], sequence, ["rust"]);
  for (const mutate of [
    (value: ProfileReport) => {
      value.results[0]!.calls.pop();
    },
    (value: ProfileReport) => {
      value.results[0]!.calls[1]!.observation.callId = "one";
    },
    (value: ProfileReport) => {
      value.results[0]!.calls[0]!.witness = {};
    },
    (value: ProfileReport) => {
      value.results[0]!.calls[0]!.witness.count = 2;
    },
  ]) {
    const changed = structuredClone(recovered);
    mutate(changed);
    assert.throws(() => assertCompleteReports([changed], sequence, ["rust"]));
  }
});
