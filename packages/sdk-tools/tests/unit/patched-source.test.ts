import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { promisify } from "node:util";
import { snapshot } from "../../src/system/files.ts";
import { preparePatchedSource } from "../../src/generation/patched-source.ts";

const execute = promisify(execFile);
const sha256 = (bytes: Buffer) =>
  createHash("sha256").update(bytes).digest("hex");

type SourceOptions = Parameters<typeof preparePatchedSource>[0];
async function fixture(
  run: (options: SourceOptions, work: string) => Promise<void>,
) {
  const work = await mkdtemp(join(tmpdir(), "sdk-patched-source-test-"));
  try {
    const source = join(work, "upstream");
    await mkdir(source);
    await writeFile(join(source, "client.rs"), "before\n");
    const archivePath = join(work, "source.crate");
    await execute("tar", ["-czf", archivePath, "-C", work, "upstream"]);
    const path = join(work, "response.patch");
    await writeFile(
      path,
      "diff --git a/client.rs b/client.rs\n--- a/client.rs\n+++ b/client.rs\n@@ -1 +1 @@\n-before\n+after\n",
    );
    const options = {
      archivePath,
      archiveSha256: sha256(await readFile(archivePath)),
      archiveRoot: "upstream",
      patches: [{ path, sha256: sha256(await readFile(path)) }],
      destination: join(work, "prepared"),
    };
    await run(options, work);
  } finally {
    await rm(work, { recursive: true, force: true });
  }
}

test("preparing the same pinned source and patch produces identical trees", async () => {
  await fixture(async (options, work) => {
    await preparePatchedSource(options);
    assert.equal(
      await readFile(join(options.destination, "client.rs"), "utf8"),
      "after\n",
    );
    const second = join(work, "second");
    await preparePatchedSource({ ...options, destination: second });
    assert.deepEqual(
      await snapshot(options.destination),
      await snapshot(second),
    );
  });
});

test("changed archive bytes are rejected before replacing prepared source", async () => {
  await fixture(async (options) => {
    await mkdir(options.destination);
    await writeFile(join(options.destination, "keep"), "existing");
    await writeFile(options.archivePath, "tampered");
    await assert.rejects(
      preparePatchedSource(options),
      /archive checksum mismatch/i,
    );
    assert.equal(
      await readFile(join(options.destination, "keep"), "utf8"),
      "existing",
    );
  });
});

test("source preparation also applies patches inside the repository tool cache", async () => {
  await fixture(async (options, work) => {
    await execute("git", ["init", "--quiet", work]);
    await preparePatchedSource(options);
    assert.equal(
      await readFile(join(options.destination, "client.rs"), "utf8"),
      "after\n",
    );
  });
});

test("changed patch bytes are rejected before applying them", async () => {
  await fixture(async (options) => {
    await writeFile(options.patches[0]!.path, "tampered");
    await assert.rejects(
      preparePatchedSource(options),
      /patch checksum mismatch/i,
    );
  });
});

test("a patch that no longer applies fails without replacing prepared source", async () => {
  await fixture(async (options) => {
    const patch = options.patches[0]!;
    await writeFile(
      patch.path,
      (await readFile(patch.path, "utf8")).replace("-before", "-different"),
    );
    patch.sha256 = sha256(await readFile(patch.path));
    await mkdir(options.destination);
    await writeFile(join(options.destination, "keep"), "existing");
    await assert.rejects(
      preparePatchedSource(options),
      /patch does not apply/i,
    );
    assert.equal(
      await readFile(join(options.destination, "keep"), "utf8"),
      "existing",
    );
  });
});
