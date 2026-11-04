import assert from "node:assert/strict"
import { spawn } from "node:child_process"
import type { ChildProcess } from "node:child_process"
import {
  mkdtemp,
  mkdir,
  readFile,
  readdir,
  rm,
  writeFile,
  access,
} from "node:fs/promises"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { fileURLToPath } from "node:url"
import { setTimeout } from "node:timers/promises"
import { test } from "node:test"
import { createServer } from "node:net"
import { chmod } from "node:fs/promises"
import { readRecipientBridge } from "../browser/support"
const wrapper = fileURLToPath(
  new URL("../../../../scripts/test-account-ui.sh", import.meta.url)
)
const fixture = fileURLToPath(
  new URL("../fixtures/account-runtime-probe.mjs", import.meta.url)
)
const runner = fileURLToPath(
  new URL("../../../../scripts/run_account_ui.py", import.meta.url)
)
const ownershipTests = fileURLToPath(
  new URL("../../../../scripts/test_account_ui.py", import.meta.url)
)

test(
  "the private recipient peer reads exactly one bounded event and closes after malformed input",
  { timeout: 8_000 },
  async () => {
    for (const valid of [true, false]) {
      const directory = await mkdtemp(join(tmpdir(), "recipient-peer-test-"))
      const path = join(directory, "event.sock")
      const sockets = new Set<import("node:net").Socket>()
      const server = createServer((socket) => {
        sockets.add(socket)
        socket.once("close", () => sockets.delete(socket))
        socket.end(
          valid
            ? JSON.stringify({
                schemaVersion: 1,
                type: "authorization-ready",
                authorizationUrl: "https://hydra.account.test:8443/oauth2/auth",
                issuer: "https://hydra.account.test:8443/",
                callbackUri: "http://127.0.0.1:12345/oauth/callback/example",
              }) + "\n"
            : "{}\n{}\n"
        )
      })
      await new Promise<void>((done, reject) => {
        server.once("error", reject)
        server.listen(path, done)
      })
      await chmod(path, 0o600)
      try {
        if (valid)
          assert.equal(
            (await readRecipientBridge(path, performance.now() + 1_000)).type,
            "authorization-ready"
          )
        else
          await assert.rejects(
            readRecipientBridge(path, performance.now() + 1_000)
          )
      } finally {
        for (const socket of sockets) socket.destroy()
        await new Promise<void>((done, reject) => {
          const timer = globalThis.setTimeout(
            () => reject(new Error("Private peer cleanup exceeded its bound.")),
            1_000
          )
          server.close((error) => {
            globalThis.clearTimeout(timer)
            if (error) reject(error)
            else done()
          })
        })
        await rm(directory, { recursive: true })
      }
    }
  }
)
const program = String.raw`
import os, runpy, sys
from pathlib import Path
Runner = runpy.run_path(sys.argv[1])["AccountUIRunner"]
class Probe(Runner):
    def _work(self):
        self.project = "inframeld-account-ui-probe"
        self.volume_baseline_complete = True
        (self.directory / "volumes-before.txt").write_text("original-a\noriginal-b\n")
        startup = os.environ["ACCOUNT_PROBE_STARTUP"] == "true"
        proof = os.environ.get("ACCOUNT_PROBE_PROOF", "")
        command = self._shell("recipient_proof_stack") if proof else self._shell("startup_stack") if startup else ["docker", "probe-phase"]
        status = self._run_phase("startup" if startup else "probe", command,
                                 float(os.environ["ACCOUNT_PROBE_BUDGET"]))
        self.qualification_complete = status == 0
        return status
root = Path(sys.argv[1]).resolve().parents[1]
basename = os.environ.get("ACCOUNT_PROBE_BASENAME", "retained")
Owner = Runner if os.environ.get("ACCOUNT_PROBE_MAIN") == "true" else Probe
raise SystemExit(Owner(root, directory=Path(sys.argv[2]) / basename,
                      cleanup_work_seconds=2).run(["--recipient-proof"] if
                      os.environ.get("ACCOUNT_PROBE_MAIN") == "true" and
                      os.environ.get("ACCOUNT_PROBE_PROOF") else ["--login-only"]))
`

type Options = {
  phase?: "hang" | "exit-with-descendant" | "exit-with-closed-descendant"
  cleanup?: "hang"
  inventory?: "hang" | "remaining"
  status?: number
  cleanupStatus?: number
  budget?: number
  main?: boolean
  basename?: string
  startup?: boolean
  startupFail?: string
  startupHang?: string
  volumeInventory?: "leak" | "missing" | "partial" | "fail" | "hang"
  baseline?: "partial" | "fail" | "sort-fail"
  proof?:
    | "success"
    | "browser-exits-first"
    | "backend-wrong-id"
    | "backend-stopped"
    | "backend-without-init"
    | "backend-host-pid"
    | "browser-wrong-owner"
    | "driver-browser-owner"
    | "unhealthy"
    | "browser-failed"
    | "driver-failed"
    | "driver-logs-failed"
    | "inspect-invalid"
    | "never-ready"
    | "stalled-terminal"
    | "wrong-id"
    | "verify-failed"
    | "denied-wrong-id"
    | "denied-host-net"
    | "denied-wrong-exit"
    | "denied-effects"
    | "denied-stalled"
    | "second-readiness-failed"
    | "lookup-zero"
    | "lookup-multiple"
    | "lookup-truncated"
    | "lookup-query-failed"
    | "lookup-wrong-project"
    | "lookup-wrong-service"
    | "lookup-reused-browser"
    | "lookup-reused-backend"
}
async function exists(path: string) {
  try {
    await access(path)
    return true
  } catch {
    return false
  }
}
async function ready(directory: string, name: string, child: ChildProcess) {
  const deadline = Date.now() + 8_000
  while (
    !(await exists(join(directory, name))) &&
    child.exitCode === null &&
    Date.now() < deadline
  )
    await setTimeout(10)
  assert.equal(
    await exists(join(directory, name)),
    true,
    "Controlled process did not become ready"
  )
}
function alive(pid: number) {
  try {
    process.kill(pid, 0)
    return true
  } catch {
    return false
  }
}
async function assertStopped(pid: number) {
  const deadline = Date.now() + 3_000
  while (alive(pid) && Date.now() < deadline) await setTimeout(10)
  assert.equal(
    alive(pid),
    false,
    "A controlled process survived the bounded shutdown and reaping grace"
  )
}

async function processes(
  directory: string
): Promise<{ pid: number; group: number }[]> {
  try {
    return (await readFile(join(directory, "processes.jsonl"), "utf8"))
      .trim()
      .split("\n")
      .filter(Boolean)
      .map((line) => JSON.parse(line) as { pid: number; group: number })
  } catch {
    return []
  }
}
async function completion(
  child: ChildProcess,
  milliseconds = 13_000
): Promise<number | null> {
  if (child.exitCode !== null || child.signalCode !== null)
    return child.exitCode
  return new Promise((resolveResult, reject) => {
    const timer = globalThis.setTimeout(() => {
      child.off("close", closed)
      reject(new Error("The wrapper did not finish within its shutdown bound."))
    }, milliseconds)
    const closed = (code: number | null) => {
      globalThis.clearTimeout(timer)
      resolveResult(code)
    }
    child.once("close", closed)
  })
}
async function probe(
  options: Options,
  check: (state: {
    child: ChildProcess
    directory: string
    output: () => string
  }) => Promise<void>
) {
  const directory = await mkdtemp(join(tmpdir(), "account-wrapper-test-"))
  const bin = join(directory, "bin")
  await mkdir(bin)
  await writeFile(
    join(bin, "docker"),
    `#!${process.execPath}\n${
      options.basename
        ? String.raw`
if (process.argv.includes("build")) {
  const images = ["BACKEND", "WEB", "PROOF"].map(
    name => process.env["INFRAMELD_ACCOUNT_" + name + "_IMAGE"]
  )
  appendFileSync(join(process.env.ACCOUNT_PROBE_DIRECTORY, "events.jsonl"),
    JSON.stringify({ kind: "image-build", images,
      context: process.env.INFRAMELD_ACCOUNT_WEB_CONTEXT }) + "\n")
  if (images.some(image => !/^localhost\/[a-z0-9]+(?:(?:[._]|__|-+)[a-z0-9]+)*:check$/.test(image))) {
    console.error("Owned image reference rejected")
    process.exit(125)
  }
}
`
        : ""
    }${await readFile(fixture, "utf8")}`,
    { mode: 0o700 }
  )
  if (options.baseline === "sort-fail")
    await writeFile(
      join(bin, "sort"),
      "#!/bin/sh\nprintf 'partial-sort\\n'\nexit 38\n",
      {
        mode: 0o700,
      }
    )
  const child = spawn(
    options.main && !options.basename ? "bash" : "python3",
    options.main && !options.basename
      ? [wrapper, options.proof ? "--recipient-proof" : "--login-only"]
      : ["-B", "-c", program, runner, directory],
    {
      detached: true,
      stdio: ["ignore", "pipe", "pipe"],
      env: {
        ...process.env,
        PATH: `${bin}:${process.env.PATH}`,
        TMPDIR: directory,
        INFRAMELD_CONTAINER_RUNTIME: "docker",
        ACCOUNT_PROBE_DIRECTORY: directory,
        ACCOUNT_PROBE_MAIN: String(options.main ?? false),
        ACCOUNT_PROBE_BASENAME: options.basename ?? "retained",
        ACCOUNT_PROBE_STARTUP: String(options.startup ?? false),
        ACCOUNT_PROBE_PROOF: options.proof ?? "",
        ACCOUNT_PROBE_STARTUP_FAIL: options.startupFail ?? "",
        ACCOUNT_PROBE_STARTUP_HANG: options.startupHang ?? "",
        ACCOUNT_PROBE_BASELINE: options.baseline ?? "",
        ACCOUNT_PROBE_VOLUME_INVENTORY: options.volumeInventory ?? "",
        ACCOUNT_PROBE_PHASE: options.phase ?? "",
        ACCOUNT_PROBE_CLEANUP: options.cleanup ?? "",
        ACCOUNT_PROBE_INVENTORY: options.inventory ?? "",
        ACCOUNT_PROBE_STATUS: String(options.status ?? 0),
        ACCOUNT_PROBE_CLEANUP_STATUS: String(options.cleanupStatus ?? 0),
        ACCOUNT_PROBE_BUDGET: String(options.budget ?? 60),
      },
    }
  )
  let output = ""
  child.stdout?.on("data", (value: Buffer) => {
    output += value.toString()
  })
  child.stderr?.on("data", (value: Buffer) => {
    output += value.toString()
  })
  let passed = false
  try {
    await check({ child, directory, output: () => output })
    passed = true
  } finally {
    // Only the live direct controller can receive cancellation. Logged IDs are observations.
    if (child.exitCode === null && child.signalCode === null) {
      child.kill("SIGTERM")
      await completion(child)
    }
    for (const entry of await processes(directory))
      await assertStopped(entry.pid)
    assert.equal(
      await exists(join(directory, "fuse-fired")),
      false,
      "A fixture fuse cannot satisfy harness cleanup"
    )
    if (passed) await rm(directory, { recursive: true, force: true })
    else console.error(`Controlled account fixture retained: ${directory}`)
  }
}
test(
  "reading recipient proof logs preserves formatted coordination state byte for byte",
  { timeout: 10_000 },
  async (context) => {
    const directory = await mkdtemp(join(tmpdir(), "account-log-state-test-"))
    let child: ChildProcess | undefined
    context.after(async () => {
      if (child) {
        if (child.exitCode === null && child.signalCode === null)
          child.kill("SIGTERM")
        await completion(child, 5_000)
        child = undefined
      }
      for (const entry of await processes(directory))
        await assertStopped(entry.pid)
      assert.equal(await exists(join(directory, "fuse-fired")), false)
      await rm(directory, { recursive: true })
    })
    const state =
      JSON.stringify(
        {
          browser: true,
          denied: true,
          negativeVerified: true,
          driver: false,
          observations: 2,
        },
        null,
        2
      ) + "\n"
    const statePath = join(directory, "proof-state.json")
    await writeFile(statePath, state, { mode: 0o600 })
    child = spawn(process.execPath, [fixture, "logs", "e".repeat(64)], {
      stdio: ["ignore", "pipe", "pipe"],
      env: {
        ...process.env,
        ACCOUNT_PROBE_DIRECTORY: directory,
        ACCOUNT_PROBE_PROOF: "success",
      },
    })
    let output = ""
    let errors = ""
    child.stdout?.on("data", (value: Buffer) => {
      output += value.toString()
    })
    child.stderr?.on("data", (value: Buffer) => {
      errors += value.toString()
    })
    assert.equal(await completion(child, 5_000), 0)
    assert.equal(
      output,
      '{"schemaVersion":1,"error":{"kind":"denied","resourceCleanup":"not-needed","credentialCleanup":"not-needed"}}\n'
    )
    assert.equal(errors, "")
    assert.equal(await readFile(statePath, "utf8"), state)
  }
)
test(
  "controlled inspection admits only recognized synthetic image bindings without reflecting rejected values",
  { timeout: 8_000 },
  async (context) => {
    const directory = await mkdtemp(
      join(tmpdir(), "account-image-binding-test-")
    )
    let child: ChildProcess | undefined
    context.after(async () => {
      if (child) {
        if (child.exitCode === null && child.signalCode === null)
          child.kill("SIGTERM")
        await completion(child, 5_000)
      }
      for (const entry of await processes(directory))
        await assertStopped(entry.pid)
      assert.equal(await exists(join(directory, "fuse-fired")), false)
      await rm(directory, { recursive: true })
    })
    for (const [image, project] of [
      ["localhost/inframeld-account-ui-private-sentinel-web:check", undefined],
      [undefined, undefined],
      [
        "localhost/inframeld-account-ui-probe-web:check",
        "inframeld-account-ui-probe",
      ],
      [
        "localhost/inframeld-account-ui--660m7cn-web:check",
        "inframeld-account-ui--660m7cn",
      ],
    ] as const) {
      child = spawn(process.execPath, [fixture, "inspect", "a".repeat(64)], {
        stdio: ["ignore", "pipe", "pipe"],
        env: {
          ...process.env,
          ACCOUNT_PROBE_DIRECTORY: directory,
          ACCOUNT_PROBE_PROOF: "success",
          INFRAMELD_ACCOUNT_WEB_IMAGE: image,
        },
      })
      let output = ""
      let errors = ""
      child.stdout?.on("data", (value: Buffer) => {
        output += value.toString()
      })
      child.stderr?.on("data", (value: Buffer) => {
        errors += value.toString()
      })
      const status = await completion(child, 5_000)
      if (project === undefined) {
        assert.equal(
          output.includes("private-sentinel"),
          false,
          "Controlled inspection reflected an unrecognized image binding"
        )
        assert.equal(status, 59)
        assert.equal(output, "")
        assert.equal(errors, "Controlled image binding rejected\n")
      } else {
        assert.equal(status, 0)
        assert.equal(errors, "")
        const inspection = JSON.parse(output) as {
          Config: { Labels: { "com.docker.compose.project": string } }
        }
        assert.equal(
          inspection.Config.Labels["com.docker.compose.project"],
          project
        )
      }
    }
  }
)
test(
  "TERM-ignoring active engine and descendant are killed and reaped before cleanup finishes",
  { timeout: 18_000 },
  async () => {
    await probe({ phase: "hang" }, async ({ child, directory, output }) => {
      await ready(directory, "phase-ready", child)
      await ready(directory, "descendant-ready", child)
      const active = await processes(directory)
      child.kill("SIGTERM")
      assert.equal(await completion(child), 143)
      for (const entry of active) await assertStopped(entry.pid)
      assert.doesNotMatch(output(), /qualification passed/i)
    })
  }
)
test(
  "blocked cleanup and its TERM-ignoring descendant cannot outlive the finalizer budget",
  { timeout: 18_000 },
  async () => {
    await probe({ cleanup: "hang" }, async ({ child, directory, output }) => {
      await ready(directory, "down-ready", child)
      await ready(directory, "descendant-ready", child)
      const cleanup = await processes(directory)
      assert.equal(await completion(child), 1)
      for (const entry of cleanup) await assertStopped(entry.pid)
      assert.match(output(), /cleanup exceeded|cleanup.*incomplete/i)
      assert.equal(await exists(join(directory, "retained")), true)
    })
  }
)

test(
  "a stuck phase times out with124 and retains confirmed cleanup metadata",
  { timeout: 18_000 },
  async () => {
    await probe(
      { phase: "hang", budget: 1 },
      async ({ child, directory, output }) => {
        await ready(directory, "phase-ready", child)
        assert.equal(await completion(child), 124)
        assert.match(output(), /phase exceeded/)
        assert.match(
          await readFile(join(directory, "retained/context.txt"), "utf8"),
          /cleanup=confirmed/
        )
      }
    )
  }
)

test(
  "blocked engine inventory is inside the finalizer deadline",
  { timeout: 18_000 },
  async () => {
    await probe({ inventory: "hang" }, async ({ child, directory, output }) => {
      await ready(directory, "inventory-ready", child)
      assert.equal(await completion(child), 1)
      assert.match(output(), /cleanup.*incomplete/i)
      const owned = await processes(directory)
      for (const entry of owned) await assertStopped(entry.pid)
      assert.match(
        await readFile(join(directory, "retained/context.txt"), "utf8"),
        /cleanup=incomplete/
      )
    })
  }
)

for (const status of [7, 130, 143]) {
  test(
    `blocked cleanup preserves original${status} and ignores repeated finalizer signals`,
    { timeout: 18_000 },
    async () => {
      await probe({ status, cleanup: "hang" }, async ({ child, directory }) => {
        await ready(directory, "down-ready", child)
        child.kill("SIGTERM")
        child.kill("SIGINT")
        assert.equal(await completion(child), status)
        const events = (await readFile(join(directory, "events.jsonl"), "utf8"))
          .trim()
          .split("\n")
          .map((line) => JSON.parse(line) as { kind: string })
        assert.equal(events.filter((event) => event.kind === "down").length, 1)
      })
    }
  )
}

for (const proof of ["success", "browser-exits-first"] as const)
  test(
    proof === "success"
      ? "recipient proof waits for browser readiness, both terminals and receipt verification before success"
      : "recipient proof survives successful browser completion while the Allow driver remains pending",
    { timeout: 12_000 },
    async () => {
      await probe(
        { proof, budget: 5 },
        async ({ child, directory, output }) => {
          assert.equal(await completion(child, 10_000), 0, output())
          const events = (
            await readFile(join(directory, "events.jsonl"), "utf8")
          )
            .trim()
            .split("\n")
            .map((line) => JSON.parse(line) as { kind: string; args: string[] })
          assert.equal(
            events.filter(
              (event) =>
                event.args.includes("proof-driver") && event.args.includes("up")
            ).length,
            1
          )
          const deniedStart = events.findIndex(
            (event) =>
              event.args.includes("proof-denied-driver") &&
              event.args.includes("up")
          )
          const deniedVerified = events.findIndex((event) =>
            event.args.includes("verify-denied-result")
          )
          const allowedStart = events.findIndex(
            (event) =>
              event.args.includes("proof-driver") && event.args.includes("up")
          )
          const ownerInspected = events.findIndex(
            (event) =>
              event.args[0] === "inspect" &&
              event.args.at(-1) === "a".repeat(64)
          )
          const browserStart = events.findIndex(
            (event) =>
              event.args.includes("browser-tests") && event.args.includes("up")
          )
          assert.ok(
            ownerInspected >= 0 &&
              browserStart > ownerInspected &&
              deniedStart > browserStart &&
              deniedVerified > deniedStart &&
              allowedStart > deniedVerified
          )
          if (proof === "browser-exits-first") {
            const state = JSON.parse(
              await readFile(join(directory, "proof-state.json"), "utf8")
            ) as {
              browserExitedWithDriverPending: boolean
              driverObservations: number
            }
            assert.equal(state.browserExitedWithDriverPending, true)
            assert.ok(state.driverObservations >= 2)
          }
          assert.ok(
            events.some((event) => event.args.includes("verify-proof-result"))
          )
          assert.equal(
            events.filter((event) => event.kind === "down").length,
            1
          )
          for (const entry of await processes(directory))
            await assertStopped(entry.pid)
          assert.equal(await exists(join(directory, "fuse-fired")), false)
        }
      )
    }
  )

test(
  "the maintained recipient-proof mode owns valid image tags for a mixed-separator temporary basename",
  { timeout: 15_000 },
  async () => {
    await probe(
      {
        main: true,
        proof: "success",
        basename: "inframeld-account-ui-_660m7cn",
      },
      async ({ child, directory }) => {
        assert.equal(await completion(child, 12_000), 0)
        const project = "inframeld-account-ui--660m7cn"
        const events = (await readFile(join(directory, "events.jsonl"), "utf8"))
          .trim()
          .split("\n")
          .map(
            (line) =>
              JSON.parse(line) as {
                kind: string
                args?: string[]
                images?: string[]
                context?: string
              }
          )
        const builds = events.filter((event) => event.kind === "image-build")
        assert.equal(builds.length, 2)
        for (const build of builds) {
          assert.deepEqual(
            build.images,
            ["backend", "web", "proof"].map(
              (service) => `localhost/${project}-${service}:check`
            )
          )
          assert.equal(
            build.context,
            join(directory, "inframeld-account-ui-_660m7cn", "web-context")
          )
        }
        const calls = events.flatMap((event) =>
          event.args ? [event.args] : []
        )
        for (const args of calls.filter(
          (args) => args[0] === "compose" && args.includes("-p")
        ))
          assert.equal(args[args.indexOf("-p") + 1], project)
        for (const label of [
          "com.docker.compose.project",
          "io.podman.compose.project",
        ])
          assert.ok(
            calls.some((args) => args.includes(`label=${label}=${project}`))
          )
        for (const service of ["backend", "web", "proof"])
          assert.ok(
            calls.some((args) =>
              args.includes(`reference=localhost/${project}-${service}:check`)
            )
          )
        assert.ok(calls.some((args) => args.includes("verify-denied-result")))
        assert.ok(calls.some((args) => args.includes("verify-proof-result")))
        assert.equal(events.filter((event) => event.kind === "down").length, 1)
        assert.equal(
          await exists(join(directory, "inframeld-account-ui-_660m7cn")),
          false
        )
        for (const entry of await processes(directory))
          await assertStopped(entry.pid)
        assert.equal(await exists(join(directory, "fuse-fired")), false)
      }
    )
  }
)

for (const [proof, expected, admitsDriver, classification, diagnostic] of [
  [
    "backend-wrong-id",
    1,
    false,
    "recipient-proof: inspect identity rejected",
    undefined,
  ],
  ["backend-stopped", 1, false, "recipient-proof: backend state rejected", "a"],
  [
    "backend-without-init",
    1,
    false,
    "recipient-proof: inspect process rejected",
    undefined,
  ],
  [
    "backend-host-pid",
    1,
    false,
    "recipient-proof: inspect process rejected",
    undefined,
  ],
  [
    "browser-wrong-owner",
    1,
    false,
    "recipient-proof: inspect namespace rejected",
    undefined,
  ],
  [
    "driver-browser-owner",
    1,
    true,
    "recipient-proof: inspect namespace rejected",
    undefined,
  ],
  [
    "lookup-reused-backend",
    1,
    false,
    "recipient-proof: selection rejected",
    undefined,
  ],
  ["unhealthy", 1, false, "recipient-proof: browser state rejected", "b"],
  ["browser-failed", 1, false, "recipient-proof: browser state rejected", "b"],
  [
    "inspect-invalid",
    1,
    false,
    "recipient-proof: inspection rejected",
    undefined,
  ],
  [
    "wrong-id",
    1,
    false,
    "recipient-proof: inspect identity rejected",
    undefined,
  ],
  ["driver-failed", 7, true, "recipient-proof: allowed exit rejected", "d"],
  [
    "driver-logs-failed",
    7,
    true,
    "recipient-proof: allowed exit rejected",
    "d",
  ],
  ["verify-failed", 25, true, undefined, undefined],
  ["never-ready", 124, false, undefined, undefined],
  ["stalled-terminal", 124, true, undefined, undefined],
  [
    "denied-wrong-id",
    1,
    false,
    "recipient-proof: inspect identity rejected",
    undefined,
  ],
  [
    "denied-host-net",
    1,
    false,
    "recipient-proof: inspect namespace rejected",
    undefined,
  ],
  ["denied-wrong-exit", 1, false, "recipient-proof: denied exit rejected", "e"],
  ["denied-effects", 25, false, undefined, undefined],
  ["denied-stalled", 124, false, undefined, undefined],
  [
    "second-readiness-failed",
    17,
    false,
    "recipient-proof: readiness rejected",
    "b",
  ],
  ["lookup-zero", 1, false, "recipient-proof: selection rejected", undefined],
  [
    "lookup-multiple",
    1,
    false,
    "recipient-proof: selection rejected",
    undefined,
  ],
  [
    "lookup-truncated",
    1,
    false,
    "recipient-proof: selection rejected",
    undefined,
  ],
  [
    "lookup-query-failed",
    57,
    false,
    "recipient-proof: selection rejected",
    undefined,
  ],
  [
    "lookup-wrong-project",
    1,
    false,
    "recipient-proof: inspect scope rejected",
    undefined,
  ],
  [
    "lookup-wrong-service",
    1,
    false,
    "recipient-proof: inspect scope rejected",
    undefined,
  ],
  [
    "lookup-reused-browser",
    1,
    true,
    "recipient-proof: selection rejected",
    undefined,
  ],
] as const) {
  test(
    `recipient proof ${proof} cannot report success and still reconciles its owned phase`,
    { timeout: 15_000 },
    async () => {
      await probe(
        {
          proof,
          budget: proof === "never-ready" || proof === "denied-stalled" ? 3 : 5,
        },
        async ({ child, directory, output }) => {
          assert.equal(await completion(child, 12_000), expected)
          const events = (
            await readFile(join(directory, "events.jsonl"), "utf8")
          )
            .trim()
            .split("\n")
            .map((line) => JSON.parse(line) as { kind: string; args: string[] })
          assert.equal(
            events.filter(
              (event) =>
                event.args.includes("proof-driver") && event.args.includes("up")
            ).length,
            Number(admitsDriver)
          )
          if (proof !== "verify-failed")
            assert.equal(
              events.some((event) =>
                event.args.includes("verify-proof-result")
              ),
              false
            )
          assert.equal(
            events.filter((event) => event.kind === "down").length,
            1
          )
          if (classification) {
            const initial = `${classification} (status ${expected})`
            assert.ok(output().includes(initial), output())
            const logs = events.filter((event) => event.args[0] === "logs")
            if (diagnostic) {
              const retained = logs.filter(
                (event) => event.args.at(-1) === diagnostic.repeat(64)
              )
              assert.equal(retained.length, 1)
              assert.ok(
                events.indexOf(retained[0]) <
                  events.findIndex((event) => event.kind === "down")
              )
              const role =
                diagnostic === "a"
                  ? "backend"
                  : diagnostic === "b"
                    ? "browser"
                    : diagnostic === "e"
                      ? "denied"
                      : "allowed"
              assert.ok(
                output().indexOf(`controlled ${role} diagnostic`) >
                  output().indexOf(initial)
              )
            } else {
              assert.equal(logs.length, Number(admitsDriver))
              if (admitsDriver)
                assert.equal(logs[0].args.at(-1), "e".repeat(64))
            }
            assert.doesNotMatch(output(), /(?:a{64}|b{64}|d{64}|e{64}|f{64})/)
            assert.doesNotMatch(output(), /"HostConfig"|"NetworkMode"/)
          }
          if (proof === "driver-logs-failed")
            assert.ok(
              output().includes("recipient-proof: diagnostic logs unavailable")
            )
          for (const entry of await processes(directory))
            await assertStopped(entry.pid)
          assert.equal(await exists(join(directory, "fuse-fired")), false)
        }
      )
    }
  )
}

test(
  "success is reported only after engine cleanup confirms absence and removes its diagnostics",
  { timeout: 8_000 },
  async () => {
    await probe({}, async ({ child, directory, output }) => {
      assert.equal(await completion(child, 6_000), 0)
      assert.equal(await exists(join(directory, "retained")), false)
      assert.match(output(), /checks passed\. Cleanup confirmed/)
      const events = (await readFile(join(directory, "events.jsonl"), "utf8"))
        .trim()
        .split("\n")
        .map((line) => JSON.parse(line) as { kind: string; args: string[] })
      assert.equal(events.filter((event) => event.kind === "down").length, 1)
      assert.ok(
        events.some(
          (event) =>
            event.args[0] === "volume" &&
            event.args[1] === "ls" &&
            !event.args.includes("--filter")
        )
      )
    })
  }
)

test(
  "cleanup failure changes success to1 and retains only project-specific recovery metadata",
  { timeout: 8_000 },
  async () => {
    await probe({ cleanupStatus: 9 }, async ({ child, directory, output }) => {
      assert.equal(await completion(child, 6_000), 1)
      assert.doesNotMatch(output(), /checks passed/)
      const context = await readFile(
        join(directory, "retained/context.txt"),
        "utf8"
      )
      assert.match(context, /project=inframeld-account-ui-probe/)
      assert.match(
        context,
        /backend_image=localhost\/inframeld-account-ui-probe-backend:check/
      )
      assert.match(
        context,
        /web_image=localhost\/inframeld-account-ui-probe-web:check/
      )
      assert.match(context, /web_context=.*retained\/web-context/)
      assert.match(context, /cleanup=incomplete/)
      assert.doesNotMatch(context, /authorizationUrl|cookie|token|password/i)
    })
  }
)

test("unsupported invocation or runtime exits2 before creating fixture state", async () => {
  const directory = await mkdtemp(join(tmpdir(), "account-invocation-test-"))
  try {
    for (const args of [[], ["--unsupported"], ["--login-only"]]) {
      const child = spawn("bash", [wrapper, ...args], {
        stdio: "ignore",
        env: {
          ...process.env,
          TMPDIR: directory,
          INFRAMELD_CONTAINER_RUNTIME: "unsupported",
        },
      })
      assert.equal(await completion(child, 3_000), 2)
      assert.deepEqual(await readdir(directory), [])
    }
  } finally {
    await rm(directory, { recursive: true, force: true })
  }
})

for (const volumeInventory of ["leak", "missing", "partial", "fail"] as const) {
  test(
    `global volume inventory ${volumeInventory} makes cleanup incomplete without deleting unexplained volumes`,
    { timeout: 8_000 },
    async () => {
      await probe({ volumeInventory }, async ({ child, directory, output }) => {
        assert.equal(await completion(child, 6_000), 1)
        assert.match(output(), /cleanup.*incomplete/i)
        assert.doesNotMatch(output(), /checks passed/)
        assert.match(
          await readFile(join(directory, "retained/context.txt"), "utf8"),
          /cleanup=incomplete/
        )
        const events = await readFile(join(directory, "events.jsonl"), "utf8")
        assert.doesNotMatch(events, /"volume","rm"/)
        assert.equal(
          await exists(join(directory, "retained/volumes-after.raw")),
          true
        )
        if (volumeInventory === "leak")
          assert.equal(
            await readFile(
              join(directory, "retained/volumes-added.txt"),
              "utf8"
            ),
            "unexplained-anonymous-volume\n"
          )
        if (volumeInventory === "missing")
          assert.equal(
            await readFile(
              join(directory, "retained/volumes-missing.txt"),
              "utf8"
            ),
            "original-b\n"
          )
      })
    }
  )
}

for (const baseline of ["partial", "fail", "sort-fail"] as const) {
  test(
    `a ${baseline} baseline cannot authorize build or startup`,
    { timeout: 8_000 },
    async () => {
      await probe(
        { main: true, baseline },
        async ({ child, directory, output }) => {
          assert.equal(
            await completion(child, 6_000),
            baseline === "sort-fail" ? 38 : 37
          )
          assert.match(output(), /cleanup.*incomplete/i)
          const events = await readFile(join(directory, "events.jsonl"), "utf8")
          assert.doesNotMatch(events, /"build"|"up"|"browser-tests"/)
          const retained = (await readdir(directory)).find((name) =>
            name.startsWith("inframeld-account-ui-")
          )
          assert.ok(retained)
          assert.equal(
            await exists(join(directory, retained, "volumes-before.raw")),
            true
          )
        }
      )
    }
  )
}

test(
  "blocked global volume inventory is stopped within the finalizer bound",
  { timeout: 18_000 },
  async () => {
    await probe(
      { volumeInventory: "hang" },
      async ({ child, directory, output }) => {
        await ready(directory, "inventory-ready", child)
        assert.equal(await completion(child), 1)
        assert.match(output(), /cleanup.*incomplete/i)
        for (const entry of await processes(directory))
          await assertStopped(entry.pid)
      }
    )
  }
)

test(
  "an unexplained volume preserves the original operation failure",
  { timeout: 8_000 },
  async () => {
    await probe(
      { status: 7, volumeInventory: "leak" },
      async ({ child, directory, output }) => {
        assert.equal(await completion(child, 6_000), 7)
        assert.match(output(), /cleanup.*incomplete/i)
        assert.doesNotMatch(
          await readFile(join(directory, "events.jsonl"), "utf8"),
          /"volume","rm"/
        )
      }
    )
  }
)

type StartupState = {
  initialized: string[]
  completed: string[]
  started: string[]
  tcpReady: string[]
  checks: Record<string, number>
}
async function startupState(directory: string): Promise<StartupState> {
  try {
    return JSON.parse(
      await readFile(join(directory, "startup-state.json"), "utf8")
    ) as StartupState
  } catch {
    return {
      initialized: [],
      completed: [],
      started: [],
      tcpReady: [],
      checks: {},
    }
  }
}

test(
  "fresh TLS initializes once before fixture setup and serving",
  { timeout: 12_000 },
  async () => {
    await probe({ startup: true }, async ({ child, directory, output }) => {
      assert.equal(await completion(child, 10_000), 0, output())
      const state = await startupState(directory)
      assert.deepEqual(state.initialized, [
        "account-tls-init",
        "breach-tls-init",
      ])
      assert.ok(state.completed.includes("seed"))
      assert.ok(state.started.includes("gateway"))
    })
  }
)

test(
  "socket-only temporary database startup cannot authorize migrations before final TCP readiness",
  { timeout: 12_000 },
  async () => {
    await probe({ startup: true }, async ({ child, directory, output }) => {
      assert.equal(await completion(child, 10_000), 0, output())
      const state = await startupState(directory)
      assert.deepEqual(state.tcpReady.sort(), [
        "hydra-postgres",
        "kratos-postgres",
        "postgres",
      ])
      for (const service of state.tcpReady)
        assert.ok(state.checks[service] >= 2)
    })
  }
)

for (const startupFail of [
  "account-tls-init",
  "breach-tls-init",
  "hydra-migrate",
  "kratos-migrate",
  "migrate",
  "oauth-client-setup",
  "identity-setup",
  "seed",
]) {
  test(
    `failed ${startupFail} stops downstream startup and preserves its failure`,
    { timeout: 12_000 },
    async () => {
      await probe(
        { startup: true, startupFail },
        async ({ child, directory, output }) => {
          assert.equal(await completion(child, 10_000), 23, output())
          const state = await startupState(directory)
          assert.ok(!state.completed.includes(startupFail))
          assert.ok(!state.started.includes("backend"))
          assert.ok(!state.started.includes("gateway"))
          assert.doesNotMatch(output(), /checks passed/)
        }
      )
    }
  )
}

for (const action of ["cancel", "deadline"] as const) {
  test(
    `startup ${action} stops a TERM-ignoring command and descendant in their dedicated phase group`,
    { timeout: 20_000 },
    async () => {
      await probe(
        {
          startup: true,
          startupHang: "identity-setup",
          budget: action === "deadline" ? 5 : 60,
        },
        async ({ child, directory, output }) => {
          await ready(directory, "startup-ready", child)
          await ready(directory, "descendant-ready", child)
          const active = (await processes(directory)).slice(-2)
          assert.equal(active.length, 2)
          assert.equal(active[0].group, active[1].group)
          assert.notEqual(active[0].group, child.pid)
          if (action === "cancel") child.kill("SIGTERM")
          assert.equal(
            await completion(child, 16_000),
            action === "cancel" ? 143 : 124
          )
          for (const entry of await processes(directory))
            await assertStopped(entry.pid)
          assert.ok(
            !(await startupState(directory)).started.includes("gateway")
          )
          assert.doesNotMatch(output(), /checks passed/)
        }
      )
    }
  )
}

test(
  "Python ownership regressions run in the maintained web suite",
  { timeout: 10_000 },
  async () => {
    const child = spawn("python3", ["-B", ownershipTests], { stdio: "inherit" })
    assert.equal(await completion(child, 8_000), 0)
  }
)

for (const phase of [
  "exit-with-descendant",
  "exit-with-closed-descendant",
] as const) {
  test(
    `natural phase exit still stops ${phase} before finalization`,
    { timeout: 18_000 },
    async () => {
      await probe({ phase }, async ({ child, directory, output }) => {
        await ready(directory, "descendant-ready", child)
        assert.equal(await completion(child), 0, output())
        for (const entry of await processes(directory))
          await assertStopped(entry.pid)
        assert.match(output(), /checks passed\. Cleanup confirmed/)
        assert.equal(await exists(join(directory, "fuse-fired")), false)
      })
    }
  )
}
