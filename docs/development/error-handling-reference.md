# Error handling: maintainer reference

Use this reference when changing shared error handling. For ordinary feature work, start with the [practical guide](error-handling.md), which also owns the public problem catalogue. This document explains which component to change, what its output must contain, and which tests protect it.

> **Status — 23 September 2026:** The shared foundation is implemented. Passing backend and integration tests were developer-reported during implementation closeout. They were not rerun for this documentation edit. The [qualification checklist](#qualification-checklist) lists coverage and commands for future changes.

[ADR-0004](../adr/ADR-0004-use-rfc-9457-problem-details-for-http-errors.md) owns the RFC 9457 decision. [ADR-0003](../adr/ADR-0003-generate-the-authoritative-openapi-contract-from-backend-code.md) owns the code-first API contract. Use [Application structure](application-structure.md) for dependency rules and [Pagination](pagination.md) for the shared list contract. Each list feature still validates its own cursor contents.

## Contents

| Reader's question | Start here |
| --- | --- |
| Which component owns the change? | [Implementation map](#ownership-and-implementation-scope) |
| What fields and bounds are exact? | [HTTP representation](#http-representation), [validation](#validation-translation) |
| Who builds and reports a failure? | [Handlers](#response-construction-and-handler-registration), [diagnostics](#safe-diagnostics-and-one-reporting-owner) |
| What may recover or retry? | [Transactions and recovery](#transactions-and-recovery) |
| How do runtime and schema stay aligned? | [OpenAPI](#openapi-and-client-compatibility) |
| What evidence exists and what should run? | [Qualification](#qualification-checklist) |

## Ownership and implementation scope

All paths below are relative to `apps/backend/src/inframeld_backend/`.

| Location | Responsibility |
| --- | --- |
| [shared/domain/errors.py](../../apps/backend/src/inframeld_backend/shared/domain/errors.py) | `DomainError` and `InvalidStateTransitionError`. No automatic HTTP mapping |
| [shared/application/application_error.py](../../apps/backend/src/inframeld_backend/shared/application/application_error.py) | Transport-neutral `ApplicationError` and its diagnostic-only message |
| [shared/application/errors.py](../../apps/backend/src/inframeld_backend/shared/application/errors.py) | Five starter application failures from the practical guide |
| [shared/http/problems.py](../../apps/backend/src/inframeld_backend/shared/http/problems.py) | `ProblemDetails`, `ValidationIssue`, aliases, and output bounds |
| [shared/http/problem_definitions.py](../../apps/backend/src/inframeld_backend/shared/http/problem_definitions.py) | `ProblemCode`, frozen `ProblemDefinition`, and the public problem catalogue |
| [shared/http/problem_mapper.py](../../apps/backend/src/inframeld_backend/shared/http/problem_mapper.py) | Exact-type application mapping and generic HTTP-status definitions |
| [shared/http/problem_response.py](../../apps/backend/src/inframeld_backend/shared/http/problem_response.py) | `build_problem_response()`: serialization, correlation, and allowed headers |
| [shared/http/problem_openapi.py](../../apps/backend/src/inframeld_backend/shared/http/problem_openapi.py) | `problem_responses()` declarations and the narrow OpenAPI media-type hook |
| [shared/http/validation.py](../../apps/backend/src/inframeld_backend/shared/http/validation.py) | `issues_from_request_error()`: bounded, sanitized validation issues |
| [shared/http/error_handlers.py](../../apps/backend/src/inframeld_backend/shared/http/error_handlers.py) | `register_error_handlers()`: request validation, application, HTTP, and unexpected failures |
| [shared/http/request_context.py](../../apps/backend/src/inframeld_backend/shared/http/request_context.py) | Request IDs, scoped log context, summaries, and request-boundary diagnostics |
| [shared/infrastructure/error_reporting.py](../../apps/backend/src/inframeld_backend/shared/infrastructure/error_reporting.py) | Report and mark the exact exception instance once |
| [shared/infrastructure/logging.py](../../apps/backend/src/inframeld_backend/shared/infrastructure/logging.py) | Bounded safe diagnostics, JSON/console rendering, and stdlib/Uvicorn integration |
| [shared/infrastructure/command_logging.py](../../apps/backend/src/inframeld_backend/shared/infrastructure/command_logging.py) | Command outcomes and operation metadata without duplicate tracebacks |
| [shared/infrastructure/database.py](../../apps/backend/src/inframeld_backend/shared/infrastructure/database.py) | API database lifecycle and SQLAlchemy parameter hiding |
| [shared/infrastructure/migrations.py](../../apps/backend/src/inframeld_backend/shared/infrastructure/migrations.py) and [migrate.py](../../apps/backend/src/inframeld_backend/migrate.py) | Migration locking/execution and the operator failure-reporting boundary |
| [composition.py](../../apps/backend/src/inframeld_backend/composition.py) | Install handlers, request middleware, and OpenAPI correction |

The separate Alembic engine in `apps/backend/migrations/env.py` also hides SQLAlchemy parameters.

Keep feature exceptions in the domain or application package that owns their meaning. Application interfaces define which failures an infrastructure adapter may expose. Domain and application code must not import HTTP models, FastAPI, database exceptions, or structlog. `DomainError` remains separate from `ApplicationError`.

`DatabaseStartupError`, `DatabaseSchemaCompatibilityError`, and `MigrationLockError` stay in their infrastructure modules. They report startup or operator failures, not request rejections. Failed startup must prevent readiness. An incompatible schema needs operator action. A migration cannot proceed without acquiring its lock.

Ordinary classes and functions are sufficient. Do not add an error bus, metaclass/decorator registry, generic result framework, hierarchy of infrastructure wrappers, or worker engine to maintain this foundation.

## HTTP representation

[RFC 9457][rfc9457] supplies the response format. The exact required fields, naming, cache rules, limits, and UUID convention below are **Inframeld's contract**, not extra requirements imposed by the RFC.

| Field | Contract |
| --- | --- |
| `type` | Required stable URI. At most 2,048 characters. Use the accepted absolute documentation prefix or `about:blank`, never the incoming host or class name. |
| `title` | Required, 1–128 characters. Fixed per problem type except possible localization. |
| `status` | Required strict integer, 400–599. Identical to the actual HTTP status. |
| `detail` | Required, 1–512 characters. Reviewed definition text, not arbitrary exception text. |
| `instance` | Omitted in the initial profile. Do not substitute the raw request URL. |
| `code` | Required, 1–64 characters. Pattern `^[a-z][a-z0-9_]*$`. Named types have a fixed paired code. Generic `about:blank` uses `http_error`, distinguished by status. |
| `requestId` | Required server-generated UUID string, identical to `X-Request-ID`. Python attribute `request_id`. Not identity, authorization, tracing, operation identity, or idempotency. |
| `errors` | Required for request-validation problems and absent otherwise. At most 20 sanitized issues. |

The server's output models reject extra fields when constructing a response. Clients must still tolerate new problem types and ignore unfamiliar extensions. The response builder checks that fields match their definition and that only supported problems carry `errors`. It does not serialize arbitrary exceptions.

Each immutable `ProblemDefinition` keeps its URI, code, title, status, and detail together. Mapping uses the **exact exception class**. Unless an operation explicitly supports them, unknown application subclasses, bare domain errors, ordinary Python errors, and internal/response validation failures are unexpected server failures.

## Validation translation

FastAPI's `RequestValidationError` is a transport failure. The accepted initial policy uses 422, including malformed JSON. Do not infer that status from arbitrary Pydantic `ValidationError` instances.

Each issue contains:

| Field | Allowed output |
| --- | --- |
| `location` | `body`, `path`, `query`, `header`, `cookie`, or `request` |
| `path` | Tuple in Python, array in JSON. At most eight verified public field names or strict non-negative integer indices. Names are 1–64 characters. An empty path refers to the whole location. |
| `code` | Product-owned category, with the same 64-character code constraint: `required`, `invalid_type`, `out_of_range`, `too_short`, `too_long`, `unexpected_field`, or safe fallback `invalid_value` |
| `message` | Reviewed corrective wording, 1–256 characters. No submitted values |

Create new, safe issue objects. Never return or log raw `.errors()`, `.body`, `str(exc)`, submitted `input`, arbitrary `ctx`, validator messages, or library error URLs. `hide_input_in_errors=True` does not make a Pydantic response safe by itself. Recorded references: [Pydantic error data][pydantic-errors] and [configuration][pydantic-config].

Check field paths as carefully as messages. For example, an unknown dictionary key may contain a secret, even if another part of the application uses the same word as a field name. Union tags and extra-field names can also come from the caller. Include only names verified for that position. If uncertain, stop at the last verified parent or return an empty path.

Use conservative normalization and field information owned by the endpoint. Do not build a general schema-traversal framework or rely on a list of suspicious words.

Use useful fixed descriptions: “A value is required.” or “Use a value within the permitted range.” Developer-owned constraints can support reviewed limit-specific wording. Unknown categories receive a safe fallback.

Keep the first 20 sanitized issues in validation order. Shorten paths and strings to their limits before constructing output models so error rendering cannot itself fail validation. Request bodies still need their own size limits.

## Response construction and handler registration

During application setup, register handlers once for request validation, application errors, Starlette `HTTPException`, and unexpected `Exception`. Test apps use the same registration function. Registering Starlette's base class also covers FastAPI's subclass and native router errors.

The builder creates `ProblemDetails` explicitly, then calls `model_dump(mode="json", by_alias=True, exclude_none=True)`. Returning `JSONResponse` does not make FastAPI validate its contents against the documented model. Set `application/problem+json`, `Cache-Control: no-store`, and the generated request-ID header. Take both body and HTTP status from the same definition.

For native HTTP errors, use reviewed text for the status and a safe fallback for unfamiliar error statuses. Do not copy `exc.detail`. Preserve trusted `Allow`, `WWW-Authenticate`, and deliberately supplied `Retry-After` headers. The component producing a 401 supplies its authentication challenge.

Forwarded headers cannot replace the problem media type, generated request ID, or no-store policy. Do not forward arbitrary headers from an upstream service.

HEAD responses have no body. Success, redirects, and statuses that forbid content must not receive a problem body. Supported configurations use `debug=False` because Starlette debug mode bypasses the safe 500 handler.

Middleware may reject a request before it reaches the routing handlers. Such middleware must build a safe response at its own boundary. See [Starlette's exception handling][starlette-errors].

### Correlation survives middleware cleanup

Starlette's unexpected-error middleware runs outside the application's middleware. By the time its 500 handler runs, request-context cleanup may already have happened. Its response may also bypass the application's wrapped `send`.

Therefore, read the request ID from `request.state.request_id`, not only structlog context. If initialization never ran, generate and store one fallback UUID. Reuse it in the body, header, and diagnostic. Pass request fields explicitly to outer-handler logs. Do not keep logging context alive after a request to work around cleanup.

Do not hide exceptions to silence logs. Starlette's unexpected-error path still passes the exception to the server or test harness after creating a safe response. A registered handled-exception path behaves differently. Ensure unregistered application errors still receive unexpected-failure diagnostics.

### After response start

After response headers have been sent, another failure cannot replace the status and body with a problem response. Report it and let it propagate without sending headers twice. Record the status already sent separately from the later failure. Cancellation or disconnect does not automatically mean a new 500 response was sent.

In-process background tasks have the same limitation. Durable workers instead record failures as job outcomes, not saved HTTP problem bodies. A reverse proxy or protocol layer can also produce its own errors outside the application.

## Safe diagnostics and one reporting owner

Keep the existing structlog contextvars and standard-library `ProcessorFormatter` integration. Production writes JSON to stdout. Human-readable local logs must follow the same rules for excluding sensitive data.

Approved context includes stable `event`, `request_id`, `operation_id`, `command_name`, `http_method`, declared `http_route`, `status_code`, `duration_ms`, reviewed `error_code`, and a bounded `failure_kind`. Omit unmatched raw paths or use a fixed sentinel. Do not log bodies, query strings, arbitrary headers, or unreviewed URLs. Log field casing remains snake_case.

The HTTP request boundary reports unexpected failures. Command logging records the operation's outcome and re-raises without another traceback. Normal client rejections usually produce informational outcomes. Known dependency failures need operational error reporting, with one sanitized diagnostic when a cause is available. A future worker reports at its own execution boundary.

`report_unexpected_error()` marks the **same exception instance** with a private, runtime-only “already reported” attribute. Do not expose or persist that flag, or mark unrelated causes. If the outer handler sees an unreported failure, it reports it using the request ID from request state.

The `uvicorn.error` filter suppresses a traceback only for that reported exception. Unrelated messages, unreported errors, and startup failures remain visible. Keep the real Uvicorn integration test as well as TestClient tests, because they exercise different reporting paths.

### Sanitization covers more than local variables

The custom transformer in `logging.py` walks exception structure for Structlog's `ExceptionRenderer` without reading messages, notes, locals, or source lines. Do not replace it with unrestricted `dict_tracebacks`. Turning off local variables alone would still expose exception text. See the recorded [Structlog API reference][structlog-api].

Keep limited exception type names, file/function/line locations, and relationships between causes, contexts, and grouped exceptions. Exclude arbitrary values, notes, source snippets, and locals at **every nesting level**. Useful descriptions must come from approved structured fields.

Limit the work of extraction as well as its output. Bound frames, depth, breadth, and total visited exceptions, and stop cycles from causing endless traversal.

JSON and console output must use the same sanitized diagnostic. Neither should format the original exception again. Clear or replace raw `exc_info` and cached exception text in standard-library logging too, so its formatter cannot append a second, unsafe traceback.

Review third-party log messages separately. Cleaning exception fields does not clean arbitrary message text. API and Alembic SQLAlchemy engines use `hide_parameters=True` as an extra safeguard, but that cannot sanitize driver messages or SQL literals. Regular-expression redaction alone cannot prove all secrets were removed.

### Operator-controlled migrations

Run `pnpm --filter @inframeld/backend migrate`. This invokes `inframeld_backend.migrate`, which calls the existing `run_migrations()` and reports caught failures as `migration_failed` before exiting with a nonzero status. It does not automatically retry. The programmatic function continues to raise for callers that own their own execution boundary.

Alembic's `env.py` installs its own logging settings. Before reporting a caught migration failure, the wrapper restores the shared safe formatter. It uses the configured output format if settings loaded, otherwise JSON. Direct Alembic CLI calls bypass this wrapper and are not the documented operator command. The wrapper cannot undo text already emitted by migration code or third-party logs.

The PostgreSQL tests cover hidden parameters and a synthetic driver message raised during migration, inspecting stdout and stderr. A failed migration still fails. API startup checks compatibility without running migrations, and a failed startup cannot begin serving.

## Transactions and recovery

Commands own short database transactions and make external calls outside them. Let exceptions leave transaction contexts before the HTTP handler builds the response, so rollback can happen. The handler must not commit, authorize, retry, migrate, or resume uncertain paid work.

Translate a database constraint failure only when the adapter recognizes the exact structured driver or constraint condition. Do not parse message text or treat every `IntegrityError` as a user conflict. Verify the selected driver's representation in the adapter and its integration tests.

Let `CancelledError`, `KeyboardInterrupt`, and `SystemExit` continue. Use context managers or `finally` for cleanup without hiding errors. A provider timeout does not establish whether work happened. Neither HTTP 503 nor `DependencyUnavailableError` authorizes a retry. Follow the [job and idempotency rules](jobs-and-idempotency.md).

## OpenAPI and client compatibility

Each route declares its success model and applicable errors using `problem_responses(definition)`. Routes with input validation declare `VALIDATION_ERROR_PROBLEM` instead of the default 422 `HTTPValidationError`. Registering handlers does not supply those declarations. The production `/health` route currently declares unexpected 500. Test-only routes exercise JSON and multipart validation.

The installed FastAPI version places additional response models under the route's default media type. To describe problem responses correctly, `problem_responses()` adds the model and a private `x-inframeld-problem-response` marker.

Application setup calls `configure_problem_openapi()` once. It wraps the original bound `application.openapi` method, keeping native component generation and caching. For a marked response, it moves the sole representation to `application/problem+json` and removes the marker. Success and unmarked responses stay unchanged. Multiple representations on a marked response cause an error rather than silently losing one.

Keep this adjustment limited to declared problem responses. Do not create another schema generator or change the OpenAPI dialect. When upgrading FastAPI, rerun contract tests and check whether the adjustment is still needed. Verify component references and that error responses do not advertise unsupported `application/json`.

The runtime response and schema must agree on aliases, required and nullable fields, limits, and omitted optional fields. A model may be absent from the committed production schema until a production response uses it. Never mount test fixture routes in the product or export them in its schema.

Use the existing OpenAPI 3.1.x exporter and drift check. Do not hand-edit `contracts/openapi/v1/inframeld-v1.json`, add another exporter, down-convert the schema, or begin SDK Kit work here. Clients need fallbacks for unfamiliar problem types and upstream responses in other formats. HTTP status alone does not define a shared retry policy.

## Qualification checklist

| Area | Required behavioral evidence |
| --- | --- |
| Public contract | Correct status/body/media type, aliases, field bounds, omission rules, safe 500, and replacement 422 schema |
| Classification | Supported mappings work. Unsupported subclasses, bare domain errors, internal validation, response validation, and bugs remain server failures |
| HTTP semantics | Native 404/405, appropriate 401 challenge, preserved trusted headers, HEAD with no body, and no problem body for a non-error status |
| Disclosure | Synthetic secrets absent from responses and final JSON/console logs, including submitted keys, messages, causes, notes, groups, locals, and standard-library exception records |
| Correlation | Matching body/header/diagnostic UUIDs on handled and unexpected failures. No cross-request leakage under concurrency or mixed sync/async execution |
| Diagnostics | One diagnostic report. Command outcomes retain operation identity. Unrelated Uvicorn failures remain visible |
| Lifecycle | Cancellation propagates. Transaction rollback is preserved. Late failures never send headers twice. Failed startup never becomes ready |
| Integration | Actual selected server/driver behavior tested where changed. Mocks are not proof of real adapter compatibility |

Use `TestClient(..., raise_server_exceptions=False)` to inspect unexpected 500 responses. Also keep a normal test proving that the server-error path still propagates the exception. To test secret disclosure, capture the **final rendered logs through production processors**. Bare `structlog.testing.capture_logs()` disables those processors and cannot establish safety by itself. See [structlog testing][structlog-testing].

HTTP and schema fixtures require no production credentials, provider calls, or database. PostgreSQL integration tests use the development test database. Follow the repository's scaffold → behavioral red test → implementation → focused tests sequence where adding behavior. The existing test setup requires the non-production `apps/backend/.env.test`.

Regression coverage lives in:

- [HTTP unit tests](../../apps/backend/tests/unit/shared/http): models, builders, mappings, validation, handlers, correlation, late failures, and cancellation.
- [Infrastructure unit tests](../../apps/backend/tests/unit/shared/infrastructure): rendered diagnostic sanitization and reporting ownership.
- [OpenAPI contract tests](../../apps/backend/tests/unit/contract/test_openapi_contract.py): media types, components, aliases, field constraints, multipart requests, drift, and exclusion of fixture routes.
- [Uvicorn integration test](../../apps/backend/tests/integration/test_error_reporting_uvicorn.py): server-path diagnostic deduplication.
- [Database integration tests](../../apps/backend/tests/integration/test_database_postgres.py) and [migration integration tests](../../apps/backend/tests/integration/test_migrations_postgres.py): transactions, lifecycle, engine parameter hiding, and migration-command disclosure.

From the repository root, run the relevant checks after changing the foundation:

```bash
pnpm --filter @inframeld/backend lint
pnpm --filter @inframeld/backend format:check
pnpm --filter @inframeld/backend typecheck
pnpm --filter @inframeld/backend test
pnpm --filter @inframeld/backend openapi:check
pnpm test:integration
```

After changing production declarations, run `pnpm --filter @inframeld/backend openapi` before checking drift. It writes the generated contract. Integration tests require the local Compose database, migrate the non-production `.env.test` database, and exercise actual PostgreSQL behavior. These are future verification instructions, not commands run for this documentation edit.

Review dependency boundaries and repository organization manually. Do not add automated architecture, import-boundary, or composition-construction tests. Test observable behavior rather than importability or inheritance alone.

Use Google-style docstrings for public exceptions, interfaces, use cases, HTTP models, builders, handlers, and diagnostics. Explain meaning, safe attributes, recovery behavior, and relevant `Raises` cases. Keep response fields and OpenAPI descriptions consistent with this reference.

When the foundation changes, update affected guides, architecture, backend README, and skills together. List endpoints also need their own checks of cursor contents and authorization on every page.

## Source basis

The file map and implementation descriptions were checked against source and tests on 23 September 2026. Passing test results were developer-reported. The practical guide's feature examples remain illustrative. The references below explain framework behavior, while repository code and behavioral tests define Inframeld's integration.

[rfc9457]: https://www.rfc-editor.org/rfc/rfc9457.html
[pydantic-errors]: https://docs.pydantic.dev/latest/errors/errors/
[pydantic-config]: https://docs.pydantic.dev/latest/api/config/#pydantic.config.ConfigDict.hide_input_in_errors
[starlette-errors]: https://starlette.dev/exceptions/
[structlog-api]: https://www.structlog.org/en/stable/api.html#structlog.tracebacks.ExceptionDictTransformer
[structlog-testing]: https://www.structlog.org/en/stable/testing.html
