import { join } from "node:path";
import { root, cache, artifacts } from "../config.ts";
import { command, type CommandOptions, type CommandResult } from "./process.ts";
import { shutdown } from "./shutdown.ts";

export function run(
  program: string,
  args: readonly string[],
  label: string,
  options: CommandOptions = {},
): Promise<CommandResult> {
  return command(program, args, {
    cwd: root,
    signal: shutdown.signal,
    ...options,
    env: {
      UV_CACHE_DIR: join(cache, "uv"),
      NO_PROXY: "127.0.0.1,localhost",
      ...options.env,
    },
    log: join(artifacts, label + ".log"),
  });
}
