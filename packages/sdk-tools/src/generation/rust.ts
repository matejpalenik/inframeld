import assert from "node:assert/strict";
import { readFile, writeFile, mkdir, cp, rm, mkdtemp } from "node:fs/promises";
import { join, dirname } from "node:path";
import { tmpdir } from "node:os";
import { home, cache } from "../config.ts";
import { run } from "../system/run.ts";
import { sourceInputs } from "./source.ts";
import { preparePatchedSource } from "./patched-source.ts";
import type { GenerationTarget } from "./types.ts";

export async function prepareRust(test = false): Promise<string> {
  const { pins, archive, patches, destination } = await sourceInputs("rust");
  // Keep Rust source builds outside the application Cargo workspace.
  const temporary = await mkdtemp(join(tmpdir(), "inframeld-sdk-generator-"));
  const source = join(temporary, "source");
  try {
    await preparePatchedSource({
      archivePath: archive,
      archiveSha256: pins.archiveSha256,
      archiveRoot:
        pins.archiveRoot ?? `openapi-to-rust-${pins.upstreamVersion}`,
      patches,
      destination: source,
    });
    const binary = join(destination, "bin/openapi-to-rust");
    try {
      await readFile(binary);
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
      await run(
        "cargo",
        [
          "install",
          "--locked",
          "--path",
          source,
          "--bin",
          "openapi-to-rust",
          "--root",
          destination,
        ],
        "rust-generator-install",
        { env: { CARGO_TARGET_DIR: join(cache, "patched-target") } },
      );
    }
    assert.equal(
      (
        await run(binary, ["--version"], "rust-generator-version")
      ).stdout.trim(),
      `openapi-to-rust ${pins.upstreamVersion}`,
    );
    if (test)
      await run(
        "cargo",
        [
          "test",
          "--locked",
          "--lib",
          "--manifest-path",
          join(source, "Cargo.toml"),
        ],
        "rust-generator-library",
        { env: { CARGO_TARGET_DIR: join(cache, "patched-target") } },
      );
    return binary;
  } finally {
    await rm(temporary, { recursive: true, force: true });
  }
}

export async function emitRust(
  target: GenerationTarget,
  tool: string,
  destination: string,
): Promise<void> {
  await mkdir(destination, { recursive: true });
  const work = dirname(destination);
  const input =
    target.kind === "production"
      ? "contracts/openapi/v1/inframeld-v1.json"
      : target.kind === "capabilities"
        ? "fixtures/patch-capabilities.json"
        : "fixtures/openapi.json";
  await mkdir(dirname(join(work, input)), { recursive: true });
  await cp(target.schema, join(work, input));
  let config = await readFile(join(home, "generators/rust.toml"), "utf8");
  config = config
    .replace(
      'spec_path = "contracts/openapi/v1/inframeld-v1.json"',
      `spec_path = ${JSON.stringify(input)}`,
    )
    .replace(
      'output_dir = "generated"',
      `output_dir = ${JSON.stringify(destination)}`,
    );
  if (target.metadata === false)
    config = config.replace(
      "response_metadata = true",
      "response_metadata = false",
    );
  if (target.kind === "capabilities")
    config =
      config.replace(
        "enable_async_client = true",
        "enable_async_client = true\nenable_sse_client = true",
      ) + "\n[generator.builders]\nenabled = true\nthreshold = 0\n";
  await writeFile(join(work, "rust.toml"), config);
  await run(
    tool,
    ["generate", "--config", join(work, "rust.toml"), "--json"],
    `generate-rust-${target.kind}`,
    { cwd: work },
  );
}
