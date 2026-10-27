import { mkdir, writeFile, rm, cp } from "node:fs/promises";
import { join } from "node:path";
import { home, packageRoot } from "../config.ts";
import { run } from "../system/run.ts";
import { wheel, python, pythonVersions } from "../system/python.ts";
import { z } from "zod";
import type { ConsumerEvidence } from "./evidence.ts";
import { withResources } from "../system/process.ts";

export async function archivePython(work: string): Promise<string> {
  const external = join(work, "external-python");
  await mkdir(external, { recursive: true });
  const staleDirectory = join(packageRoot("python"), "build/lib/inframeld_sdk");
  const stale = join(staleDirectory, "__sdk_stale_probe__.py");
  const archive = await withResources(
    async () => {
      // Building a wheel from the sdist must exclude stale local build/lib files.
      await mkdir(staleDirectory, { recursive: true });
      await writeFile(
        stale,
        "raise RuntimeError('Stale build artifact must not ship')\n",
      );
      const archive = await wheel(
        packageRoot("python"),
        external,
        "python-package",
      );
      await run(
        python,
        [join(home, "consumers/python/archive.py"), archive],
        "python-archive-contents",
      );
      return archive;
    },
    () => rm(stale, { force: true }),
  );
  return archive;
}

export async function consumePython(
  work: string,
  archive: string,
  baseUrl: string,
): Promise<ConsumerEvidence> {
  const runtimes: ConsumerEvidence["runtimes"] = [];
  const versions = await pythonVersions();
  for (const [role, version] of [
    ["minimum", versions.minimum],
    ["primary", versions.primary],
  ] as const) {
    const external = join(work, `python-consumer-${version}`);
    await mkdir(external, { recursive: true });
    const environment = join(external, "venv");
    await run(
      "uv",
      ["venv", environment, "--python", version],
      `python-${version}-external-environment`,
    );
    const executable = join(environment, "bin/python");
    await run(
      "uv",
      [
        "pip",
        "install",
        "--python",
        executable,
        "--constraint",
        join(home, "requirements.lock"),
        archive,
      ],
      `python-${version}-external-install`,
    );
    await cp(join(home, "consumers/python/main.py"), join(external, "main.py"));
    const result = await run(
      executable,
      [join(external, "main.py"), baseUrl],
      `python-${version}-external-lifecycle`,
      { cwd: external },
    );
    const observed = z
      .object({
        python: z.string().min(1),
        httpx: z.string().min(1),
        pydantic: z.string().min(1),
        package: z.string().min(1),
      })
      .parse(JSON.parse(result.stdout));
    runtimes.push({
      role,
      versions: {
        python: observed.python,
        httpx: observed.httpx,
        pydantic: observed.pydantic,
      },
    });
  }
  return { runtimes };
}
