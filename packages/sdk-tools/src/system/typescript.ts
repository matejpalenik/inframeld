import { rm } from "node:fs/promises";
import { join } from "node:path";
import { packageRoot } from "../config.ts";
import { run } from "./run.ts";

/** tsc leaves removed files in outDir, so verification starts from clean output. */
export async function buildTypescript(label: string): Promise<void> {
  await rm(join(packageRoot("typescript"), "dist"), {
    recursive: true,
    force: true,
  });
  await run("pnpm", ["--filter", "@inframeld/sdk", "build"], label);
}
