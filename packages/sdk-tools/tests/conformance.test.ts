import assert from "node:assert/strict";
import { assertDispatch } from "../src/conformance/assertions.ts";
import { before, after, test } from "node:test";
import { readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { randomUUID } from "node:crypto";
import { z } from "zod";
import { root, home } from "../src/config.ts";
import { cases } from "./conformance/index.ts";
import type {
  CaseCall,
  CaseContext,
  CallResult,
} from "../src/conformance/cases.ts";
import { runtimeSchema } from "../src/conformance/build.ts";
import {
  startProfile,
  type ProfileFixture,
} from "../src/conformance/profile.ts";
import {
  profileSchema,
  driverRequestSchema,
  type JsonValue,
  type SdkCall,
} from "../src/conformance/protocol.ts";
import { controlJson } from "../src/conformance/backend.ts";
import { assertCoverage } from "../src/conformance/coverage.ts";
import {
  assertCompleteReports,
  assertCaseOutcome,
  type ProfileReport,
  type CaseResult,
} from "../src/conformance/report.ts";
import { withResources } from "../src/system/process.ts";
import { budgets } from "../src/system/budgets.ts";
import { installInterruptHandlers } from "../src/system/shutdown.ts";

const profile = profileSchema.parse(process.env.SDK_PROFILE);
const work = z.string().parse(process.env.SDK_PROFILE_WORK);
const reportPath = z.string().parse(process.env.SDK_REPORT_PATH);
const evidencePath = z.string().parse(process.env.SDK_EVIDENCE_REPORT);
const filter = process.env.SDK_CASE;
const selected = filter ? cases.filter((entry) => entry.id === filter) : cases;
assert.ok(
  selected.length,
  "No conformance cases matched the requested selection",
);
const report: ProfileReport = {
  version: 2,
  profile,
  partial: Boolean(filter),
  results: [],
};
let fixture: ProfileFixture;
let operations: Map<string, { method: string; path: string }>;
const removeInterruptHandlers = installInterruptHandlers();

before(
  async (hook) => {
    const runtime = runtimeSchema.parse(
      JSON.parse(
        await readFile(z.string().parse(process.env.SDK_RUNTIME_FILE), "utf8"),
      ),
    );
    const production = z
      .object({ paths: z.record(z.string(), z.unknown()) })
      .parse(
        JSON.parse(
          await readFile(
            join(root, "contracts/openapi/v1/inframeld-v1.json"),
            "utf8",
          ),
        ),
      );
    const synthetic = z
      .object({ paths: z.record(z.string(), z.unknown()) })
      .parse(
        JSON.parse(await readFile(join(home, "fixtures/openapi.json"), "utf8")),
      );
    operations = assertCoverage(
      { paths: { ...production.paths, ...synthetic.paths } },
      cases,
      { [profile]: runtime.bindings },
    );
    fixture = await startProfile(profile, runtime, work, hook.signal);
    if (fixture.browserVersion) report.browserVersion = fixture.browserVersion;
  },
  { timeout: budgets.startup + budgets.cleanup },
);

after(
  async () => {
    try {
      if (fixture) await fixture.close();
    } catch (error) {
      report.cleanupError = String(error);
      throw error;
    } finally {
      removeInterruptHandlers();
      await writeFile(reportPath, JSON.stringify(report, null, 2) + "\n");
    }
    assertCompleteReports([report], selected, [profile], Boolean(filter));
  },
  { timeout: budgets.cleanup },
);

for (const definition of selected)
  test(
    `${profile}/${definition.id}`,
    { timeout: budgets.case },
    async (testContext) => {
      const calls: CallResult[] = [];
      const result: CaseResult = {
        id: definition.id,
        operation: definition.operation,
        status: "failed",
        calls,
      };
      report.results.push(result);
      const caseId = `${definition.id}-${randomUUID()}`;
      let nextCall = 0;
      const sequence = async (inputs: CaseCall[]): Promise<CallResult[]> => {
        const registrationId = `${caseId}-sequence-${nextCall}`;
        const faults: Record<string, unknown> = {};
        const native: SdkCall[] = [];
        for (const input of inputs) {
          const { fault, ...call } = structuredClone(input);
          const id = `${caseId}-${++nextCall}`;
          faults[id] = fault ?? { kind: "none" };
          native.push({
            ...call,
            id,
            headers: { ...call.headers, "X-SDK-Test": id },
          });
        }
        const request = driverRequestSchema.parse({
          version: 2,
          profile,
          caseId,
          baseUrl: fixture.backend.url,
          calls: native,
        });
        const beforeCounts = z
          .record(z.string(), z.number())
          .parse(
            await controlJson(fixture.backend.url + "/sdk-control/counts"),
          );
        return withResources(
          async () => {
            await controlJson(
              `${fixture.backend.url}/sdk-control/cases/${registrationId}`,
              {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ calls: faults }),
                signal: testContext.signal,
              },
            );
            const observations = await fixture.execute(
              request,
              testContext.signal,
            );
            const evidence = z
              .object({
                observations: z.record(
                  z.string(),
                  z.record(z.string(), z.json()),
                ),
                counts: z.record(z.string(), z.number()),
              })
              .parse(
                await controlJson(
                  `${fixture.backend.url}/sdk-control/cases/${registrationId}`,
                  { signal: testContext.signal },
                ),
              );
            const witnesses = z
              .record(z.string(), z.record(z.string(), z.json()))
              .parse(evidence.observations);
            const counts = z
              .record(z.string(), z.number())
              .parse(
                await controlJson(fixture.backend.url + "/sdk-control/counts"),
              );
            assert.equal(
              (counts._total ?? 0) - (beforeCounts._total ?? 0),
              native.length,
              "Native sequence dispatched extra or missing requests, including untagged requests",
            );
            const observed: CallResult[] = [];
            for (const call of native) {
              const observation = observations.find(
                (entry) => entry.callId === call.id,
              )!;
              const witness: Record<string, JsonValue> = {
                ...witnesses[call.id],
                count: evidence.counts[call.id] ?? 0,
              };
              const entry = { observation, witness };
              calls.push(entry);
              observed.push(entry);
              assert.equal(
                call.operation,
                definition.operation,
                "Case invoked a different declared operation",
              );
              const operation = operations.get(call.operation)!;
              assertDispatch(
                witness,
                operation.method,
                operation.path.replace(/\{([^}]+)\}/g, (_, name: string) =>
                  encodeURIComponent(call.path?.[name] ?? ""),
                ),
              );
            }
            return observed;
          },
          () =>
            controlJson(
              `${fixture.backend.url}/sdk-control/cases/${registrationId}`,
              { method: "DELETE" },
            ).then(() => {}),
        );
      };
      const context: CaseContext = {
        profile,
        origin: fixture.origin,
        sequence,
        call: async (input) => (await sequence([input]))[0]!,
      };
      try {
        await definition.run(context);
        assertCaseOutcome(calls, definition.outcome);
        result.status = "passed";
      } catch (error) {
        result.error =
          error instanceof Error
            ? (error.stack ?? String(error))
            : String(error);
        console.error(
          `Reproduce: pnpm sdk:test --profile ${profile} --case ${definition.id}\nEvidence: ${evidencePath}`,
        );
        throw error;
      }
    },
  );
