import assert from "node:assert/strict";
import test from "node:test";
import { assertCoverage } from "../../src/conformance/coverage.ts";

const schema = { paths: { "/session": { get: { operationId: "session" } } } };
const cases = [
  { id: "session", operation: "session", outcome: "success" as const },
];
test("a new delivered operation needs a scenario and every native binding", () => {
  assert.throws(
    () => assertCoverage(schema, [], { rust: ["session"] }),
    /scenario/,
  );
  assert.throws(() => assertCoverage(schema, cases, { rust: [] }), /binding/);
  assert.doesNotThrow(() =>
    assertCoverage(schema, cases, { rust: ["session"] }),
  );
});
test("a case cannot claim coverage for an unknown operation", () => {
  assert.throws(
    () =>
      assertCoverage(
        schema,
        [
          ...cases,
          { id: "wrong", operation: "missing", outcome: "success" as const },
        ],
        { rust: ["session"] },
      ),
    /Unknown/,
  );
});
