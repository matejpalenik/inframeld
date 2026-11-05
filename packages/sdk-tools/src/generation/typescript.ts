import { mkdir, symlink, realpath, readdir } from "node:fs/promises";
import { dirname, join } from "node:path";
import { pathToFileURL, fileURLToPath } from "node:url";
import { sourceInputs, typescriptParserInputs } from "./source.ts";
import { preparePatchedSource } from "./patched-source.ts";
import type { GenerationTarget } from "./types.ts";
import { jsonSafeInteger } from "./zod-safe-integers.ts";

export async function prepareTypescript(): Promise<string> {
  const { pins, archive, patches, destination } =
    await sourceInputs("typescript");
  const source = join(destination, "source");
  await preparePatchedSource({
    archivePath: archive,
    archiveSha256: pins.archiveSha256,
    archiveRoot: pins.archiveRoot ?? "package",
    patches,
    destination: source,
  });
  const installed = await realpath(
    fileURLToPath(import.meta.resolve("@hey-api/openapi-ts")),
  );
  const dependencies = installed.slice(
    0,
    installed.lastIndexOf("/node_modules/") + "/node_modules".length,
  );
  const parser = await typescriptParserInputs();
  const parserSource = join(parser.destination, "source");
  await preparePatchedSource({
    archivePath: parser.archive,
    archiveSha256: parser.pins.archiveSha256,
    archiveRoot: parser.pins.archiveRoot ?? "package",
    patches: parser.patches,
    destination: parserSource,
  });
  const installedParser = await realpath(join(dependencies, "@hey-api/shared"));
  const parserDependencies = installedParser.slice(
    0,
    installedParser.lastIndexOf("/node_modules/") + "/node_modules".length,
  );
  await symlink(parserDependencies, join(parserSource, "node_modules"), "dir");
  // Private links select the patched parser and legacy compiler API without changing installed dependencies.
  const local = join(source, "node_modules");
  await mkdir(local, { recursive: true });
  const compilerApi = dirname(
    fileURLToPath(import.meta.resolve("typescript-compiler-api/package.json")),
  );
  for (const entry of await readdir(dependencies)) {
    if (entry === "@hey-api") {
      await mkdir(join(local, entry), { recursive: true });
      for (const name of await readdir(join(dependencies, entry)))
        await symlink(
          name === "shared" ? parserSource : join(dependencies, entry, name),
          join(local, entry, name),
          "dir",
        );
    } else
      await symlink(
        entry === "typescript" ? compilerApi : join(dependencies, entry),
        join(local, entry),
        "dir",
      );
  }
  return source;
}

export async function emitTypescript(
  target: GenerationTarget,
  tool: string,
  destination: string,
): Promise<void> {
  await mkdir(destination, { recursive: true });
  const { createClient }: typeof import("@hey-api/openapi-ts") = await import(
    pathToFileURL(join(tool, "dist/index.mjs")).href
  );
  await createClient({
    input: target.schema,
    output: { path: destination, importFileExtension: ".js" },
    plugins: [
      "@hey-api/typescript",
      "@hey-api/client-fetch",
      { name: "zod", $resolvers: { number: jsonSafeInteger } },
      { name: "@hey-api/sdk", validator: { request: false, response: true } },
    ],
    logs: { file: false },
  });
}
