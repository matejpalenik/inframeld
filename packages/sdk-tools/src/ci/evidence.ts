import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { createHash } from "node:crypto";
import { z } from "zod";
import { root, languages, profiles, type Language } from "../config.ts";
import { pythonVersions } from "../system/python.ts";
import { cases } from "../../tests/conformance/index.ts";
import {
  profileReportSchema,
  assertCompleteReports,
} from "../conformance/report.ts";

const stageSchema = z.object({
  name: z.string(),
  status: z.enum(["passed", "failed"]),
  detail: z.unknown().optional(),
});
const summarySchema = z.object({
  version: z.literal(3),
  action: z.literal("verify"),
  partial: z.literal(false),
  schemaSha256: z.string(),
  environment: z.object({ platform: z.string() }),
  common: z.array(stageSchema),
  results: z.array(
    z.object({
      language: z.enum(languages),
      status: z.literal("passed"),
      stages: z.array(stageSchema),
    }),
  ),
});

export function assertStageInventory(
  stages: z.infer<typeof stageSchema>[],
  language: Language,
): void {
  const expected = [
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
  assert.deepEqual(
    stages.map((entry) => entry.name).sort(),
    expected.sort(),
    "Missing or unexpected verification stage",
  );
  assert.ok(
    stages.every((entry) => entry.status === "passed"),
    "A required SDK stage failed",
  );
}

async function assertPackageEvidence(
  stages: z.infer<typeof stageSchema>[],
  language: Language,
): Promise<void> {
  z.object({
    filename: z.string().min(1),
    sha256: z.string().regex(/^[a-f0-9]{64}$/),
  }).parse(stages.find((stage) => stage.name === "package-archive")?.detail);
  const evidence = z
    .object({
      runtimes: z.array(
        z.object({
          role: z.enum(["minimum", "primary"]),
          versions: z.record(z.string(), z.string().min(1)),
        }),
      ),
    })
    .parse(stages.find((stage) => stage.name === "external-consumer")?.detail);
  assert.deepEqual(
    evidence.runtimes.map((runtime) => runtime.role).sort(),
    language === "python" ? ["minimum", "primary"] : ["primary"],
    "Incomplete installed runtime evidence",
  );
  for (const runtime of evidence.runtimes) {
    for (const key of language === "python"
      ? ["python", "httpx", "pydantic"]
      : [language === "rust" ? "rustc" : "node"])
      assert.ok(
        runtime.versions[key],
        `Missing installed ${key} runtime evidence`,
      );
  }
  if (language === "python") {
    const expected = await pythonVersions();
    for (const runtime of evidence.runtimes)
      assert.equal(
        runtime.role === "minimum"
          ? runtime.versions.python
              ?.split(/\s+/)[0]
              ?.split(".")
              .slice(0, 2)
              .join(".")
          : runtime.versions.python?.split(/\s+/)[0],
        expected[runtime.role],
        `Unexpected ${runtime.role} Python interpreter`,
      );
  }
}

export async function assertEvidence(
  directory: string,
  macos = false,
): Promise<void> {
  const schemaHash = createHash("sha256")
    .update(
      await readFile(join(root, "contracts/openapi/v1/inframeld-v1.json")),
    )
    .digest("hex");
  for (const os of ["ubuntu-24.04", ...(macos ? ["macos-15"] : [])])
    for (const language of languages) {
      const artifact = join(directory, `sdk-${language}-${os}`);
      const summary = summarySchema.parse(
        JSON.parse(
          await readFile(join(artifact, `${language}-summary.json`), "utf8"),
        ),
      );
      assert.equal(
        summary.schemaSha256,
        schemaHash,
        "Evidence belongs to a different OpenAPI contract",
      );
      assert.equal(
        summary.environment.platform,
        os.startsWith("ubuntu") ? "linux" : "darwin",
      );
      assert.deepEqual(
        summary.common.map((entry) => entry.name).sort(),
        ["tooling-typecheck", "harness-regressions", "backend-contract"].sort(),
        "Incomplete common checks",
      );
      assert.ok(
        summary.common.every((entry) => entry.status === "passed"),
        "A common verification check failed",
      );
      assert.equal(summary.results.length, 1);
      const result = summary.results[0]!;
      assert.equal(result.language, language);
      assertStageInventory(result.stages, language);
      await assertPackageEvidence(result.stages, language);
      const reports = [];
      for (const profile of profiles[language]) {
        const report = profileReportSchema.parse(
          JSON.parse(
            await readFile(
              join(artifact, language, profile, "report.json"),
              "utf8",
            ),
          ),
        );
        if (profile === "typescript-chromium")
          assert.ok(
            report.browserVersion,
            "Missing actual Chromium runtime version",
          );
        reports.push(report);
      }
      assertCompleteReports(reports, cases, profiles[language]);
    }
}
if (process.argv[1] === fileURLToPath(import.meta.url))
  await assertEvidence(process.argv[2]!, process.argv[3] === "true");
