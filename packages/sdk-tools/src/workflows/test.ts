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
import { stage, type Stage, type StageResult } from "./stages.ts";

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
    let profileCompleted = true;
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
      profileCompleted = false;
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
    // Read any completed report before blocking subsequent runtime admission.
    if (!profileCompleted) break;
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
  admission: StageResult = { passed: true, mayStartProcess: true },
  recordStage: typeof stage = stage,
): Promise<StageResult> {
  let runtime: Runtime | undefined;
  let permitted = admission.mayStartProcess;
  const compilation = await recordStage(
    stages,
    "compilation",
    async () => {
      runtime = await buildRuntime(language, work);
      return { bindings: runtime.bindings };
    },
    permitted,
  );
  permitted &&= compilation.mayStartProcess;
  const typing = await recordStage(
    stages,
    "native-typing",
    () => typecheckNative(language),
    permitted,
  );
  permitted &&= typing.mayStartProcess;
  const models = await recordStage(
    stages,
    "native-models",
    async () => {
      if (!runtime)
        throw new Error("Native model checks blocked by compilation failure");
      await checkNativeModels(language, runtime);
    },
    permitted && admission.passed && compilation.passed,
  );
  permitted &&= models.mayStartProcess;
  const nativeAdmitted = permitted && admission.passed && compilation.passed;
  const regressions = await recordStage(
    stages,
    "native-regressions",
    async () => {
      if (!runtime)
        throw new Error("Driver regressions blocked by compilation failure");
      await checkNativeRegressions(language, runtime);
    },
    nativeAdmitted,
  );
  // A clean outer launcher cannot establish failed nested fixture ownership.
  permitted &&=
    regressions.mayStartProcess && (!nativeAdmitted || regressions.passed);
  const http = await recordStage(
    stages,
    "http",
    async () => {
      if (!runtime)
        throw new Error("HTTP behavior blocked by compilation failure");
      return testConformance(language, work, runtime, selection);
    },
    permitted && admission.passed && compilation.passed,
  );
  permitted &&= http.mayStartProcess;
  if (language === "rust") {
    const synthetic = await recordStage(
      stages,
      "synthetic-capabilities",
      () =>
        run(
          "cargo",
          ["test", "--locked", "-p", "inframeld-sdk-test-rust-capabilities"],
          "rust-capabilities",
        ),
      permitted && admission.passed && compilation.passed,
    );
    permitted &&= synthetic.mayStartProcess;
  }
  return {
    passed: stages.every((entry) => entry.status === "passed"),
    mayStartProcess: permitted,
  };
}
