# Error handling: maintainer reference

**Read this when changing the shared foundation—not before writing your first feature.** The [practical guide](error-handling.md) explains ordinary usage and owns the stable public problem catalogue. The existing [implementation walkthrough](error-handling-implementation.md) supplies issue 19's implementation sequence.

**Status — 22 September 2026:** requirements and proposed behavior, not implementation evidence. This reference preserves the supplied policy while moving infrastructure detail out of the onboarding path. Owners remain ADR-0002 for the public contract and ADR-0001 for dependency rules.

## Ownership and implementation scope

All paths below are relative to `apps/backend/src/inframeld_backend/`.

| Location | Responsibility | Status in the supplied documentation |
| --- | --- | --- |
| `shared/domain/errors.py` | `DomainError`, `InvalidStateTransitionError` | Planned |
| `shared/application/application_error.py` | Existing `ApplicationError`; clarify its diagnostic-only message contract | Existing base |
| `shared/application/errors.py` | Five starter application failures from the practical guide | Planned |
| `shared/http/problems.py` | `ProblemDetails`, `ValidationIssue`, frozen definitions, exact-type mapping, response builder and response declarations | Planned |
| `shared/http/validation.py` | Bounded validation translator | Planned |
| `shared/http/error_handlers.py` | One `register_error_handlers(application)` function | Planned |
| `shared/infrastructure/error_reporting.py` | Shared diagnostic owner/deduplication helper | Planned |
| Existing logging, command logging, request context, database, and `composition.py` | Connect and qualify the foundation | Changes planned |

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

A small shared reporter may mark the **exact exception instance** with a private runtime-only “already reported” attribute. Do not add it to the public exception contract, persist it, or mark unrelated causes. The outer handler reports an unreported failure with explicit request-state correlation. A narrowly scoped `uvicorn.error` filter may suppress a server traceback only for that same reported exception. Preserve unrelated messages, unreported exceptions, and startup failures. Verify this with the selected Uvicorn version, not only TestClient.

### Sanitization covers more than local variables

Replace the current default `dict_tracebacks` behavior with explicit `show_locals=False`. Structlog's exception transformer otherwise defaults to including locals; see its [API reference][structlog-api]. That change alone is insufficient.

Keep bounded exception types, file/function/line locations, and cause/context/group relationships. Exclude arbitrary exception values, notes, source snippets, and locals **at every nesting level**. Use approved structured metadata for useful descriptions. Bound extraction work as well as the final output: frame counts, traversal depth, breadth, and total visited exceptions. Handle cycles without unbounded traversal.

JSON and console renderers must consume the same sanitized diagnostic, rather than independently formatting the original exception. Standard-library integration must also clear or replace raw `exc_info` and cached exception text so a formatter cannot append an unsanitized traceback.

Review third-party free-text logging separately; sanitizing exception fields does not sanitize arbitrary log messages. Add SQLAlchemy `hide_parameters=True` as defense in depth, not as a substitute for this policy. Regex redaction cannot establish that all secrets were removed.

## Transactions and recovery

The command owns short transactions; external calls happen outside them. Exceptions must leave transaction contexts before the HTTP handler consumes them. An error handler must not commit, authorize, retry, start migrations, or resume uncertain paid work.

Translate a database constraint violation only after identifying the exact understood structured driver/constraint condition. Do not parse message text or classify all `IntegrityError` instances as user conflicts. Identify the actual driver representation in that adapter's implementation and integration tests.

Keep `CancelledError`, `KeyboardInterrupt`, and `SystemExit` propagating. Prefer context managers or `finally` for cleanup without suppressing errors. A provider timeout does not prove work had no effect; neither a 503 nor `DependencyUnavailableError` authorizes replay. Preserve ADR-0007's idempotency and uncertainty rules.

## OpenAPI and client compatibility

Each route declares its actual success model and applicable error responses. The shared response-declaration helper must reference the problem model and explicitly describe `application/problem+json`; replace the default 422 `HTTPValidationError` contract. Test that FastAPI does not also advertise an unsupported `application/json` error representation. Do not replace the OpenAPI generator to avoid checking the generated result.

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

Fixtures require no production credentials, provider calls, or database. Follow the repository's scaffold → behavioral red test → implementation → focused tests sequence where adding behavior. The existing test setup requires the non-production `apps/backend/.env.test`.

From the repository root, the supplied implementation plan lists:

```bash
pnpm --filter @inframeld/backend lint
pnpm --filter @inframeld/backend typecheck
pnpm --filter @inframeld/backend test
pnpm --filter @inframeld/backend openapi
pnpm --filter @inframeld/backend openapi:check
```

Generate the contract when production declarations change. These are instructions, not a record of checks run. Manually review dependency boundaries and repository organization; do not add automated architecture/import-boundary or composition-construction tests. Test observable behavior rather than importability or inheritance alone.

Use Google-style docstrings for public exceptions, ports, use cases, HTTP models, builders, handlers, and diagnostics. Explain meaning, safe attributes, recovery implications, and relevant `Raises`; keep wire fields and OpenAPI descriptions consistent with this reference. After qualification, update status notes in the guides, architecture, backend README, and affected skill. Issue 19 also has separate pagination acceptance criteria; error-handling work alone does not complete it.

## Source basis

This reference reorganizes the supplied maintainer rules and implementation plan; it does not claim to inspect application source or establish installed dependency versions. The practical guide's new feature snippets are marked separately. Primary framework references were checked when preparing the rewrite.

[rfc9457]: https://www.rfc-editor.org/rfc/rfc9457.html
[pydantic-errors]: https://docs.pydantic.dev/latest/errors/errors/
[pydantic-config]: https://docs.pydantic.dev/latest/api/config/#pydantic.config.ConfigDict.hide_input_in_errors
[starlette-errors]: https://starlette.dev/exceptions/
[structlog-api]: https://www.structlog.org/en/stable/api.html#structlog.tracebacks.ExceptionDictTransformer
[structlog-testing]: https://www.structlog.org/en/stable/testing.html
