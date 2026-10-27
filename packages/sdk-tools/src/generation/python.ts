import assert from "node:assert/strict";
import { readFile, writeFile, mkdir, cp, rm } from "node:fs/promises";
import { join, dirname } from "node:path";
import { run } from "../system/run.ts";
import { sourceInputs } from "./source.ts";
import type { GenerationTarget } from "./types.ts";

// Native selective generation retains runtime support, including PEP 561 typing,
// without generating a second package definition, usage guide or CI configuration.
const runtimeSupport = [
  "configuration.py",
  "__init__.py",
  "exceptions.py",
  "api_client.py",
  "api_response.py",
  "rest.py",
  "sync_helper.py",
  "py.typed",
];

const patchedResources = [
  "python/model_generic.mustache",
  "python/api_client.mustache",
  "python/api_response.mustache",
  "python/api.mustache",
  "python/partial_api.mustache",
  "python/exceptions.mustache",
  "python/httpx/rest.mustache",
];

export async function preparePython(): Promise<string> {
  const { archive, patches, destination } = await sourceInputs("python");
  await rm(destination, { recursive: true, force: true });
  await mkdir(destination, { recursive: true });
  const source = join(destination, "resources");
  await run(
    "unzip",
    ["-q", archive, ...patchedResources, "-d", source],
    "python-extract",
  );
  await run("git", ["init", "--quiet", source], "python-source-git");
  for (const p of patches) {
    await run(
      "git",
      ["apply", "--check", "--whitespace=error-all", p.path],
      "python-patch-check",
      { cwd: source },
    );
    await run(
      "git",
      ["apply", "--whitespace=error-all", p.path],
      "python-patch",
      { cwd: source },
    );
  }
  const jar = join(destination, "generator.jar");
  await cp(archive, jar);
  await run(
    "jar",
    [
      "uf",
      jar,
      ...patchedResources.flatMap((resource) => ["-C", source, resource]),
    ],
    "python-jar",
  );
  return jar;
}
export async function emitPython(
  target: GenerationTarget,
  tool: string,
  destination: string,
): Promise<void> {
  await mkdir(destination, { recursive: true });
  const metadata = await readFile(
    join(target.directory, "pyproject.toml"),
    "utf8",
  );
  const version = metadata.match(/^version\s*=\s*"([^"]+)"/m)?.[1];
  assert.ok(version, "Python package version is required");
  const properties = {
    library: "httpx",
    supportHttpxSync: true,
    packageVersion: version,
    packageName:
      target.kind === "production" ? "inframeld_sdk" : "inframeld_sdk_fixtures",
    projectName:
      target.kind === "production"
        ? "inframeld-sdk"
        : "inframeld-sdk-test-fixtures",
    disallowAdditionalPropertiesIfNotPresent: false,
    hideGenerationTimestamp: true,
  };
  const config = join(dirname(destination), "python.json");
  await writeFile(config, JSON.stringify(properties));
  await run(
    "java",
    [
      "-jar",
      tool,
      "generate",
      "-g",
      "python",
      "-i",
      target.schema,
      "-o",
      destination,
      "-c",
      config,
      "--global-property",
      `apis,models,supportingFiles=${runtimeSupport.join(":")},apiTests=false,modelTests=false,apiDocs=false,modelDocs=false`,
    ],
    `generate-python-${target.kind}`,
  );
}
