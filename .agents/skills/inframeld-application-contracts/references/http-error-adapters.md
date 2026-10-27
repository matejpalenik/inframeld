# Translate and report failures at HTTP boundaries

Alice’s adapter observes a provider outage. The boundary translates only recognized failures and preserves safe diagnostics. Framework middleware, validation and late response failures need their own narrowly defined handling.

<a id="validation-translation"></a>

## Validation translation

FastAPI's `RequestValidationError` is a transport failure. The accepted initial policy uses 422, including malformed JSON. Do not infer that status from arbitrary Pydantic `ValidationError` instances.

Each issue contains:

| Field | Allowed output |
| --- | --- |
| `location` | `body`, `path`, `query`, `header`, `cookie`, or `request` |
| `path` | Tuple in Python, array in JSON. At most eight verified public field names or strict non-negative integer indices. Names are 1–64 characters. An empty path refers to the whole location. |
| `code` | Product-owned category, with the same 64-character code constraint: `required`, `invalid_type`, `out_of_range`, `too_short`, `too_long`, `unexpected_field`, or safe fallback `invalid_value` |
| `message` | Reviewed corrective wording, 1–256 characters. No submitted values |

Create new, safe issue objects. Never return or log raw `.errors()`, `.body`, `str(exc)`, submitted `input`, arbitrary `ctx`, validator messages, or library error URLs. `hide_input_in_errors=True` does not make a Pydantic response safe by itself. Recorded references: [Pydantic error data](https://docs.pydantic.dev/latest/errors/errors/) and [configuration](https://docs.pydantic.dev/latest/api/config/#pydantic.config.ConfigDict.hide_input_in_errors).

Check field paths as carefully as messages. For example, an unknown dictionary key may contain a secret, even if another part of the application uses the same word as a field name. Union tags and extra-field names can also come from the caller. Include only names verified for that position. If uncertain, stop at the last verified parent or return an empty path.

Use conservative normalization and field information owned by the endpoint. Do not build a general schema-traversal framework or rely on a list of suspicious words.

Use useful fixed descriptions: “A value is required.” or “Use a value within the permitted range.” Developer-owned constraints can support reviewed limit-specific wording. Unknown categories receive a safe fallback.

Keep the first 20 sanitized issues in validation order. Shorten paths and strings to their limits before constructing output models so error rendering cannot itself fail validation. Request bodies still need their own size limits.

<a id="response-construction-and-handler-registration"></a>

## Response construction and handler registration

During application setup, register handlers once for request validation, application errors, Starlette `HTTPException`, and unexpected `Exception`. Test apps use the same registration function. Registering Starlette's base class also covers FastAPI's subclass and native router errors.

The builder creates `ProblemDetails` explicitly, then calls `model_dump(mode="json", by_alias=True, exclude_none=True)`. Returning `JSONResponse` does not make FastAPI validate its contents against the documented model. Set `application/problem+json`, `Cache-Control: no-store`, and the generated request-ID header. Take both body and HTTP status from the same definition.

For native HTTP errors, use reviewed text for the status and a safe fallback for unfamiliar error statuses. Do not copy `exc.detail`. Preserve trusted `Allow`, `WWW-Authenticate`, and deliberately supplied `Retry-After` headers. The component producing a 401 supplies its authentication challenge.

Forwarded headers cannot replace the problem media type, generated request ID, or no-store policy. Do not forward arbitrary headers from an upstream service.

HEAD responses have no body. Success, redirects, and statuses that forbid content must not receive a problem body. Supported configurations use `debug=False` because Starlette debug mode bypasses the safe 500 handler.

Middleware may reject a request before it reaches the routing handlers. Such middleware must build a safe response at its own boundary. See [Starlette's exception handling](https://starlette.dev/exceptions/).

<a id="openapi-and-client-compatibility"></a>

## OpenAPI and client compatibility

Each route declares its success model and applicable errors using `problem_responses(definition)`. Routes with input validation declare `VALIDATION_ERROR_PROBLEM` instead of the default 422 `HTTPValidationError`. Registering handlers does not supply those declarations. The production `/health` route currently declares unexpected 500. Test-only routes exercise JSON and multipart validation.

The installed FastAPI version places additional response models under the route's default media type. To describe problem responses correctly, `problem_responses()` adds the model and a private `x-inframeld-problem-response` marker.

Application setup calls `configure_problem_openapi()` once. It wraps the original bound `application.openapi` method, keeping native component generation and caching. For a marked response, it moves the sole representation to `application/problem+json` and removes the marker. Success and unmarked responses stay unchanged. Multiple representations on a marked response cause an error rather than silently losing one.

Keep this adjustment limited to declared problem responses. Do not create another schema generator or change the OpenAPI dialect. When upgrading FastAPI, rerun contract tests and check whether the adjustment is still needed. Verify component references and that error responses do not advertise unsupported `application/json`.

The runtime response and schema must agree on aliases, required and nullable fields, limits, and omitted optional fields. A model may be absent from the committed production schema until a production response uses it. Never mount test fixture routes in the product or export them in its schema.

Use the existing OpenAPI 3.1.x exporter and drift check. Do not hand-edit `contracts/openapi/v1/inframeld-v1.json`, add another exporter, down-convert the schema, or implement a custom generator here. Clients need fallbacks for unfamiliar problem types and upstream responses in other formats. HTTP status alone does not define a shared retry policy.
