export const shutdown = new AbortController();

/** CLI cancellation is shared by subprocesses and HTTP fixture resources. */
export function installInterruptHandlers(): () => void {
  const interrupt = (signal: NodeJS.Signals) =>
    shutdown.abort(new Error(`Interrupted by ${signal}`));
  const term = () => interrupt("SIGTERM");
  const int = () => interrupt("SIGINT");
  process.once("SIGINT", int);
  process.once("SIGTERM", term);
  return () => {
    process.off("SIGINT", int);
    process.off("SIGTERM", term);
  };
}
