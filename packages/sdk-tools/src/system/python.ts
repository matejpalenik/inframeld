import { mkdir, readdir, rm, readFile } from "node:fs/promises";
import { join } from "node:path";
import { cache, home, root, packageRoot } from "../config.ts";
import { parse } from "smol-toml";
import { z } from "zod";
import { withResources } from "./process.ts";
import { run } from "./run.ts";
export const python = join(cache, "python/bin/python");
/** The SDK declares its minimum, while the repository pins the primary toolchain. */
export async function pythonVersions(): Promise<{
  minimum: string;
  primary: string;
}> {
  const project = z
    .object({ project: z.object({ "requires-python": z.string() }) })
    .parse(
      parse(
        await readFile(join(packageRoot("python"), "pyproject.toml"), "utf8"),
      ),
    );
  const tools = z
    .object({
      tools: z.object({ python: z.string().regex(/^\d+\.\d+\.\d+$/) }),
    })
    .parse(parse(await readFile(join(root, "mise.toml"), "utf8")));
  const minimum =
    project.project["requires-python"].match(/>=\s*(\d+\.\d+)/)?.[1];
  if (!minimum)
    throw new Error("Python SDK must declare an explicit minimum interpreter");
  return { minimum, primary: tools.tools.python };
}

export async function setupPython(): Promise<void> {
  const versions = await pythonVersions();
  await run(
    "uv",
    [
      "venv",
      join(cache, "python"),
      "--python",
      versions.primary,
      "--allow-existing",
    ],
    "python-environment",
  );
  await run(
    "uv",
    [
      "pip",
      "sync",
      "--python",
      python,
      "--require-hashes",
      join(home, "requirements.lock"),
    ],
    "python-install",
  );
}
export async function wheel(
  directory: string,
  output: string,
  label: string,
): Promise<string> {
  await rm(join(directory, "build"), { recursive: true, force: true });
  await mkdir(output, { recursive: true });
  await withResources(
    () =>
      run(
        python,
        // The standard frontend builds the wheel from a fresh sdist, excluding
        // stale local build/lib files without a handwritten source-copy pipeline.
        ["-m", "build", "--no-isolation", "--outdir", output],
        label,
        { cwd: directory },
      ),
    () => rm(join(directory, "build"), { recursive: true, force: true }),
  );
  const files = (await readdir(output)).filter((name) => name.endsWith(".whl"));
  if (files.length !== 1)
    throw new Error(
      `Expected one freshly built wheel in ${output}, found ${files.join(", ")}`,
    );
  return join(output, files[0]!);
}
