import assert from "node:assert/strict";
import { z } from "zod";
import { profileSchema, observationSchema } from "./protocol.ts";
import type { SdkCase } from "./cases.ts";
import type { Observation } from "./protocol.ts";

export const caseResultSchema = z.object({
  id: z.string(),
  operation: z.string(),
  status: z.enum(["passed", "failed"]),
  error: z.string().optional(),
  calls: z.array(
    z.object({
      observation: observationSchema,
      witness: z.record(z.string(), z.json()),
    }),
  ),
});
export const profileReportSchema = z.object({
  version: z.literal(2),
  profile: profileSchema,
  partial: z.boolean(),
  browserVersion: z.string().min(1).optional(),
  results: z.array(caseResultSchema),
  cleanupError: z.string().optional(),
});
export type CaseResult = z.infer<typeof caseResultSchema>;
export type ProfileReport = z.infer<typeof profileReportSchema>;

export function assertCompleteReports(
  reports: ProfileReport[],
  expectedCases: readonly Pick<
    SdkCase,
    "id" | "operation" | "outcome" | "expectedCalls"
  >[],
  expectedProfiles: readonly string[],
  allowPartial = false,
): void {
  const exact = (
    actual: string[],
    expected: readonly string[],
    label: string,
  ) => {
    assert.equal(new Set(actual).size, actual.length, `Duplicate ${label}`);
    assert.deepEqual(
      [...actual].sort(),
      [...expected].sort(),
      `Incomplete ${label}`,
    );
  };
  exact(
    reports.map((report) => report.profile),
    expectedProfiles,
    "profiles",
  );
  for (const report of reports) {
    assert.ok(
      allowPartial || !report.partial,
      "Partial evidence cannot satisfy complete verification",
    );
    assert.ok(
      !report.cleanupError,
      report.cleanupError ?? "Unexpected cleanup failure",
    );
    exact(
      report.results.map((entry) => entry.id),
      expectedCases.map((entry) => entry.id),
      `${report.profile} cases`,
    );
    for (const result of report.results) {
      assert.equal(
        result.status,
        "passed",
        `${report.profile}/${result.id}: ${result.error}`,
      );
      assert.equal(
        result.operation,
        expectedCases.find((entry) => entry.id === result.id)?.operation,
        "Wrong declared operation",
      );
      const definition = expectedCases.find((entry) => entry.id === result.id)!;
      assert.equal(
        result.calls.length,
        definition.expectedCalls ?? 1,
        "Incomplete case call inventory",
      );
      assert.equal(
        new Set(result.calls.map((call) => call.observation.callId)).size,
        result.calls.length,
        "Duplicate native call result",
      );
      for (const { witness } of result.calls) {
        assert.equal(
          witness.count,
          1,
          "Missing or repeated witnessed dispatch",
        );
        assert.ok(
          typeof witness.method === "string" && witness.method.length > 0,
          "Missing witnessed method",
        );
        assert.ok(
          typeof witness.path === "string" && witness.path.startsWith("/"),
          "Missing witnessed path",
        );
      }
      assertCaseOutcome(
        result.calls,
        expectedCases.find((entry) => entry.id === result.id)!.outcome,
      );
    }
  }
}

export function assertCaseOutcome(
  calls: readonly { observation: Observation }[],
  outcome: "success" | "failure",
): void {
  const kind = outcome === "success" ? "success" : "sdk-error";
  assert.ok(
    calls.some((call) => call.observation.kind === kind),
    "Declared native outcome was not observed",
  );
}
