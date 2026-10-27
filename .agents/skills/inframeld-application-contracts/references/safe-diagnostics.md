# Report failures without exposing protected values

<a id="report-failures-without-exposing-protected-values"></a>

Alice’s failed request needs enough information for debugging without printing its credential or private content. One reporting boundary records a bounded sanitized diagnostic and the same request identity returned to the caller.

> **Status:** accepted behavior is stated separately from proposed representations and qualification work. Existing Python types, generated OpenAPI and migrations own implemented shapes. Pending decisions are not accepted by this reference.

<a id="logging-cleanup-and-retries"></a>

<a id="6-logging-cleanup-and-retries"></a>

## Logging, cleanup, and retries

**Feature code raises the failure. The request boundary reports it.** Do not add `logger.exception()` before every re-raise. The request handler owns unexpected-failure diagnostics. Command logging records a limited outcome and operation ID without another traceback. Report known dependency failures too. Ordinary client rejections usually need no traceback.

Write exception messages as controlled developer text, but do not assume they or chained SDK messages are safe to log. Use approved fields such as request ID, operation ID, route template, and failure category. Exclude document text, prompts, keys, SQL parameters, and provider bodies.

**Cleaning up does not turn failure into success.** Prefer context managers and let exceptions leave the transaction so rollback happens before the HTTP response is built. Never return success from `except` or `finally` after a failed command. Keep external calls outside short SQL transactions. When a catch needs to pass on the same exception, use bare `raise`.

**Cancellation is not an ordinary 500.** Do not catch `BaseException`. Let cancellation, `KeyboardInterrupt`, and `SystemExit` continue. Use `finally` for necessary cleanup without hiding the original failure. See [asyncio cancellation](https://docs.python.org/3/library/asyncio-exceptions.html).

**A 503 is not permission to repeat an operation.** Idempotency, uncertain paid calls, recorded job state, and expected revisions retain their existing application rules. Never “fix” a revision conflict by replacing the client's revision and retrying automatically.

<a id="correlation-survives-middleware-cleanup"></a>

### Correlation survives middleware cleanup

Starlette's unexpected-error middleware runs outside the application's middleware. By the time its 500 handler runs, request-context cleanup may already have happened. Its response may also bypass the application's wrapped `send`.

Therefore, read the request ID from `request.state.request_id`, not only structlog context. If initialization never ran, generate and store one fallback UUID. Reuse it in the body, header, and diagnostic. Pass request fields explicitly to outer-handler logs. Do not keep logging context alive after a request to work around cleanup.

Do not hide exceptions to silence logs. Starlette's unexpected-error path still passes the exception to the server or test harness after creating a safe response. A registered handled-exception path behaves differently. Ensure unregistered application errors still receive unexpected-failure diagnostics.

<a id="after-response-start"></a>

### After response start

After response headers have been sent, another failure cannot replace the status and body with a problem response. Report it and let it propagate without sending headers twice. Record the status already sent separately from the later failure. Cancellation or disconnect does not automatically mean a new 500 response was sent.

In-process background tasks have the same limitation. Durable workers instead record failures as job outcomes, not saved HTTP problem bodies. A reverse proxy or protocol layer can also produce its own errors outside the application.

<a id="safe-diagnostics-and-one-reporting-owner"></a>

## Safe diagnostics and one reporting owner

Keep the existing structlog contextvars and standard-library `ProcessorFormatter` integration. Production writes JSON to stdout. Human-readable local logs must follow the same rules for excluding sensitive data.

Approved context includes stable `event`, `request_id`, `operation_id`, `command_name`, `http_method`, declared `http_route`, `status_code`, `duration_ms`, reviewed `error_code`, and a bounded `failure_kind`. Omit unmatched raw paths or use a fixed sentinel. Do not log bodies, query strings, arbitrary headers, or unreviewed URLs. Log field casing remains snake_case.

The HTTP request boundary reports unexpected failures. Command logging records the operation's outcome and re-raises without another traceback. Normal client rejections usually produce informational outcomes. Known dependency failures need operational error reporting, with one sanitized diagnostic when a cause is available. A future worker reports at its own execution boundary.

`report_unexpected_error()` marks the **same exception instance** with a private, runtime-only “already reported” attribute. Do not expose or persist that flag, or mark unrelated causes. If the outer handler sees an unreported failure, it reports it using the request ID from request state.

The `uvicorn.error` filter suppresses a traceback only for that reported exception. Unrelated messages, unreported errors, and startup failures remain visible. Keep the real Uvicorn integration test as well as TestClient tests, because they exercise different reporting paths.

<a id="sanitization-covers-more-than-local-variables"></a>

### Sanitization covers more than local variables

The custom transformer in `logging.py` walks exception structure for Structlog's `ExceptionRenderer` without reading messages, notes, locals, or source lines. Do not replace it with unrestricted `dict_tracebacks`. Turning off local variables alone would still expose exception text. See the recorded [Structlog API reference](https://www.structlog.org/en/stable/api.html#structlog.tracebacks.ExceptionDictTransformer).

Keep limited exception type names, file/function/line locations, and relationships between causes, contexts, and grouped exceptions. Exclude arbitrary values, notes, source snippets, and locals at **every nesting level**. Useful descriptions must come from approved structured fields.

Limit the work of extraction as well as its output. Bound frames, depth, breadth, and total visited exceptions, and stop cycles from causing endless traversal.

JSON and console output must use the same sanitized diagnostic. Neither should format the original exception again. Clear or replace raw `exc_info` and cached exception text in standard-library logging too, so its formatter cannot append a second, unsafe traceback.

Review third-party log messages separately. Cleaning exception fields does not clean arbitrary message text. API and Alembic SQLAlchemy engines use `hide_parameters=True` as an extra safeguard, but that cannot sanitize driver messages or SQL literals. Regular-expression redaction alone cannot prove all secrets were removed.

<a id="operator-controlled-migrations"></a>

### Operator-controlled migrations

Run `pnpm --filter @inframeld/backend migrate`. This invokes `inframeld_backend.migrate`, which calls the existing `run_migrations()` and reports caught failures as `migration_failed` before exiting with a nonzero status. It does not automatically retry. The programmatic function continues to raise for callers that own their own execution boundary.

Alembic's `env.py` installs its own logging settings. Before reporting a caught migration failure, the wrapper restores the shared safe formatter. It uses the configured output format if settings loaded, otherwise JSON. Direct Alembic CLI calls bypass this wrapper and are not the documented operator command. The wrapper cannot undo text already emitted by migration code or third-party logs.

The PostgreSQL tests cover hidden parameters and a failing constraint carrying a synthetic marker in the real driver diagnostic during migration, inspecting stdout and stderr. A failed migration still fails. API startup checks compatibility without running migrations, and a failed startup cannot begin serving.
