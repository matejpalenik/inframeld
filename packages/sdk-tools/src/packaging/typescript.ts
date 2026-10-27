import { writeFile, mkdir, rm, cp } from "node:fs/promises";
import { join } from "node:path";
import { home, cache, packageRoot } from "../config.ts";
import { z } from "zod";
import type { ConsumerEvidence } from "./evidence.ts";
import { run } from "../system/run.ts";
import { buildTypescript } from "../system/typescript.ts";
import { withResources } from "../system/process.ts";

export async function archiveTypescript(work: string): Promise<string> {
  const external = join(work, "external-typescript");
  await mkdir(external, { recursive: true });
  const stale = join(
    packageRoot("typescript"),
    "dist",
    "__sdk_stale_probe__.js",
  );
  const archive = await withResources(
    async () => {
      // A removed source file must not survive through tsc's previous outDir.
      await mkdir(join(packageRoot("typescript"), "dist"), { recursive: true });
      await writeFile(
        stale,
        "throw new Error('Stale build artifact must not ship');\n",
      );
      await buildTypescript("typescript-package-build");
      const pack = await run(
        "npm",
        ["pack", "--ignore-scripts", "--json", "--pack-destination", external],
        "typescript-pack",
        { cwd: packageRoot("typescript") },
      );
      const [archive] = z
        .array(
          z.object({
            filename: z.string(),
            files: z.array(z.object({ path: z.string() })),
          }),
        )
        .length(1)
        .parse(JSON.parse(pack.stdout));
      if (!archive) throw new Error("Missing npm archive");
      if (archive.files.some((f) => /sdk-tools|fixtures/.test(f.path)))
        throw new Error("Test tooling leaked into SDK archive");
      if (
        archive.files.some((file) => file.path.includes("__sdk_stale_probe__"))
      )
        throw new Error("Stale build output leaked into npm archive");
      return archive;
    },
    () => rm(stale, { force: true }),
  );
  return join(external, archive.filename);
}

export async function consumeTypescript(
  work: string,
  archive: string,
  baseUrl: string,
): Promise<ConsumerEvidence> {
  const external = join(work, "typescript-consumer");
  await mkdir(external, { recursive: true });
  await writeFile(
    join(external, "package.json"),
    JSON.stringify({
      name: "sdk-external-consumer",
      private: true,
      type: "module",
    }),
  );
  await run(
    "npm",
    [
      "install",
      "--ignore-scripts",
      "--no-audit",
      "--no-fund",
      "--cache",
      join(cache, "npm"),
      archive,
    ],
    "typescript-consumer-install",
    { cwd: external },
  );
  await cp(
    join(home, "consumers/typescript/main.ts"),
    join(external, "main.ts"),
  );
  await run(
    join(home, "node_modules/.bin/tsc"),
    [
      "--strict",
      "--skipLibCheck",
      "--module",
      "NodeNext",
      "--moduleResolution",
      "NodeNext",
      "--target",
      "ES2022",
      "--typeRoots",
      join(home, "node_modules/@types"),
      join(external, "main.ts"),
    ],
    "typescript-external-types",
    { cwd: external },
  );
  const result = await run(
    process.execPath,
    [join(external, "main.js"), baseUrl],
    "typescript-external-runtime",
    { cwd: external },
  );
  const observed = z
    .object({ node: z.string().min(1) })
    .parse(JSON.parse(result.stdout));
  return { runtimes: [{ role: "primary", versions: observed }] };
}
