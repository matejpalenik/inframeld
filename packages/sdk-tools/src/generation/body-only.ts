import { readFile, writeFile, mkdir, mkdtemp, rm } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { parse, stringify } from "smol-toml";
import { packageRoot, cache, home } from "../config.ts";
import { prepare, emit, targets } from "./generators.ts";
import { run } from "../system/run.ts";
export async function bodyOnlyRegression(): Promise<void> {
  const tool = await prepare("rust");
  const work = await mkdtemp(join(tmpdir(), "inframeld-sdk-body-only-"));
  try {
    await emit(
      "rust",
      { ...targets("rust")[0]!, metadata: false },
      tool,
      join(work, "generated"),
    );
    const production = await readFile(
      join(packageRoot("rust"), "Cargo.toml"),
      "utf8",
    );
    await writeFile(
      join(work, "Cargo.toml"),
      stringify({
        package: {
          name: "inframeld-sdk-body-only-check",
          version: "0.0.0",
          edition: "2024",
        },
        workspace: {},
        lib: { path: "generated/mod.rs" },
        dependencies: parse(production).dependencies,
      }),
    );
    await mkdir(join(work, "examples"));
    await writeFile(
      join(work, "examples/contract.rs"),
      await readFile(join(home, "tests/native/body-only.rs"), "utf8"),
    );
    await run(
      "cargo",
      [
        "check",
        "--examples",
        "--manifest-path",
        join(work, "Cargo.toml"),
        "--target-dir",
        join(cache, "body-only-target"),
      ],
      "rust-body-only",
    );
  } finally {
    await rm(work, { recursive: true, force: true });
  }
}
