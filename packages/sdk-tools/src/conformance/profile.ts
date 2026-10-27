import { createServer, type Server } from "node:http";
import { readFile } from "node:fs/promises";
import { pathToFileURL } from "node:url";
import { join } from "node:path";
import type { Browser, BrowserServer } from "playwright";
import { home, cache, type Profile } from "../config.ts";
import { run } from "../system/run.ts";
import { withResources } from "../system/process.ts";
import { budgets } from "../system/budgets.ts";
import { shutdown } from "../system/shutdown.ts";
import { withinDeadline } from "../system/deadline.ts";
import { startBackend, type Backend } from "./backend.ts";
import {
  parseDriverReply,
  type DriverRequest,
  type Observation,
} from "./protocol.ts";
import type { Runtime } from "./build.ts";

export interface ProfileFixture {
  backend: Backend;
  origin: string;
  browserVersion?: string;
  execute(request: DriverRequest, signal?: AbortSignal): Promise<Observation[]>;
  close(): Promise<void>;
}

async function closeWeb(server: Server): Promise<void> {
  if (!server.listening) return;
  server.closeAllConnections();
  await new Promise<void>((resolve, reject) =>
    server.close((error) => (error ? reject(error) : resolve())),
  );
}

/** One backend per profile, one browser context per case, one native process per case. */
export async function startProfile(
  profile: Profile,
  runtime: Runtime,
  work: string,
  signal = shutdown.signal,
): Promise<ProfileFixture> {
  const startupDeadline = Date.now() + budgets.startup;
  const startupSignal = AbortSignal.any([
    signal,
    shutdown.signal,
    AbortSignal.timeout(budgets.startup),
  ]);
  const remaining = () => {
    startupSignal.throwIfAborted();
    return Math.max(1, startupDeadline - Date.now());
  };
  let browserServer: BrowserServer | undefined;
  let browser: Browser | undefined,
    web: Server | undefined,
    backend: Backend | undefined;
  let origin = "https://account.test";
  const closeBrowser = async () => {
    if (!browserServer) return;
    try {
      await withinDeadline(browserServer.close(), budgets.resourceCleanup / 2);
    } catch (error) {
      try {
        await withinDeadline(browserServer.kill(), budgets.resourceCleanup / 2);
      } catch (cleanup) {
        throw new AggregateError(
          [error, cleanup],
          "Browser close and forced kill failed",
        );
      }
      throw error;
    }
  };
  let closing: Promise<void> | undefined;
  const dispose = async () => {
    const errors: unknown[] = [];
    for (const dispose of [
      () => backend?.close(),
      closeBrowser,
      () => (web ? closeWeb(web) : undefined),
    ]) {
      try {
        await withinDeadline(
          Promise.resolve(dispose()),
          budgets.resourceCleanup,
        );
      } catch (error) {
        errors.push(error);
      }
    }
    if (errors.length)
      throw new AggregateError(errors, "Profile cleanup failed");
  };
  const close = () => (closing ??= withinDeadline(dispose(), budgets.cleanup));
  const interrupt = () => {
    void close().catch(() => {});
  };
  try {
    remaining();
    if (profile === "typescript-chromium") {
      if (!runtime.typescriptBundle)
        throw new Error("Missing browser driver bundle");
      process.env.PLAYWRIGHT_BROWSERS_PATH ??= join(cache, "browsers");
      const { chromium } = await import("playwright");
      browserServer = await chromium.launchServer({
        channel: "chromium",
        headless: true,
        timeout: remaining(),
      });
      remaining();
      browser = await chromium.connect(browserServer.wsEndpoint(), {
        timeout: remaining(),
      });
      remaining();
      const bundle = await readFile(runtime.typescriptBundle, {
        signal: startupSignal,
      });
      remaining();
      web = createServer((request, response) => {
        if (request.url === "/driver.mjs") {
          response.setHeader("Content-Type", "text/javascript");
          response.end(bundle);
        } else if (request.url === "/")
          response.end("<!doctype html><title>SDK conformance</title>");
        else {
          response.statusCode = 404;
          response.end();
        }
      });
      await withinDeadline(
        new Promise<void>((resolve, reject) => {
          web!.once("error", reject);
          web!.listen(0, "127.0.0.1", resolve);
        }),
        remaining(),
      );
      remaining();
      const address = web.address();
      if (!address || typeof address === "string")
        throw new Error("Browser origin did not bind a port");
      origin = `http://127.0.0.1:${address.port}`;
    }
    backend = await startBackend(
      work,
      profile === "typescript-chromium" ? origin : undefined,
      startupSignal,
      remaining(),
    );
    remaining();
    const execute = async (
      request: DriverRequest,
      signal = shutdown.signal,
    ): Promise<Observation[]> => {
      signal = AbortSignal.any([signal, shutdown.signal]);
      signal.throwIfAborted();
      let value: unknown;
      if (profile === "rust" || profile.startsWith("python-")) {
        const program =
          profile === "rust"
            ? runtime.rustExecutable
            : runtime.pythonExecutable;
        if (!program) throw new Error(`Missing compiled ${profile} driver`);
        const result = await run(
          program,
          profile === "rust" ? [] : [join(home, "drivers/python/main.py")],
          `${profile}-${request.caseId}`,
          {
            input: JSON.stringify(request),
            signal: AbortSignal.any([shutdown.signal, signal]),
            timeout:
              budgets.cleanup +
              request.calls.reduce((total, call) => total + call.timeout, 0),
          },
        );
        value = JSON.parse(result.stdout);
      } else if (browser) {
        const context = await browser.newContext();
        const interrupt = () => {
          void context.close().catch(() => {});
        };
        signal.addEventListener("abort", interrupt, { once: true });
        value = await withResources(
          async () => {
            const input = structuredClone(request);
            const cookie = input.calls.find((call) => call.headers.Cookie)
              ?.headers.Cookie;
            if (cookie) {
              const [name, ...parts] = cookie.split("=");
              await context.addCookies([
                { name: name!, value: parts.join("="), url: request.baseUrl },
              ]);
            }
            for (const call of input.calls) {
              delete call.headers.Cookie;
              delete call.headers.Origin;
            }
            const page = await context.newPage();
            await page.goto(origin, { timeout: budgets.case });
            const serialized = await withinDeadline(
              page.evaluate(async (serialized: string) => {
                const input = JSON.parse(serialized) as DriverRequest;
                const path = "/driver.mjs";
                const driver: import("./protocol.ts").NativeDriver =
                  await import(path);
                return JSON.stringify(await driver.execute(input));
              }, JSON.stringify(input)),
              budgets.cleanup +
                input.calls.reduce((total, call) => total + call.timeout, 0),
            );
            return JSON.parse(serialized) as unknown;
          },
          async () => {
            signal.removeEventListener("abort", interrupt);
            await withinDeadline(context.close(), budgets.resourceCleanup);
          },
        );
      } else {
        if (!runtime.typescriptBundle)
          throw new Error("Missing TypeScript driver bundle");
        const driver: import("./protocol.ts").NativeDriver = await import(
          pathToFileURL(runtime.typescriptBundle).href
        );
        value = await driver.execute(structuredClone(request), signal);
      }
      return parseDriverReply(request, value);
    };
    shutdown.signal.addEventListener("abort", interrupt, { once: true });
    shutdown.signal.throwIfAborted();
    return {
      backend,
      origin,
      ...(browser ? { browserVersion: browser.version() } : {}),
      execute,
      close: async () => {
        shutdown.signal.removeEventListener("abort", interrupt);
        await close();
      },
    };
  } catch (error) {
    try {
      await close();
    } catch (cleanup) {
      throw new AggregateError(
        [error, cleanup],
        "Profile startup and cleanup failed",
      );
    }
    throw error;
  }
}
