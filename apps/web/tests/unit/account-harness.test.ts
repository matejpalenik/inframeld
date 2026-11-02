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
import { join, resolve } from "node:path"
import { setTimeout } from "node:timers/promises"
import { test } from "node:test"
const wrapper = resolve("../../scripts/test-account-ui.sh")
const fixture = resolve("tests/fixtures/account-runtime-probe.mjs")
const runner = resolve("../../scripts/run_account_ui.py")
const ownershipTests = resolve("../../scripts/test_account_ui.py")
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
        command = self._shell("startup_stack") if startup else ["docker", "probe-phase"]
        status = self._run_phase("startup" if startup else "probe", command,
                                 float(os.environ["ACCOUNT_PROBE_BUDGET"]))
        self.qualification_complete = status == 0
        return status
root = Path(sys.argv[1]).resolve().parents[1]
raise SystemExit(Probe(root, directory=Path(sys.argv[2]) / "retained",
                      cleanup_work_seconds=2).run(["--login-only"]))
`

type Options = {
  phase?: "hang" | "exit-with-descendant" | "exit-with-closed-descendant"
  cleanup?: "hang"
  inventory?: "hang" | "remaining"
  status?: number
  cleanupStatus?: number
  budget?: number
  main?: boolean
  startup?: boolean
  startupFail?: string
  startupHang?: string
  volumeInventory?: "leak" | "missing" | "partial" | "fail" | "hang"
  baseline?: "partial" | "fail" | "sort-fail"
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
    `#!${process.execPath}\n${await readFile(fixture, "utf8")}`,
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
    options.main ? "bash" : "python3",
    options.main
      ? [wrapper, "--login-only"]
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
        ACCOUNT_PROBE_STARTUP: String(options.startup ?? false),
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
