import { writeFile, mkdir, rm, readFile, cp } from "node:fs/promises";
import { join } from "node:path";
import { home, cache } from "../config.ts";
import { z } from "zod";
import { parse, stringify } from "smol-toml";
import type { ConsumerEvidence } from "./evidence.ts";
import { run } from "../system/run.ts";

export async function archiveRust(work: string): Promise<string> {
  const external = join(work, "external-rust");
  await mkdir(external, { recursive: true });
  const metadata = z
    .object({
      packages: z.array(z.object({ name: z.string(), version: z.string() })),
      target_directory: z.string(),
    })
    .parse(
      JSON.parse(
        (
          await run(
            "cargo",
            ["metadata", "--no-deps", "--format-version", "1"],
            "rust-package-metadata",
          )
        ).stdout,
      ),
    );
  const pkg = metadata.packages.find((pkg) => pkg.name === "inframeld-sdk");
  if (!pkg) throw new Error("Rust SDK metadata missing");
  const identity = `${pkg.name}-${pkg.version}`;
  const archive = join(
    metadata.target_directory,
    "package",
    identity + ".crate",
  );
  await rm(archive, { force: true });
  await run(
    "cargo",
    [
      "package",
      "--locked",
      "--allow-dirty",
      "--no-verify",
      "-p",
      "inframeld-sdk",
    ],
    "rust-package",
  );
  return archive;
}

export async function consumeRust(
  work: string,
  archive: string,
  baseUrl: string,
): Promise<ConsumerEvidence> {
  const external = join(work, "external-rust");
  await mkdir(external, { recursive: true });
  await run("tar", ["-xzf", archive, "-C", external], "rust-extract");
  const listing = await run("tar", ["-tzf", archive], "rust-archive-list");
  const identity = z.string().min(1).parse(listing.stdout.split("/")[0]);
  const fixture = join(home, "consumers/rust");
  await cp(join(fixture, "src"), join(external, "src"), { recursive: true });
  const manifest = parse(await readFile(join(fixture, "Cargo.toml"), "utf8"));
  const dependencies = z
    .record(z.string(), z.unknown())
    .parse(manifest.dependencies);
  manifest.dependencies = {
    ...dependencies,
    "inframeld-sdk": { path: identity },
  };
  await writeFile(join(external, "Cargo.toml"), stringify(manifest));
  await run(
    "cargo",
    [
      "run",
      "--manifest-path",
      join(external, "Cargo.toml"),
      "--target-dir",
      join(cache, "consumer-target"),
      "--",
      baseUrl,
    ],
    "rust-external-consumer",
  );
  const version = await run(
    "rustc",
    ["--version"],
    "rust-consumer-compiler-version",
  );
  return {
    runtimes: [{ role: "primary", versions: { rustc: version.stdout.trim() } }],
  };
}
