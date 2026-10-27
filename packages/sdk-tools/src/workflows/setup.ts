import { join } from "node:path";
import { home, cache, type Language } from "../config.ts";
import { prepare } from "../generation/generators.ts";
import { setupPython } from "../system/python.ts";
import { run } from "../system/run.ts";
import { stage, type Stage } from "./stages.ts";

export async function setupSdk(
  language: Language,
  stages: Stage[],
): Promise<void> {
  await stage(stages, "generator-preparation", () => prepare(language));
  if (language === "python") await stage(stages, "python-tooling", setupPython);
  if (language === "typescript")
    await stage(stages, "chromium", () =>
      run(
        join(home, "node_modules/.bin/playwright"),
        ["install", "chromium", "--no-shell"],
        "chromium-install",
        { env: { PLAYWRIGHT_BROWSERS_PATH: join(cache, "browsers") } },
      ),
    );
}
