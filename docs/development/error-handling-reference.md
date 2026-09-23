# Error handling: maintainer reference

**Read this when changing the shared foundation.** The [practical guide](error-handling.md) explains ordinary usage and owns the stable public problem catalogue. This reference describes the implemented components and the rules their tests protect.

**Status — 23 September 2026:** the error-handling foundation is implemented. The developer reported passing backend and integration tests during implementation closeout; this documentation update did not rerun them. The [qualification checklist](#qualification-checklist) identifies the regression coverage and commands to run for later changes. The separate [pagination guide](pagination.md) describes the implemented shared contract; each owning feature validates cursor contents. ADR-0002 owns the public contract and ADR-0001 owns dependency rules.

## Ownership and implementation scope

All paths below are relative to `apps/backend/src/inframeld_backend/`.

| Location | Responsibility |
| --- | --- |
| `shared/domain/errors.py` | `DomainError` and `InvalidStateTransitionError`; no automatic HTTP mapping |
| `shared/application/application_error.py` | Transport-neutral `ApplicationError` and its diagnostic-only message |
| `shared/application/errors.py` | Five starter application failures from the practical guide |
| `shared/http/problems.py` | `ProblemDetails`, `ValidationIssue`, aliases, and output bounds |
| `shared/http/problem_definitions.py` | `ProblemCode`, frozen `ProblemDefinition`, and the public problem catalogue |
| `shared/http/problem_mapper.py` | Exact-type application mapping and generic HTTP-status definitions |
| `shared/http/problem_response.py` | `build_problem_response()`: serialization, correlation, and allowed headers |
| `shared/http/problem_openapi.py` | `problem_responses()` declarations and the narrow OpenAPI media-type hook |
| `shared/http/validation.py` | `issues_from_request_error()`: bounded, sanitized validation issues |
| `shared/http/error_handlers.py` | `register_error_handlers()`: request validation, application, HTTP, and unexpected failures |
| `shared/http/request_context.py` | Request IDs, scoped log context, summaries, and request-boundary diagnostics |
| `shared/infrastructure/error_reporting.py` | Report and mark the exact exception instance once |
| `shared/infrastructure/logging.py` | Bounded safe diagnostics, JSON/console rendering, and stdlib/Uvicorn integration |
| `shared/infrastructure/command_logging.py` | Command outcomes and operation metadata without duplicate tracebacks |
| `shared/infrastructure/database.py` | API database lifecycle and SQLAlchemy parameter hiding |
| `shared/infrastructure/migrations.py` and `migrate.py` | Migration locking/execution and the operator failure-reporting boundary |
| `composition.py` | Install handlers, request middleware, and OpenAPI correction |

The separate Alembic engine is configured in `apps/backend/migrations/env.py`; it also uses SQLAlchemy parameter hiding.

Feature exceptions stay in their owner's domain/application package. Application ports own the failure contract offered by their infrastructure implementations. Domain/application code must not import HTTP models, FastAPI, database exceptions, or structlog. `DomainError` must not inherit from `ApplicationError`.

Keep existing `DatabaseStartupError`, `DatabaseSchemaCompatibilityError`, and `MigrationLockError` in their infrastructure modules. They are startup/operator failures, not request errors. Failed startup cannot become ready, incompatible schemas require operator action, and migrations cannot proceed without their lock.

Use ordinary classes and functions. Do not add an error bus, metaclass/decorator registry, generic result framework, infrastructure-wrapper hierarchy, or worker execution engine for this issue.

## HTTP representation

[RFC 9457][rfc9457] supplies the format. The following required fields, naming, cache policy, limits, and UUID convention are **Inframeld choices**, not additional RFC requirements.

| Field | Contract |
| --- | --- |
| `type` | Required stable URI; at most 2,048 characters. Use the accepted absolute documentation prefix or `about:blank`, never the incoming host or class name. |
| `title` | Required, 1–128 characters; fixed per problem type except possible localization. |
| `status` | Required strict integer, 400–599; identical to the actual HTTP status. |
| `detail` | Required, 1–512 characters; reviewed definition text, not arbitrary exception text. |
| `instance` | Omitted in the initial profile. Do not substitute the raw request URL. |
| `code` | Required, 1–64 characters; pattern `^[a-z][a-z0-9_]*$`. Named types have a fixed paired code. Generic `about:blank` uses `http_error`, distinguished by status. |
| `requestId` | Required server-generated UUID string, identical to `X-Request-ID`; Python attribute `request_id`. Not identity, authorization, tracing, operation identity, or idempotency. |
| `errors` | Required for request-validation problems and absent otherwise; at most 20 sanitized issues. |

The server construction models reject extra fields. Clients must still ignore unfamiliar extensions and tolerate new problem types. The response builder—not a general exception serializer—enforces the definition pairing and which problems may carry `errors`.

Keep each definition's URI, code, title, status, and detail together in one small frozen value. Select supported exceptions by **exact concrete class**. Unknown application subclasses, bare domain errors, ordinary Python errors, and response/internal validation failures follow the unexpected-failure policy unless explicitly supported for that operation.

## Validation translation

FastAPI's `RequestValidationError` is a transport failure. The accepted initial policy uses 422, including malformed JSON. Do not infer that status from arbitrary Pydantic `ValidationError` instances.

Each issue contains:

| Field | Allowed output |
| --- | --- |
| `location` | `body`, `path`, `query`, `header`, `cookie`, or `request` |
| `path` | Tuple in Python, array in JSON; at most eight verified public field names or strict non-negative integer indices. Names are 1–64 characters. An empty path refers to the whole location. |
| `code` | Product-owned category, with the same 64-character code constraint: `required`, `invalid_type`, `out_of_range`, `too_short`, `too_long`, `unexpected_field`, or safe fallback `invalid_value` |
| `message` | Reviewed corrective wording, 1–256 characters; no submitted values |

Build fresh issue objects. Never return or log raw `.errors()`, `.body`, `str(exc)`, submitted `input`, arbitrary `ctx`, validator messages, or library error URLs. Pydantic's `hide_input_in_errors=True` is not a validation-response sanitizer. See [Pydantic error data][pydantic-errors] and [configuration][pydantic-config].

Verify paths as well as messages. Unknown object/dictionary keys, union tags, and extra-field names may be attacker-controlled. A globally familiar word does not prove a key is a declared field at that position. Keep the last verified parent, or use an empty path, when unsure. Start with a conservative normalizer and endpoint-owned path information; do not build an exhaustive schema-traversal framework or a suspicious-word denylist.

Use useful fixed descriptions: “A value is required.” or “Use a value within the permitted range.” Developer-owned constraints can support reviewed limit-specific wording. Unknown categories receive a safe fallback.

Take the first 20 sanitized issues in validation order and truncate paths/strings before constructing output models. Do not let rendering create a second validation error. These output bounds do not replace request-body limits.

## Response construction and handler registration

Register four handler paths once during composition: request validation, application errors, Starlette `HTTPException`, and unexpected `Exception`. Test applications use the same registration function. Register Starlette's base to include FastAPI's subclass and native router errors.

The builder explicitly constructs `ProblemDetails` and uses `model_dump(mode="json", by_alias=True, exclude_none=True)`. Returning `JSONResponse` directly does not cause FastAPI to validate that content against a documented model. Supply `application/problem+json`, `Cache-Control: no-store`, and the generated request-ID header; body and response status come from the same definition.

Normalize native HTTP errors using safe status-specific text and a generic fallback for unfamiliar error statuses. Do not echo `exc.detail`. Preserve trusted `Allow`, `WWW-Authenticate`, and intentionally supplied `Retry-After` headers. A 401 producer must supply the correct challenge. Passed headers cannot override the problem media type, generated ID, or no-store policy; do not forward arbitrary upstream headers.

HEAD responses have no body. Do not create problem bodies for success, redirects, or statuses that prohibit content. Run supported application configurations with `debug=False`: Starlette's debug mode bypasses the safe 500 handler. HTTP exceptions raised outside the handled routing layer cannot be assumed to use the same conversion; middleware that rejects a request must return the appropriate safe response at its own boundary. See [Starlette's exception handling][starlette-errors].

### Correlation survives middleware cleanup

Starlette's unexpected-error middleware wraps user middleware. The outer 500 handler can run after request-context cleanup, and its response can bypass the user's wrapped `send`.

Read the request ID from `request.state.request_id`, not only structlog context. A defensive fallback generates and stores one UUID when initialization has not run. Use that same value in the body, header, and diagnostic. Use explicit request fields in outer-handler logs; do not leave context bound after a request to work around its lifetime.

Do not suppress exceptions to make logging quiet. Unexpected exceptions handled by Starlette's server-error path still propagate to the server/test harness after a safe response is generated. Returning a response from a registered handled-exception path is different; ensure unmapped application errors still receive unexpected-failure diagnostics.

### After response start

Once headers have been sent, a failure cannot replace the status/body with a new problem. Record the late failure and propagate it, without a second response-start message. Report the observed status separately from the execution failure; a cancelled/disconnected request is not automatically a new 500 response.

In-process background tasks have the same response-start limitation. Durable worker failures belong to recorded job outcomes, not stored HTTP problem bodies. Reverse-proxy and protocol errors outside the application are separate response producers.

## Safe diagnostics and one reporting owner

Keep the existing structlog contextvars and standard-library `ProcessorFormatter` integration. Production emits JSON to stdout; readable local output obeys the same disclosure rules.

Approved context includes stable `event`, `request_id`, `operation_id`, `command_name`, `http_method`, declared `http_route`, `status_code`, `duration_ms`, reviewed `error_code`, and a bounded `failure_kind`. Omit unmatched raw paths or use a fixed sentinel. Do not log bodies, query strings, arbitrary headers, or unreviewed URLs. Log field casing remains snake_case.

The HTTP execution boundary owns unexpected diagnostics. Command scope emits its operation outcome and re-raises, without a second traceback. Expected client rejections normally emit informational outcomes. Known dependency failures warrant operational error reporting, with one sanitized diagnostic when a cause is available. A future worker owns its own execution boundary.

`report_unexpected_error()` marks the **exact exception instance** with a private runtime-only “already reported” attribute. Do not add it to the public exception contract, persist it, or mark unrelated causes. The outer handler reports an unreported failure with explicit request-state correlation. The `uvicorn.error` filter suppresses a server traceback only for that same reported exception. Preserve unrelated messages, unreported exceptions, and startup failures. The Uvicorn integration test exercises the selected server's reporting path; retain it alongside TestClient tests.

### Sanitization covers more than local variables

`logging.py` supplies a custom transformer to Structlog's `ExceptionRenderer`. It traverses exception structure without reading messages, notes, locals, or source lines. Do not replace it with unrestricted `dict_tracebacks` output. Disabling locals alone would still leave unreviewed exception text; see Structlog's [API reference][structlog-api].

Keep bounded exception types, file/function/line locations, and cause/context/group relationships. Exclude arbitrary exception values, notes, source snippets, and locals **at every nesting level**. Use approved structured metadata for useful descriptions. Bound extraction work as well as the final output: frame counts, traversal depth, breadth, and total visited exceptions. Handle cycles without unbounded traversal.

JSON and console renderers must consume the same sanitized diagnostic, rather than independently formatting the original exception. Standard-library integration must also clear or replace raw `exc_info` and cached exception text so a formatter cannot append an unsanitized traceback.

Review third-party free-text logging separately; sanitizing exception fields does not sanitize arbitrary log messages. Both the API and Alembic engines set SQLAlchemy `hide_parameters=True` as defense in depth. It does not sanitize driver messages or SQL literals. Regex redaction cannot establish that all secrets were removed.

### Operator-controlled migrations

Run `pnpm --filter @inframeld/backend migrate`. This invokes `inframeld_backend.migrate`, which calls the existing `run_migrations()` and reports caught failures as `migration_failed` before exiting with a nonzero status. It does not automatically retry. The programmatic function continues to raise for callers that own their own execution boundary.

Alembic's `env.py` installs its own logging configuration. The command restores the shared sanitized formatter before reporting a caught failure. It uses the configured output format when settings loaded successfully, or JSON when settings could not be loaded. Direct Alembic CLI invocations bypass this boundary; do not use them as the documented operator command. The wrapper cannot retract text already emitted by migration code or a third-party logger.

The real PostgreSQL tests cover parameter hiding and a synthetic driver message raised during migration, capturing both stdout and stderr. Failed migrations still fail; failed API startup still prevents serving requests. API startup checks compatibility and does not run migrations.

## Transactions and recovery

The command owns short transactions; external calls happen outside them. Exceptions must leave transaction contexts before the HTTP handler consumes them. An error handler must not commit, authorize, retry, start migrations, or resume uncertain paid work.

Translate a database constraint violation only after identifying the exact understood structured driver/constraint condition. Do not parse message text or classify all `IntegrityError` instances as user conflicts. Identify the actual driver representation in that adapter's implementation and integration tests.

Keep `CancelledError`, `KeyboardInterrupt`, and `SystemExit` propagating. Prefer context managers or `finally` for cleanup without suppressing errors. A provider timeout does not prove work had no effect; neither a 503 nor `DependencyUnavailableError` authorizes replay. Preserve ADR-0007's idempotency and uncertainty rules.

## OpenAPI and client compatibility

Each route declares its actual success model and applicable error responses with `problem_responses(definition)`. Input-validating routes declare `VALIDATION_ERROR_PROBLEM` to replace the default 422 `HTTPValidationError` contract. Handler registration alone does not declare a response. `/health` currently declares the applicable unexpected 500; JSON and multipart validation are exercised on test-only routes.

The installed FastAPI version generates an additional response model under the route's default media type. `problem_responses()` therefore adds the model plus a private `x-inframeld-problem-response` marker. Composition calls `configure_problem_openapi()` once: it wraps the original bound `application.openapi` method, preserves native component generation and caching, moves each marked response's sole representation to `application/problem+json`, and removes the marker. It leaves successful and unmarked responses unchanged. A marked response with multiple representations is rejected rather than silently dropping one.

Keep this adjustment limited to declared problem responses. Do not introduce a second schema generator or change the OpenAPI dialect. When upgrading FastAPI, rerun the contract tests and reassess whether the adjustment is still needed. Test the generated result for component references and the absence of an unsupported `application/json` error representation.

Runtime and schema must agree on aliases, required/nullable fields, constraints, and optional-field omission. Models may remain absent from the committed production schema until a real production response references them. Test-only fixture routes must never be mounted in the product app or exported in its schema.

Use the existing native OpenAPI 3.1.x exporter and drift check. Do not hand-edit `contracts/openapi/v1/inframeld-v1.json`, introduce another exporter, down-convert the schema, or begin SDK Kit work here. SDK clients need fallbacks for unknown types and non-problem upstream errors; no shared status-based retry policy is implied.

## Qualification checklist

| Area | Required behavioral evidence |
| --- | --- |
| Public contract | Correct status/body/media type, aliases, field bounds, omission rules, safe 500, and replacement 422 schema |
| Classification | Supported mappings work; unsupported subclasses, bare domain errors, internal validation, response validation, and bugs remain server failures |
| HTTP semantics | Native 404/405, appropriate 401 challenge, preserved trusted headers, HEAD with no body, and no problem body for a non-error status |
| Disclosure | Synthetic secrets absent from responses and final JSON/console logs, including submitted keys, messages, causes, notes, groups, locals, and standard-library exception records |
| Correlation | Matching body/header/diagnostic UUIDs on handled and unexpected failures; no cross-request leakage under concurrency or mixed sync/async execution |
| Diagnostics | One diagnostic report; command outcomes retain operation identity; unrelated Uvicorn failures remain visible |
| Lifecycle | Cancellation propagates; transaction rollback is preserved; late failures never send headers twice; failed startup never becomes ready |
| Integration | Actual selected server/driver behavior tested where changed; mocks are not proof of real adapter compatibility |

Use `TestClient(..., raise_server_exceptions=False)` to inspect unexpected 500 responses, and retain a normal propagation test for the server-error path. Capture **final rendered output through the production processors** for disclosure tests. Bare `structlog.testing.capture_logs()` disables configured processors and is not sufficient by itself; see [structlog testing][structlog-testing].

HTTP and schema fixtures require no production credentials, provider calls, or database. PostgreSQL integration tests use the development test database. Follow the repository's scaffold → behavioral red test → implementation → focused tests sequence where adding behavior. The existing test setup requires the non-production `apps/backend/.env.test`.

Regression coverage lives in:

- [HTTP unit tests](../../apps/backend/tests/unit/shared/http/): models, builders, mappings, validation, handlers, correlation, late failures, and cancellation.
- [Infrastructure unit tests](../../apps/backend/tests/unit/shared/infrastructure/): rendered diagnostic sanitization and reporting ownership.
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

When production declarations change, run `pnpm --filter @inframeld/backend openapi` before the drift check; the command writes the generated contract. The integration command requires the local Compose database, runs migrations against `.env.test`, and exercises real PostgreSQL behavior. These are commands for future verification, not an assertion that this documentation edit executed them. Manually review dependency boundaries and repository organization; do not add automated architecture/import-boundary or composition-construction tests. Test observable behavior rather than importability or inheritance alone.

Use Google-style docstrings for public exceptions, ports, use cases, HTTP models, builders, handlers, and diagnostics. Explain meaning, safe attributes, recovery implications, and relevant `Raises`; keep wire fields and OpenAPI descriptions consistent with this reference. Keep the guides, architecture, backend README, and affected skill aligned when changing the foundation. For list endpoints, separately verify the owning feature's cursor-content validation and authorization on every page.

## Source basis

The file map and operational descriptions were reconciled with application source and test files on 23 September 2026. Test results above are developer-reported. Feature examples in the practical guide remain illustrative. The links below explain the underlying framework behavior; the repository's code and behavioral tests establish its selected integration.

[rfc9457]: https://www.rfc-editor.org/rfc/rfc9457.html
[pydantic-errors]: https://docs.pydantic.dev/latest/errors/errors/
[pydantic-config]: https://docs.pydantic.dev/latest/api/config/#pydantic.config.ConfigDict.hide_input_in_errors
[starlette-errors]: https://starlette.dev/exceptions/
[structlog-api]: https://www.structlog.org/en/stable/api.html#structlog.tracebacks.ExceptionDictTransformer
[structlog-testing]: https://www.structlog.org/en/stable/testing.html
