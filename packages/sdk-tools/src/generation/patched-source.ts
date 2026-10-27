import assert from "node:assert/strict";
import { shutdown } from "../system/shutdown.ts";
import { command, withResources } from "../system/process.ts";
import { createHash } from "node:crypto";
import { mkdir, mkdtemp, readFile, rename, rm } from "node:fs/promises";
import { dirname, join } from "node:path";

const execute = (
  program: string,
  args: string[],
  options: { cwd?: string } = {},
) => command(program, args, { ...options, signal: shutdown.signal });
export const sha256 = (bytes: string | Buffer) =>
  createHash("sha256").update(bytes).digest("hex");

export async function preparePatchedSource({
  archivePath,
  archiveSha256,
  archiveRoot,
  patches,
  destination,
}: {
  archivePath: string;
  archiveSha256: string;
  archiveRoot: string;
  patches: { path: string; sha256: string }[];
  destination: string;
}): Promise<void> {
  assert.equal(
    sha256(await readFile(archivePath)),
    archiveSha256,
    "Generator archive checksum mismatch",
  );
  for (const patch of patches)
    assert.equal(
      sha256(await readFile(patch.path)),
      patch.sha256,
      `Generator patch checksum mismatch: ${patch.path}`,
    );

  await mkdir(dirname(destination), { recursive: true });
  const work = await mkdtemp(join(dirname(destination), ".prepare-generator-"));
  await withResources(
    async () => {
      await execute("tar", ["-xzf", archivePath, "-C", work]);
      const source = join(work, archiveRoot);
      // Keep git apply independent of any enclosing repository or ignored cache.
      await execute("git", ["init", "--quiet", source]);
      for (const patch of patches) {
        await execute(
          "git",
          ["apply", "--check", "--whitespace=error-all", patch.path],
          { cwd: source },
        );
        await execute("git", ["apply", "--whitespace=error-all", patch.path], {
          cwd: source,
        });
      }
      await rm(join(source, ".git"), { recursive: true });
      await rm(destination, { recursive: true, force: true });
      await rename(source, destination);
    },
    () => rm(work, { recursive: true, force: true }),
  );
}
