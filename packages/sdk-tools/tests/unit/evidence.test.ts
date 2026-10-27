import assert from "node:assert/strict";
import { mkdir, mkdtemp, writeFile, rm, readFile } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { createHash } from "node:crypto";
import test from "node:test";
import { assertEvidence, assertStageInventory } from "../../src/ci/evidence.ts";
import { pythonVersions } from "../../src/system/python.ts";
import { root, languages, profiles } from "../../src/config.ts";
import { cases } from "../conformance/index.ts";

async function evidence(directory: string): Promise<void> {
  const python = await pythonVersions();
  const schemaSha256 = createHash("sha256")
    .update(
      await readFile(join(root, "contracts/openapi/v1/inframeld-v1.json")),
    )
    .digest("hex");
  for (const language of languages) {
    const target = join(directory, `sdk-${language}-ubuntu-24.04`);
    await mkdir(target, { recursive: true });
    const names = [
      "regeneration-drift",
      "compilation",
      "native-typing",
      "native-models",
      "native-regressions",
      "http",
      "package-archive",
      "external-consumer",
      ...(language === "rust"
        ? [
            "synthetic-capabilities",
            "generator-library",
            "metadata-disabled-compatibility",
          ]
        : []),
    ];
    await writeFile(
      join(target, `${language}-summary.json`),
      JSON.stringify({
        version: 3,
        action: "verify",
        partial: false,
        schemaSha256,
        environment: { platform: "linux" },
        common: [
          "tooling-typecheck",
          "harness-regressions",
          "backend-contract",
        ].map((name) => ({ name, status: "passed" })),
        results: [
          {
            language,
            status: "passed",
            stages: names.map((name) => ({
              name,
              status: "passed",
              ...(name === "package-archive"
                ? {
                    detail: {
                      filename: "sdk-0.0.0.archive",
                      sha256: "a".repeat(64),
                    },
                  }
                : {}),
              ...(name === "external-consumer"
                ? {
                    detail: {
                      runtimes:
                        language === "python"
                          ? [
                              {
                                role: "minimum",
                                versions: {
                                  python: python.minimum,
                                  httpx: "tested",
                                  pydantic: "tested",
                                },
                              },
                              {
                                role: "primary",
                                versions: {
                                  python: python.primary,
                                  httpx: "tested",
                                  pydantic: "tested",
                                },
                              },
                            ]
                          : [
                              {
                                role: "primary",
                                versions:
                                  language === "rust"
                                    ? { rustc: "tested" }
                                    : { node: "tested" },
                              },
                            ],
                    },
                  }
                : {}),
            })),
          },
        ],
      }),
    );
    for (const profile of profiles[language]) {
      const work = join(target, language, profile);
      await mkdir(work, { recursive: true });
      await writeFile(
        join(work, "report.json"),
        JSON.stringify({
          version: 2,
          profile,
          ...(profile === "typescript-chromium"
            ? { browserVersion: "tested" }
            : {}),
          partial: false,
          results: cases.map((entry) => ({
            id: entry.id,
            operation: entry.operation,
            status: "passed",
            calls: Array.from(
              { length: entry.expectedCalls ?? 1 },
              (_, index) => ({
                observation: {
                  kind: entry.outcome === "success" ? "success" : "sdk-error",
                  ...(entry.outcome === "failure"
                    ? { error: "Expected SDK failure" }
                    : {}),
                  callId: `${entry.id}-${index}`,
                  validation: "generated-model",
                  headers: [],
                },
                witness: { method: "GET", path: "/", count: 1 },
              }),
            ),
          })),
        }),
      );
    }
  }
}

test("CI requires all profiles, common/native stages and applicable platforms", async () => {
  const directory = await mkdtemp(join(tmpdir(), "sdk-evidence-"));
  try {
    await evidence(directory);
    await assertEvidence(directory);
    await assert.rejects(assertEvidence(directory, true), /ENOENT/);
    const file = join(
      directory,
      "sdk-typescript-ubuntu-24.04/typescript/typescript-chromium/report.json",
    );
    await rm(file);
    await assert.rejects(assertEvidence(directory), /ENOENT/);
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});
test("a passing HTTP report cannot hide a missing verification stage or partial run", async () => {
  const directory = await mkdtemp(join(tmpdir(), "sdk-evidence-"));
  try {
    await evidence(directory);
    const file = join(directory, "sdk-rust-ubuntu-24.04/rust-summary.json");
    const summary = JSON.parse(await readFile(file, "utf8")) as {
      partial: boolean;
      results: { stages: unknown[] }[];
    };
    summary.partial = true;
    await writeFile(file, JSON.stringify(summary));
    await assert.rejects(assertEvidence(directory));
    summary.partial = false;
    summary.results[0]!.stages.pop();
    await writeFile(file, JSON.stringify(summary));
    await assert.rejects(assertEvidence(directory));
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});
test("compilation, model checks and HTTP behavior retain distinct stages", () => {
  assertStageInventory(
    [
      "regeneration-drift",
      "compilation",
      "native-typing",
      "native-models",
      "native-regressions",
      "http",
      "package-archive",
      "external-consumer",
    ].map((name) => ({ name, status: "passed" })),
    "typescript",
  );
});

test("CI rejects missing archive identity or installed runtime evidence", async () => {
  const directory = await mkdtemp(join(tmpdir(), "sdk-runtime-evidence-"));
  try {
    await evidence(directory);
    const file = join(directory, "sdk-python-ubuntu-24.04/python-summary.json");
    const value: unknown = JSON.parse(await readFile(file, "utf8"));
    const { z } = await import("zod");
    const summary = z
      .object({
        results: z.array(
          z
            .object({
              stages: z.array(
                z.object({
                  name: z.string(),
                  status: z.string(),
                  detail: z.unknown().optional(),
                }),
              ),
            })
            .passthrough(),
        ),
      })
      .passthrough()
      .parse(value);
    for (const missing of ["external-consumer", "package-archive"]) {
      const changed = structuredClone(summary);
      const stage = changed.results[0]!.stages.find(
        (entry) => entry.name === missing,
      )!;
      delete stage.detail;
      await writeFile(file, JSON.stringify(changed));
      await assert.rejects(assertEvidence(directory));
    }
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});
