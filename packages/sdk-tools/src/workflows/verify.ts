import type { Language } from "../config.ts";
import { prepare } from "../generation/generators.ts";
import { bodyOnlyRegression } from "../generation/body-only.ts";
import { createHash } from "node:crypto";
import { basename } from "node:path";
import { mkdir, readFile } from "node:fs/promises";
import { join } from "node:path";
import { startBackend } from "../conformance/backend.ts";
import { withResources } from "../system/process.ts";
import { buildArchive, consumePackage } from "./package.ts";
import { stage, type Stage, type StageResult } from "./stages.ts";

export async function verifyPackage(
  language: Language,
  work: string,
  stages: Stage[],
  admission: StageResult = { passed: true, mayStartProcess: true },
): Promise<StageResult> {
  let permitted = admission.mayStartProcess;
  if (language === "rust") {
    const generator = await stage(
      stages,
      "generator-library",
      () => prepare(language, true),
      permitted,
    );
    permitted &&= generator.mayStartProcess;
    const compatibility = await stage(
      stages,
      "metadata-disabled-compatibility",
      bodyOnlyRegression,
      permitted && generator.passed,
    );
    permitted &&= compatibility.mayStartProcess;
  }
  let archive: string | undefined;
  const packaged = await stage(
    stages,
    "package-archive",
    async () => {
      archive = await buildArchive(language, work);
      return {
        filename: basename(archive),
        sha256: createHash("sha256")
          .update(await readFile(archive))
          .digest("hex"),
      };
    },
    permitted,
  );
  permitted &&= packaged.mayStartProcess;
  const consumed = await stage(
    stages,
    "external-consumer",
    async () => {
      if (!archive)
        throw new Error("Consumer blocked by package archive failure");
      const serverWork = join(work, "consumer-server");
      await mkdir(serverWork, { recursive: true });
      const backend = await startBackend(serverWork);
      return withResources(
        () => consumePackage(language, work, archive!, backend.url),
        backend.close,
      );
    },
    permitted && admission.passed && packaged.passed,
  );
  permitted &&= consumed.mayStartProcess;
  return {
    passed: stages.every((entry) => entry.status === "passed"),
    mayStartProcess: permitted,
  };
}
