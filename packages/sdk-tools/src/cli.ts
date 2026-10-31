import {
  readFile,
  writeFile,
  mkdir,
  mkdtemp,
  rm,
  readdir,
} from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { createHash } from "node:crypto";
import { home, root, artifacts } from "./config.ts";
import { argumentsFor } from "./arguments.ts";
import { manifest } from "./generation/source.ts";
import { generate } from "./workflows/generate.ts";
import { setupSdk } from "./workflows/setup.ts";
import { testSdk } from "./workflows/test.ts";
import { verifyPackage } from "./workflows/verify.ts";
import { stage, describeError, type Stage } from "./workflows/stages.ts";
import { run } from "./system/run.ts";
import { budgets } from "./system/budgets.ts";
import { withinDeadline } from "./system/deadline.ts";
import { installInterruptHandlers } from "./system/shutdown.ts";

const selection = argumentsFor(process.argv.slice(2));
const removeHandlers = installInterruptHandlers();
await mkdir(artifacts, { recursive: true });
const summary = {
  version: 3,
  action: selection.action,
  selection: selection.selected,
  partial: selection.partial,
  createdAt: new Date().toISOString(),
  schemaSha256: createHash("sha256")
    .update(
      await readFile(join(root, "contracts/openapi/v1/inframeld-v1.json")),
    )
    .digest("hex"),
  environment: {
    node: process.version,
    platform: process.platform,
    architecture: process.arch,
  },
  generators: manifest,
  common: [] as Stage[],
  results: [] as {
    language: string;
    status: "passed" | "failed";
    stages: Stage[];
  }[],
};

let subprocessAllowed = true;
let harnessPassed = true;
try {
  if (["test", "verify"].includes(selection.action)) {
    const typing = await stage(summary.common, "tooling-typecheck", () =>
      run(
        join(home, "node_modules/.bin/tsc"),
        ["-p", join(home, "tsconfig.tools.json")],
        "tooling-typecheck",
      ),
    );
    subprocessAllowed &&= typing.mayStartProcess;
    const harness = await stage(
      summary.common,
      "harness-regressions",
      async () => {
        const tests = (await readdir(join(home, "tests/unit")))
          .filter((name) => name.endsWith(".test.ts"))
          .map((name) => join(home, "tests/unit", name));
        await run(
          process.execPath,
          [
            "--import",
            join(home, "node_modules/tsx/dist/loader.mjs"),
            "--test",
            ...tests,
          ],
          "harness-regressions",
        );
      },
      subprocessAllowed,
    );
    harnessPassed = typing.passed && harness.passed;
    // An outer test runner cannot prove cleanup of failed nested fixtures.
    subprocessAllowed &&= harnessPassed && harness.mayStartProcess;
  }
  if (selection.action === "verify") {
    const contract = await stage(
      summary.common,
      "backend-contract",
      () =>
        run(
          "uv",
          [
            "run",
            "--directory",
            "apps/backend",
            "pytest",
            "tests/unit/contract",
          ],
          "backend-contract",
        ),
      subprocessAllowed,
    );
    subprocessAllowed &&= contract.mayStartProcess;
    harnessPassed &&= contract.passed;
  }

  for (const language of selection.selected) {
    const stages: Stage[] = [];
    const work = await mkdtemp(join(tmpdir(), `inframeld-sdk-${language}-`));
    console.log(
      `\n${language.toUpperCase()}${selection.partial ? " (partial local run)" : ""}`,
    );
    try {
      if (selection.action === "setup") {
        const result = await setupSdk(language, stages, {
          passed: true,
          mayStartProcess: subprocessAllowed,
        });
        subprocessAllowed &&= result.mayStartProcess;
      } else {
        if (["generate", "check", "verify"].includes(selection.action)) {
          const generated = await stage(
            stages,
            selection.action === "generate"
              ? "generation"
              : "regeneration-drift",
            () => generate(language, selection.action !== "generate"),
            subprocessAllowed,
          );
          subprocessAllowed &&= generated.mayStartProcess;
        }
        if (["test", "verify"].includes(selection.action)) {
          const result = await testSdk(language, work, stages, selection, {
            passed: harnessPassed,
            mayStartProcess: subprocessAllowed,
          });
          subprocessAllowed &&= result.mayStartProcess;
        }
        if (selection.action === "verify") {
          const result = await verifyPackage(language, work, stages, {
            passed: harnessPassed,
            mayStartProcess: subprocessAllowed,
          });
          subprocessAllowed &&= result.mayStartProcess;
        }
      }
    } catch (error) {
      subprocessAllowed = false;
      stages.push({
        name: "workflow",
        status: "failed",
        milliseconds: 0,
        error: describeError(error),
      });
    } finally {
      // Reports and backend logs survive deletion of temporary runtimes and consumers.
      const { cp } = await import("node:fs/promises");
      try {
        for (const entry of await readdir(work))
          if (
            entry === language ||
            entry === "consumer-server" ||
            entry.startsWith("typescript-") ||
            (entry.startsWith("python-") &&
              !entry.startsWith("python-consumer-"))
          ) {
            const { stat } = await import("node:fs/promises");
            const from = join(work, entry);
            if (!(await stat(from)).isDirectory()) continue;
            if (entry === "python-runtime") continue;
            await cp(from, join(artifacts, language, entry), {
              recursive: true,
            });
          }
        if (subprocessAllowed)
          await withinDeadline(
            rm(work, { recursive: true, force: true }),
            budgets.cleanup,
          );
        else
          stages.push({
            name: "cleanup",
            status: "failed",
            milliseconds: 0,
            error: "Cleanup unconfirmed, private work retained",
          });
      } catch (error) {
        stages.push({
          name: "cleanup",
          status: "failed",
          milliseconds: 0,
          error: describeError(error),
        });
      }
    }
    summary.results.push({
      language,
      status: stages.every((entry) => entry.status === "passed")
        ? "passed"
        : "failed",
      stages,
    });
  }
} finally {
  removeHandlers();
  await writeFile(
    join(artifacts, "summary.json"),
    JSON.stringify(summary, null, 2) + "\n",
  );
  for (const result of summary.results)
    await writeFile(
      join(artifacts, `${result.language}-summary.json`),
      JSON.stringify(
        { ...summary, selection: [result.language], results: [result] },
        null,
        2,
      ) + "\n",
    );
}
console.log(`\nEvidence: ${artifacts}/summary.json`);
process.exitCode =
  summary.common.every((entry) => entry.status === "passed") &&
  summary.results.length === selection.selected.length &&
  summary.results.every((entry) => entry.status === "passed")
    ? 0
    : 1;
