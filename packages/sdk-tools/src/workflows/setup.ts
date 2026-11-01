import { join } from "node:path";
import { home, cache, type Language } from "../config.ts";
import { prepare } from "../generation/generators.ts";
import { setupPython } from "../system/python.ts";
import { run } from "../system/run.ts";
import { stage, type Stage, type StageResult } from "./stages.ts";

export async function setupSdk(
  language: Language,
  stages: Stage[],
  admission: StageResult = { passed: true, mayStartProcess: true },
): Promise<StageResult> {
  const preparation = await stage(
    stages,
    "generator-preparation",
    () => prepare(language),
    admission.mayStartProcess,
  );
  let permitted = admission.mayStartProcess && preparation.mayStartProcess;
  if (language === "python") {
    const tooling = await stage(
      stages,
      "python-tooling",
      setupPython,
      permitted && preparation.passed,
    );
    permitted &&= tooling.mayStartProcess;
  }
  if (language === "typescript") {
    const chromium = await stage(
      stages,
      "chromium",
      () =>
        run(
          join(home, "node_modules/.bin/playwright"),
          ["install", "chromium", "--no-shell"],
          "chromium-install",
          { env: { PLAYWRIGHT_BROWSERS_PATH: join(cache, "browsers") } },
        ),
      permitted && preparation.passed,
    );
    permitted &&= chromium.mayStartProcess;
  }
  return {
    passed: stages.every((entry) => entry.status === "passed"),
    mayStartProcess: permitted,
  };
}
