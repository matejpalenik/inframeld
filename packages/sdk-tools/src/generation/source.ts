import assert from "node:assert/strict";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { join } from "node:path";
import { z } from "zod";
import { home, cache, languages, type Language } from "../config.ts";
import { sha256 } from "./patched-source.ts";
import type { PreparedSource, GeneratorPin } from "./types.ts";
import { shutdown } from "../system/shutdown.ts";

const sourcePin = z.object({
  upstreamVersion: z.string(),
  archiveUrl: z.url(),
  archiveFile: z.string().optional(),
  archiveRoot: z.string().optional(),
  archiveSha256: z.string(),
  revision: z.string().optional(),
  patches: z.array(z.object({ file: z.string(), sha256: z.string() })),
});
const pin = sourcePin.extend({ sharedParser: sourcePin.optional() });
export const manifest = z
  .record(z.enum(languages), pin)
  .parse(
    JSON.parse(await readFile(join(home, "generators/manifest.json"), "utf8")),
  );

/** Cached archives are verified again before any generator source is used. */
export async function sourceInputs(
  language: Language,
): Promise<PreparedSource> {
  return verifiedInputs(manifest[language], language);
}

export async function typescriptParserInputs(): Promise<PreparedSource> {
  const pins = manifest.typescript.sharedParser;
  assert.ok(pins, "The selected TypeScript parser source must be pinned");
  return verifiedInputs(pins, "typescript-parser");
}

async function verifiedInputs(
  pins: GeneratorPin,
  namespace: string,
): Promise<PreparedSource> {
  await mkdir(cache, { recursive: true });
  const archive = join(
    cache,
    pins.archiveFile ?? `openapi-to-rust-${pins.upstreamVersion}.crate`,
  );
  try {
    await readFile(archive);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
    const response = await fetch(pins.archiveUrl, {
      signal: AbortSignal.any([shutdown.signal, AbortSignal.timeout(60_000)]),
    });
    if (!response.ok)
      throw new Error(`Source download failed: ${response.status}`);
    const bytes = Buffer.from(await response.arrayBuffer());
    assert.equal(
      sha256(bytes),
      pins.archiveSha256,
      "Generator archive checksum mismatch",
    );
    await writeFile(archive, bytes);
  }
  assert.equal(
    sha256(await readFile(archive)),
    pins.archiveSha256,
    "Generator archive checksum mismatch",
  );
  const patches = pins.patches.map((patch) => ({
    ...patch,
    path: join(home, "generators", patch.file),
  }));
  for (const patch of patches)
    assert.equal(
      sha256(await readFile(patch.path)),
      patch.sha256,
      `Generator patch checksum mismatch: ${patch.file}`,
    );
  return {
    pins,
    archive,
    patches,
    destination: join(
      cache,
      "selected",
      namespace,
      sha256(JSON.stringify(pins)),
    ),
  };
}
