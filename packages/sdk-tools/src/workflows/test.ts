import { mkdir, writeFile, readFile } from "node:fs/promises";
import { join } from "node:path";
import {
  artifacts,
  home,
  profiles,
  type Language,
  type Profile,
} from "../config.ts";
import { profileBudget, budgets } from "../system/budgets.ts";
import { run } from "../system/run.ts";
import {
  buildRuntime,
  checkNativeModels,
  checkNativeRegressions,
  typecheckNative,
  type Runtime,
} from "../conformance/build.ts";
import {
  profileReportSchema,
  assertCompleteReports,
  type ProfileReport,
} from "../conformance/report.ts";
import { cases } from "../../tests/conformance/index.ts";
import { stage, type Stage } from "./stages.ts";

export interface TestSelection {
  profile?: Profile;
  caseId?: string;
}

export async function testConformance(
  language: Language,
  work: string,
  runtime: Runtime,
  selection: TestSelection = {},
): Promise<{ profiles: string[]; cases: number; reports: ProfileReport[] }> {
  const file = join(work, "runtime.json");
  await writeFile(file, JSON.stringify(runtime));
  const reports: ProfileReport[] = [],
    errors: unknown[] = [];
  const selected = profiles[language].filter(
    (profile) => !selection.profile || profile === selection.profile,
  );
  for (const profile of selected) {
    const directory = join(work, profile);
    await mkdir(directory, { recursive: true });
    const reportPath = join(directory, "report.json");
    try {
      const result = await run(
        process.execPath,
        [
          "--import",
          join(home, "node_modules/tsx/dist/loader.mjs"),
          "--test",
          "--test-reporter=spec",
          "--test-reporter-destination=stdout",
          "--test-reporter=junit",
          `--test-reporter-destination=${join(directory, "junit.xml")}`,
          join(home, "tests/conformance.test.ts"),
        ],
        `${profile}-tests`,
        {
          env: {
            SDK_PROFILE: profile,
            SDK_PROFILE_WORK: directory,
            SDK_REPORT_PATH: reportPath,
            SDK_EVIDENCE_REPORT: join(
              artifacts,
              language,
              profile,
              "report.json",
            ),
            SDK_RUNTIME_FILE: file,
            ...(selection.caseId ? { SDK_CASE: selection.caseId } : {}),
          },
          timeout: profileBudget(),
          cleanupTimeout: budgets.cleanup,
        },
      );
      console.log(result.stdout);
    } catch (error) {
      errors.push(error);
    }
    try {
      reports.push(
        profileReportSchema.parse(
          JSON.parse(await readFile(reportPath, "utf8")),
        ),
      );
    } catch (error) {
      errors.push(
        new Error(`Missing/invalid ${profile} report at ${reportPath}`, {
          cause: error,
        }),
      );
    }
  }
  const expected = selection.caseId
    ? cases.filter((entry) => entry.id === selection.caseId)
    : cases;
  try {
    assertCompleteReports(
      reports,
      expected,
      selected,
      Boolean(selection.caseId),
    );
  } catch (error) {
    errors.push(error);
  }
  if (errors.length)
    throw new AggregateError(errors, `${language} conformance failed`);
  return { profiles: selected, cases: expected.length, reports };
}

export async function testSdk(
  language: Language,
  work: string,
  stages: Stage[],
  selection: TestSelection = {},
): Promise<void> {
  let runtime: Runtime | undefined;
  await stage(stages, "compilation", async () => {
    runtime = await buildRuntime(language, work);
    return { bindings: runtime.bindings };
  });
  await stage(stages, "native-typing", () => typecheckNative(language));
  await stage(stages, "native-models", async () => {
    if (!runtime)
      throw new Error("Native model checks blocked by compilation failure");
    await checkNativeModels(language, runtime);
  });
  await stage(stages, "native-regressions", async () => {
    if (!runtime)
      throw new Error("Driver regressions blocked by compilation failure");
    await checkNativeRegressions(language, runtime);
  });
  await stage(stages, "http", async () => {
    if (!runtime)
      throw new Error("HTTP behavior blocked by compilation failure");
    return testConformance(language, work, runtime, selection);
  });
  if (language === "rust")
    await stage(stages, "synthetic-capabilities", () =>
      run(
        "cargo",
        ["test", "--locked", "-p", "inframeld-sdk-test-rust-capabilities"],
        "rust-capabilities",
      ),
    );
}
