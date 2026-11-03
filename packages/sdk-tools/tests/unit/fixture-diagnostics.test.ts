import assert from "node:assert/strict";
import {
  mkdtemp,
  mkdir,
  rm,
  writeFile,
  lstat,
  realpath,
} from "node:fs/promises";
import { tmpdir } from "node:os";
import { basename, join, sep } from "node:path";
import test from "node:test";
import { artifacts } from "../../src/config.ts";
import { withResources } from "../../src/system/process.ts";
import {
  publishFixtureDiagnostics,
  type FixtureClock,
} from "../native/fixtures/browser-owner.ts";
import {
  fixtureDiagnostic,
  fixtureCaptureMetadata,
  FixtureDiagnostics,
  prepareFixtureCapture,
  observeFixtureController,
  acquireProtectedFixtureDirectory,
} from "../native/fixtures/fixture-diagnostics.ts";

function publicationClock() {
  let time = 100;
  const clock: FixtureClock = {
    now: () => time,
    set: () => 0,
    clear() {},
  };
  return { clock, expire: () => (time = 200) };
}

test("owner diagnostics publishes both safe destinations", async (context) => {
  const diagnostics = new FixtureDiagnostics("broker"),
    { clock } = publicationClock(),
    destinations: string[] = [];
  diagnostics.note({
    phase: "native-controller",
    category: "failed",
    status: 1,
  });
  context.mock.method(diagnostics, "write", async (folder: string) => {
    destinations.push(folder);
  });
  await publishFixtureDiagnostics(diagnostics, "/private/status", 200, clock);
  assert.deepEqual(destinations, ["/private/status", artifacts]);
});

test("owner diagnostics refuses expired writes before their effects", async (context) => {
  for (const deadline of [99, 100]) {
    const diagnostics = new FixtureDiagnostics("assertion"),
      { clock } = publicationClock();
    let writes = 0;
    context.mock.method(diagnostics, "write", async () => {
      writes++;
    });
    await assert.rejects(
      publishFixtureDiagnostics(
        diagnostics,
        "/private/status",
        deadline,
        clock,
      ),
      (error) => {
        assert.ok(error instanceof AggregateError);
        assert.equal(error.errors.length, 2);
        for (const failure of error.errors)
          assert.match(String(failure), /report-deadline/);
        return true;
      },
    );
    assert.equal(writes, 0);
  }
});

test("owner diagnostics still publishes ordinary status after private failure", async (context) => {
  const diagnostics = new FixtureDiagnostics("assertion"),
    { clock } = publicationClock(),
    destinations: string[] = [],
    failure = new Error("controlled private publication failure");
  context.mock.method(diagnostics, "write", async (folder: string) => {
    destinations.push(folder);
    if (folder === "/private/status") throw failure;
  });
  await assert.rejects(
    publishFixtureDiagnostics(diagnostics, "/private/status", 200, clock),
    (error) => error === failure,
  );
  assert.deepEqual(destinations, ["/private/status", artifacts]);
});

test("owner diagnostics retains both destination failures", async (context) => {
  const diagnostics = new FixtureDiagnostics("worker"),
    { clock } = publicationClock(),
    privateFailure = new Error("controlled private publication failure"),
    ordinaryFailure = new Error("controlled ordinary publication failure");
  context.mock.method(diagnostics, "write", async (folder: string) => {
    throw folder === "/private/status" ? privateFailure : ordinaryFailure;
  });
  await assert.rejects(
    publishFixtureDiagnostics(diagnostics, "/private/status", 200, clock),
    (error) => {
      assert.ok(error instanceof AggregateError);
      assert.deepEqual(error.errors, [privateFailure, ordinaryFailure]);
      return true;
    },
  );
});

test("owner diagnostics never starts its second write after allowance exhaustion", async (context) => {
  const diagnostics = new FixtureDiagnostics("worker"),
    { clock, expire } = publicationClock(),
    destinations: string[] = [];
  context.mock.method(diagnostics, "write", async (folder: string) => {
    destinations.push(folder);
    expire();
  });
  await assert.rejects(
    publishFixtureDiagnostics(diagnostics, "/private/status", 200, clock),
    (error) => {
      assert.ok(error instanceof AggregateError);
      for (const failure of error.errors)
        assert.match(String(failure), /report-deadline/);
      return true;
    },
  );
  assert.deepEqual(destinations, ["/private/status"]);
});

test("owner diagnostics preserves an initiating error alongside publication failure", async (context) => {
  const diagnostics = new FixtureDiagnostics("worker"),
    { clock } = publicationClock(),
    primary = new Error("controlled initiating failure"),
    publication = new Error("controlled publication failure");
  context.mock.method(diagnostics, "write", async (folder: string) => {
    if (folder === "/private/status") throw publication;
  });
  await assert.rejects(
    withResources(
      async () => {
        throw primary;
      },
      () =>
        publishFixtureDiagnostics(diagnostics, "/private/status", 200, clock),
    ),
    (error) => {
      assert.ok(error instanceof AggregateError);
      assert.deepEqual(error.errors, [primary, publication]);
      return true;
    },
  );
});

test("fixed native failure details never forward original messages or nested secrets", () => {
  const original = new Error("secret ws://capability/private");
  const error = new AggregateError([original], "argv nonce");
  Object.defineProperty(original, "cause", { value: error });
  const output = fixtureDiagnostic({
    phase: "fixture-terminal",
    category: "failed",
    status: null,
    failure: error,
  });
  assert.ok(
    !output.includes("secret") &&
      !output.includes("capability") &&
      !output.includes("nonce"),
  );
  assert.ok(output.includes("cycle"));
  assert.ok(Buffer.byteLength(output) < 8192);
});

test(
  "pure fixture diagnostics publishes only fixed records on success and failure",
  { timeout: 5000 },
  () => {
    for (const category of ["passed", "failed", "capture-unproved"]) {
      const output = fixtureDiagnostic({
        phase: "native-controller",
        category,
        status: null,
      });
      assert.ok(
        output.startsWith("{"),
        "A fixed status record must be published",
      );
      assert.deepEqual(JSON.parse(output), {
        phase: "native-controller",
        category,
        status: null,
      });
    }
  },
);

test(
  "pure fixture diagnostics rejects raw clipped errors and free-form success fields",
  { timeout: 5000 },
  () => {
    for (const unsafe of [
      new Error("nonce-fragment"),
      new AggregateError([new Error("ws-fragment")], "clipped", {
        cause: new Error("private-cause"),
      }),
      {
        phase: "native-controller",
        category: "passed",
        status: null,
        output: "nonce-fragment",
      },
      { phase: "native-controller", category: "failed", cause: "ws-fragment" },
      { phase: "private-phase", category: "failed" },
      { phase: "peer-lost", category: "failed", peer: "nonce-fragment" },
    ])
      assert.throws(
        () => fixtureDiagnostic(unsafe),
        /Invalid fixture diagnostic/,
      );
  },
);

test(
  "pure fixture diagnostics bounds encoded metadata without decoding protected text",
  { timeout: 5000 },
  () => {
    const initial = { bytes: 0, device: 1, inode: 2 };
    assert.deepEqual(
      fixtureCaptureMetadata(initial, { ...initial, bytes: 3 }),
      { ...initial, bytes: 3 },
    );
    assert.equal(Buffer.byteLength("\uFFFD\uFFFD"), 6);
    for (const current of [
      { ...initial, bytes: 64 * 1024 * 1024 + 1 },
      { ...initial, bytes: -1 },
      { ...initial, inode: 3 },
      { ...initial, device: 2 },
    ])
      assert.throws(
        () => fixtureCaptureMetadata(initial, current),
        /Invalid protected capture/,
      );
  },
);

test(
  "pure fixture diagnostics retains a private capture and checks its identity",
  { timeout: 5000 },
  async () => {
    const work = await mkdtemp(join(tmpdir(), "sdk-diagnostic-capture-"));
    let folder: string | undefined;
    try {
      const publication = join(work, "artifacts");
      await mkdir(publication);
      const report = join(publication, "sdk-diagnostic-capture.json");
      folder = await acquireProtectedFixtureDirectory(report);
      const canonicalArtifacts = await realpath(publication);
      const canonicalFolder = await realpath(folder);
      assert.equal((await lstat(folder)).mode & 0o777, 0o700);
      assert.ok(basename(folder).startsWith(basename(report) + ".protected-"));
      assert.notEqual(canonicalFolder, canonicalArtifacts);
      assert.ok(!canonicalFolder.startsWith(canonicalArtifacts + sep));
      const capture = await prepareFixtureCapture(folder, "timeout");
      assert.equal((await lstat(capture.path)).mode & 0o777, 0o600);
      await writeFile(capture.path, "nonce-fragment\uFFFD");
      const metadata = await capture.check();
      assert.equal(metadata.bytes, Buffer.byteLength("nonce-fragment\uFFFD"));
      assert.ok(metadata.device >= 0 && metadata.inode > 0);
    } finally {
      if (folder) await rm(folder, { recursive: true, force: true });
      await rm(work, { recursive: true, force: true });
    }
  },
);

test(
  "pure fixture diagnostics preserves cancellation identity and independent recording failure",
  { timeout: 5000 },
  async () => {
    const diagnostics = new FixtureDiagnostics("broker"),
      cancellation = new Error("controlled cancellation");
    await assert.rejects(
      observeFixtureController(diagnostics, "probe-controller", async () => {
        throw cancellation;
      }),
      (error) => error === cancellation,
    );
    assert.notEqual(
      diagnostics.snapshot(),
      "",
      "The controlled failure category must be retained",
    );
    assert.equal(JSON.parse(diagnostics.snapshot())[0].category, "failed");
    const full = new FixtureDiagnostics("broker");
    for (let n = 0; n < 32; n++)
      full.note({ phase: "startup", category: "started", status: null });
    await assert.rejects(
      observeFixtureController(full, "probe-controller", async () => {
        throw cancellation;
      }),
      (error) => {
        assert.ok(error instanceof AggregateError);
        assert.equal(error.errors[0], cancellation);
        assert.equal(error.errors.length, 2);
        return true;
      },
    );
  },
);

test(
  "pure fixture diagnostics retains unknown status and bounded phase records",
  { timeout: 5000 },
  () => {
    const diagnostics = new FixtureDiagnostics("worker");
    for (let n = 0; n < 32; n++)
      diagnostics.note({
        phase: "shutdown-observed",
        category: "capture-unproved",
        status: null,
      });
    assert.notEqual(
      diagnostics.snapshot(),
      "",
      "The phase records must be retained",
    );
    assert.equal(JSON.parse(diagnostics.snapshot()).length, 32);
    assert.ok(Buffer.byteLength(diagnostics.snapshot()) <= 4096);
    assert.throws(
      () =>
        diagnostics.note({ phase: "ready", category: "started", status: null }),
      /Fixture diagnostic limit/,
    );
  },
);
