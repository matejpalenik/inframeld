# Implementing the error-handling foundation

**Audience:** The developer implementing issue 19 by hand.  
**Prerequisite:** Read the accepted [maintainer rules and error reference](error-handling.md).  
**Status:** Instructions and proposed code, not an implementation report. No application code is created by this document.

Work through the stages in order. The first two stages supply complete starter definitions and a scaffold/test/implementation cycle. Later stages specify the exact responsibilities and behavioral checkpoints for each increment. This lets the developer implement and review the system in manageable pieces instead of installing an unverified block of infrastructure.

All application paths are relative to the repository root. Code marked **complete new file** can be copied into the named file. Code marked **replacement** replaces only the stated file or class block. Do not apply both the scaffold and finished model simultaneously: they are successive versions of one file.

## Implementation map

| Stage | Files the developer will create or change | Result |
| --- | --- | --- |
| 1. Exception vocabulary | `apps/backend/src/inframeld_backend/shared/domain/errors.py`; `shared/application/application_error.py`; `shared/application/errors.py`; existing infrastructure exception docstrings | Ordinary Python failures with clear ownership and no HTTP dependencies. |
| 2. Response models | `apps/backend/src/inframeld_backend/shared/http/problems.py`; `apps/backend/tests/unit/shared/http/test_problems.py` | Typed RFC output, aliases, bounds, field descriptions, and class documentation. |
| 3. Definitions and response builder | Extend `shared/http/problems.py` and its tests | Stable definitions, explicit mappings, safe output, and matching status/headers. |
| 4. Validation translation | `apps/backend/src/inframeld_backend/shared/http/validation.py`; `apps/backend/tests/unit/shared/http/test_validation.py` | Useful bounded validation issues without reflected sensitive data. |
| 5. Handlers | `apps/backend/src/inframeld_backend/shared/http/error_handlers.py`; `apps/backend/tests/unit/shared/http/test_error_handlers.py`; `composition.py` | Normalized HTTP failures, including unexpected errors and correlation. |
| 6. Diagnostics | Existing `shared/infrastructure/logging.py`, `shared/infrastructure/command_logging.py`, `shared/http/request_context.py`; new `shared/infrastructure/error_reporting.py`; focused logging tests | Safe structured diagnostics with one reporting owner. |
| 7. OpenAPI and qualification | Existing `apps/backend/tests/unit/contract/test_openapi_contract.py`; HTTP response declarations; generated contract if those declarations change | Runtime/schema parity and regression evidence. |

In rows using a short `shared/...` or `composition.py` path, the prefix is `apps/backend/src/inframeld_backend/`. None of these proposed code/test files is created by the documentation change.

Use the repository's TDD sequence for new behavior: establish only the necessary names/signatures, write the behavioral test, verify the intended failure, implement the behavior, run the focused test and relevant suite. The first stage establishes exception symbols; it does not require tests that merely check class inheritance or imports.

## 1. Establish the exception vocabulary

These definitions establish the names and metadata later behavioral tests need. They do not implement business rules, authorization, retry behavior, or HTTP translation.

### Domain exceptions

**Complete new file:** `apps/backend/src/inframeld_backend/shared/domain/errors.py`.

```python
"""Define business-neutral exception bases for deliberate domain rejections.

Feature-specific rules and exception classes stay in the owning domain. These
classes have no transport, persistence, logging, or request-context dependency.
"""

from typing import ClassVar


class DomainError(Exception):
    """Describe a deliberate rejection by a domain rule.

    This base does not imply any HTTP status or public response. The calling
    use case determines whether the rejection is an expected outcome for its
    caller or evidence of an internal inconsistency.

    Attributes:
        code: Stable diagnostic category. It is not an HTTP problem definition.
        message: Developer-authored explanation. It must not include secrets,
            source content, or untrusted input and is not automatically public.
    """

    code: ClassVar[str] = "domain_error"

    def __init__(self, message: str) -> None:
        """Initialize the failure without logging or serializing it.

        Args:
            message: Controlled explanation for the domain caller. Transport
                adapters select public wording separately.
        """
        self.message = message
        super().__init__(message)


class InvalidStateTransitionError(DomainError):
    """Reject an action that the current domain state does not permit.

    The constructor and message rules are inherited from DomainError. A use
    case may translate a supported caller-initiated rejection into a conflict.
    Do not globally map this class to a client status: an invalid transition
    during internal reconstruction can indicate a defect instead.

    Define a more specific exception in the owning domain when the distinction
    matters to its callers. Do not use this class for empty query results,
    missing infrastructure, malformed HTTP bodies, or programming assertions.
    """

    code: ClassVar[str] = "invalid_state_transition"
```

### Existing application base

**Replace the complete contents of:** `apps/backend/src/inframeld_backend/shared/application/application_error.py`.

This preserves the existing constructor, `code`, `message`, and `Exception.args` behavior. The documentation changes the interpretation of `message`: safety for a public response is established by the transport mapper, not by this constructor.

```python
"""Define the transport-neutral base for application operation failures."""

from typing import ClassVar


class ApplicationError(Exception):
    """Describe a failure expressed by an application operation or port.

    A supported concrete failure can be translated into an HTTP problem, an
    MCP outcome, or a worker failure without importing those technologies here.
    The base itself has no public mapping. An unrecognized subclass must not
    automatically become a client error or expose its message.

    Attributes:
        code: Stable semantic category for supported callers and diagnostics.
            The HTTP adapter explicitly associates it with a public problem.
        message: Developer-authored diagnostic explanation. Never include
            credentials, source content, or raw external responses. This text
            is not automatically safe for public responses or operational logs.
    """

    code: ClassVar[str] = "application_error"

    def __init__(self, message: str) -> None:
        """Initialize an application failure without transport side effects.

        Args:
            message: Controlled diagnostic explanation. Public descriptions
                come from the transport adapter's reviewed problem definitions.
        """
        self.message = message
        super().__init__(message)
```

### Application categories

**Complete new file:** `apps/backend/src/inframeld_backend/shared/application/errors.py`.

```python
"""Provide the small initial vocabulary for application failures.

Each class inherits ApplicationError's message constructor. Codes describe
meaning; the HTTP adapter owns status codes, problem URIs, and public text.
Feature-specific failures belong in the owning application's package.
"""

from typing import ClassVar

from inframeld_backend.shared.application.application_error import ApplicationError


class InvalidInputError(ApplicationError):
    """Reject an application argument that violates a use-case precondition.

    Use after transport parsing when the application can identify a supported
    input rejection. Do not wrap arbitrary ValueError or model-construction
    failures: those may be defects. No raw input is stored on this exception.
    """

    code: ClassVar[str] = "invalid_input"


class ResourceNotFoundError(ApplicationError):
    """Report a requested resource unavailable to the operation.

    The owning use case performs scope and permission checks and decides
    whether existence must be concealed. This class makes no such decision
    and must not disclose resource contents or another tenant's identity.
    """

    code: ClassVar[str] = "resource_not_found"


class AccessDeniedError(ApplicationError):
    """Report that an authorization decision denied the operation.

    Raise only after the owning access behavior has made that decision. The
    exception does not authenticate a caller, inspect credentials, or grant
    rights. Missing authentication has its own transport challenge semantics.
    """

    code: ClassVar[str] = "access_denied"


class ConflictError(ApplicationError):
    """Reject an operation that conflicts with current application state.

    Use for an explicitly understood state conflict. A caller may need to
    inspect current state and make a new decision; repeating the same command
    is not necessarily useful or safe. Specific recovery contracts can add
    narrower exceptions in their owning application package.
    """

    code: ClassVar[str] = "conflict"


class DependencyUnavailableError(ApplicationError):
    """Report a known availability failure of a required dependency.

    An infrastructure adapter raises this application-owned failure after
    identifying a specific external availability failure. Preserve the cause
    for controlled diagnostics. Do not use it for arbitrary provider errors,
    unsupported configuration, invalid credentials, or programming defects.

    This exception does not establish whether external work completed and
    never authorizes automatic retries or another paid request.
    """

    code: ClassVar[str] = "dependency_unavailable"
```

### Existing infrastructure exceptions

Retain the existing exception types and their lifecycle. Their callers already supply diagnostic messages. Do not introduce a new infrastructure hierarchy or change exception chaining in this documentation-only stage.

**Replace only the two named class definitions**, before `class Database`, in `apps/backend/src/inframeld_backend/shared/infrastructure/database.py`. No imports change; `RuntimeError` is built in. The rest of the file remains as it is.

```python
class DatabaseStartupError(RuntimeError):
    """Report failure to establish the database startup prerequisite.

    Raised by database lifecycle code before the API is ready to serve. An
    operator must inspect safe startup diagnostics. This is not an application
    request rejection and has no direct HTTP problem mapping. Its diagnostic
    text may describe internal configuration and must not be sent to clients.
    """


class DatabaseSchemaCompatibilityError(DatabaseStartupError):
    """Report a missing or unsupported database schema at startup.

    Requires the operator-controlled migration or compatibility procedure.
    Catching this exception must not run migrations automatically or allow the
    API to serve against an incompatible schema. Constructor behavior remains
    inherited from RuntimeError.
    """
```

**Replace only `class MigrationLockError`**, before `migration_lock`, in `apps/backend/src/inframeld_backend/shared/infrastructure/migrations.py`. No imports or other code change.

```python
class MigrationLockError(RuntimeError):
    """Report that a migration could not obtain its coordination lock.

    Raised by migration infrastructure when its bounded lock-acquisition wait
    fails. The operator can investigate the active migration before retrying.
    Never proceed without the lock. This operational failure has no direct
    HTTP mapping and retains RuntimeError's constructor behavior.
    """
```

The HTTP layer already has `RequestValidationError` and Starlette `HTTPException`. Use those framework types in handlers; the typed error response is introduced next. There is no need for a duplicate `HttpError` base.

## 2. Build the typed problem models with a red/green cycle

### 2a. Establish only the model symbols

**Complete new scaffold file:** `apps/backend/src/inframeld_backend/shared/http/problems.py`.

This temporary version deliberately lacks aliases, bounds, and extra-field restrictions. It establishes imports and construction only. Replace it with the finished model after observing the behavioral failures.

```python
"""Scaffold the HTTP problem model API before its behavior is implemented."""

from uuid import UUID

from pydantic import BaseModel


class ValidationIssue(BaseModel):
    """Provide the initial validation-issue test seam."""

    location: str
    path: tuple[str | int, ...]
    code: str
    message: str


class ProblemDetails(BaseModel):
    """Provide the initial problem-response test seam."""

    type: str
    title: str
    status: int
    detail: str
    code: str
    request_id: UUID
    errors: tuple[ValidationIssue, ...] | None = None
```

### 2b. Write observable serialization tests

**Complete new test file:** `apps/backend/tests/unit/shared/http/test_problems.py`.

```python
"""Verify the public problem representation and its output bounds."""

import pytest
from pydantic import ValidationError

from inframeld_backend.shared.http.problems import ProblemDetails

REQUEST_ID = "c66a2044-4e4f-4c07-983e-a3c221c7b1ad"
TYPE_PREFIX = (
    "https://github.com/matejpalenik/inframeld/blob/main/"
    "docs/development/error-handling.md"
)


def _payload() -> dict[str, object]:
    """Return synthetic server-owned data for the initial validation problem."""
    return {
        "type": f"{TYPE_PREFIX}#validation-error",
        "title": "Request validation failed",
        "status": 422,
        "detail": "One or more request fields are invalid.",
        "code": "validation_error",
        "request_id": REQUEST_ID,
        "errors": [
            {
                "location": "query",
                "path": ["limit"],
                "code": "out_of_range",
                "message": "Use a value within the permitted range.",
            }
        ],
    }


def test_serializes_public_request_id_and_issue_path() -> None:
    """Emit camel-case wire names, a UUID string, and JSON array paths."""
    problem = ProblemDetails.model_validate(_payload())

    result = problem.model_dump(mode="json", by_alias=True, exclude_none=True)

    assert result == {
        "type": f"{TYPE_PREFIX}#validation-error",
        "title": "Request validation failed",
        "status": 422,
        "detail": "One or more request fields are invalid.",
        "code": "validation_error",
        "requestId": REQUEST_ID,
        "errors": [
            {
                "location": "query",
                "path": ["limit"],
                "code": "out_of_range",
                "message": "Use a value within the permitted range.",
            }
        ],
    }


def test_rejects_undeclared_response_fields() -> None:
    """Reject accidental metadata that has no reviewed public contract."""
    payload = _payload()
    payload["providerKey"] = "synthetic-test-only"

    with pytest.raises(ValidationError):
        ProblemDetails.model_validate(payload)


def test_rejects_more_than_twenty_validation_issues() -> None:
    """Enforce the model's bound; the translator will truncate before this."""
    payload = _payload()
    payload["errors"] = [
        {
            "location": "body",
            "path": [],
            "code": "invalid_value",
            "message": "A supplied value is invalid.",
        }
        for _ in range(21)
    ]

    with pytest.raises(ValidationError):
        ProblemDetails.model_validate(payload)
```

From the repository root, run the focused file:

```bash
uv run --project apps/backend pytest apps/backend/tests/unit/shared/http/test_problems.py -q
```

The scaffold should fail these assertions because the public alias and restrictions are missing. An import/collection failure is not the intended red result. The repository's `conftest.py` requires `apps/backend/.env.test`; use the existing non-production test configuration. These tests need no running database and must not run migrations.

### 2c. Implement the model behavior

**Replace the complete scaffold in:** `apps/backend/src/inframeld_backend/shared/http/problems.py`.

This is the initial finished model section. Stage 3 will add problem definitions and response construction below these classes. The model validates representation; it does not decide which exception is public or sanitize raw request data.

```python
"""Define the bounded RFC 9457 representation used by the HTTP adapter.

The HTTP layer constructs these models only from reviewed definitions and
sanitized issue data. Domain/application code must not import this module.
See docs/development/error-handling.md for stable problem identities and
disclosure rules.
"""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import AnyUrl, BaseModel, ConfigDict, Field, UrlConstraints

MAX_VALIDATION_ISSUES = 20
MAX_VALIDATION_PATH_SEGMENTS = 8

ProblemType = Annotated[AnyUrl, UrlConstraints(max_length=2048)]
FieldName = Annotated[str, Field(min_length=1, max_length=64)]
ArrayIndex = Annotated[int, Field(ge=0, strict=True)]
IssueLocation = Literal["body", "path", "query", "header", "cookie", "request"]
ErrorCode = Annotated[
    str,
    Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$"),
]


class ValidationIssue(BaseModel):
    """Describe one sanitized issue in an incoming request.

    Attributes:
        location: Request component containing the issue.
        path: Verified public field names or array indices, relative to that
            component. An empty path identifies the component as a whole.
        code: Product-owned validation category, independent of library names.
        message: Reviewed corrective description without submitted values.

    This model checks the output shape, not whether a string contains a secret.
    The validation translator must sanitize locations and messages first.
    """

    model_config = ConfigDict(extra="forbid")

    location: IssueLocation = Field(description="Request component containing the issue.")
    path: tuple[FieldName | ArrayIndex, ...] = Field(
        max_length=MAX_VALIDATION_PATH_SEGMENTS,
        description="Verified public fields and indices relative to the request component.",
    )
    code: ErrorCode = Field(description="Stable Inframeld validation category.")
    message: str = Field(
        min_length=1,
        max_length=256,
        description="Safe corrective description without submitted values.",
    )


class ProblemDetails(BaseModel):
    """Represent an Inframeld HTTP error using RFC 9457 Problem Details.

    Wire field reference:

    | Field | Meaning | Inframeld rule |
    | --- | --- | --- |
    | type | Primary URI identifying the problem kind. | Stable definition URI. |
    | title | Human-readable summary of that kind. | Fixed per problem type. |
    | status | Status for this occurrence. | Same as the HTTP response status. |
    | detail | Corrective explanation. | Reviewed text, never arbitrary exception text. |
    | instance | Optional RFC occurrence URI. | Omitted from this initial profile. |
    | code | Short Inframeld problem identifier. | Paired with the problem type. |
    | requestId | Server-generated request UUID. | Same value as X-Request-ID. |
    | errors | Individual validation issues. | Present only for request validation. |

    Attributes:
        type: Absolute problem URI; about:blank is used for generic HTTP errors.
        title: Short public summary without occurrence-specific internal data.
        status: Error status in the range 400 through 599.
        detail: Safe public explanation selected by the HTTP adapter.
        code: Stable public code; clients must tolerate unfamiliar future codes.
        request_id: Correlation UUID serialized as requestId, never authorization.
        errors: Optional bounded collection of already sanitized request issues.

    The response builder enforces the selected definition's type/code/status
    pairing and whether errors is appropriate. This model does not map Python
    exceptions, authenticate callers, authorize retries, or render tracebacks.
    Server-side extra fields are rejected; client parsers must still tolerate
    future RFC extension members.
    """

    model_config = ConfigDict(
        extra="forbid",
        validate_by_name=True,
        serialize_by_alias=True,
    )

    type: ProblemType = Field(description="Primary RFC 9457 problem-type URI.")
    title: str = Field(
        min_length=1,
        max_length=128,
        description="Stable human-readable summary of the problem type.",
    )
    status: int = Field(
        ge=400,
        le=599,
        strict=True,
        description="HTTP error status, equal to the actual response status.",
    )
    detail: str = Field(
        min_length=1,
        max_length=512,
        description="Reviewed explanation without internal or submitted sensitive values.",
    )
    code: ErrorCode = Field(description="Stable Inframeld code paired with the problem type.")
    request_id: UUID = Field(
        alias="requestId",
        description="Server request identifier, also returned in X-Request-ID.",
    )
    errors: tuple[ValidationIssue, ...] | None = Field(
        default=None,
        max_length=MAX_VALIDATION_ISSUES,
        description="At most 20 sanitized issues; the list may be incomplete.",
    )
```

Rerun the same focused tests. Then add behavioral coverage for URI validity, status bounds, negative indices, issue/path/string bounds, and omission of `errors` on a non-validation problem. Exercise the JSON Schema as part of stage 7; do not add tests for module placement or import graphs.

## 3. Add definitions, mapping, and one response builder

Continue in `apps/backend/src/inframeld_backend/shared/http/problems.py`; extend `apps/backend/tests/unit/shared/http/test_problems.py`.

1. Add a small frozen `ProblemDefinition` dataclass containing `type_uri`, `code`, `title`, `status`, and `detail`. Keep these values together. Add one constant for each named problem in the reference; use its exact documented identity and wording. This is HTTP metadata, not a base exception.
2. Add an explicit lookup from each supported concrete application exception class to its definition. Use exact registered types initially. An unknown subclass follows the internal-error policy until deliberately registered. Do not use a global mutable decorator registry or derive mappings from names.
3. Establish the response builder's signature before testing it. It receives a request, definition, optional already-sanitized issues, and trusted protocol headers. It returns the HTTP response. It must not accept arbitrary exception objects or arbitrary public `detail` text.
4. Write a failing test asserting status, content type, body, request-ID header, and `no-store` against a synthetic request. Implement explicit `ProblemDetails` construction followed by JSON serialization with aliases and omitted `None` values. Use the same definition for HTTP and body status.
5. Obtain or initialize the request UUID in request state. Headers supplied by an HTTP adapter must not override the generated request ID, problem media type, or error cache policy. Preserve legitimate authentication and method headers.
6. Require issues for the validation definition and reject/omit inappropriate issues for other definitions. Respect HEAD's no-body semantics. This builder is for error statuses only.
7. Test that a diagnostic message containing a synthetic secret never appears in a mapped application's response. The definition supplies safe public wording instead.

Document public functions with `Args`, `Returns`, and relevant `Raises`, including whether they accept pre-sanitized values. The builder is a small function; no custom response framework is needed.

## 4. Translate validation failures

**New implementation file:** `apps/backend/src/inframeld_backend/shared/http/validation.py`.  
**New behavioral tests:** `apps/backend/tests/unit/shared/http/test_validation.py`.

Establish a translator returning `tuple[ValidationIssue, ...]` and a small safe category/location normalizer. Its input can be the request-validation exception's structured errors, but it must build a new output from approved fields. Do not return those dictionaries unchanged.

Implement one test category at a time:

| Test input | Required observable output |
| --- | --- |
| Missing known field | `required`, a safe field location when verified, and a useful message. |
| Wrong type or out-of-range number | Appropriate product-owned category; no original input. |
| Unknown Pydantic category/custom validator | Fixed safe fallback; no original validator message or context. |
| Invalid JSON | Request/body-level issue with fixed safe wording. |
| Submitted secret in a dictionary key or extra field name | No reflection of the key; fall back to the verified parent/request location. |
| More than 20 failures/deep locations | Bounded output without raising a second error. |
| Nested list or aliased public field | Preserve a verified public alias/index where available. |

Do not introspect every possible Pydantic schema construct to reconstruct paths. Start conservatively: unknown path components collapse to the known parent. A declared list of safe public fields or endpoint-owned path information can improve precision where useful. Test the chosen approach through real request validation so it does not silently trust user-owned keys.

The bounds and category mapping belong to this HTTP contract; domain exceptions must not depend on them.

## 5. Register handlers and exercise real HTTP responses

**New implementation file:** `apps/backend/src/inframeld_backend/shared/http/error_handlers.py`.  
**New behavioral tests:** `apps/backend/tests/unit/shared/http/test_error_handlers.py`.  
**Existing composition change:** `apps/backend/src/inframeld_backend/composition.py`.

Establish a `register_error_handlers(application: FastAPI) -> None` function. The initial scaffold may do nothing so tests collect. Tests build a bare FastAPI fixture app, install the real request middleware and handler registration function, and define synthetic routes only in that fixture.

Register async handlers for:

| Exception | Behavior |
| --- | --- |
| `RequestValidationError` | Sanitized validation issues and the named 422 definition. |
| `ApplicationError` | Lookup by supported concrete type; known definition or safe unexpected-failure policy. |
| Starlette `HTTPException` | Generic `about:blank` problem with fixed safe text and required trusted headers. |
| `Exception` | Safe internal-error response; diagnostic reporting coordinated with stage 6. |

Test a supported application error, an unknown application subclass, a bare domain error, an unexpected runtime error, an invalid response model, invalid input, route 404, method 405, and a synthetic 401 with its explicit challenge. Preserve `Allow`; test HEAD separately. Do not infer user/client error status from generic Python exception classes.

For the unexpected response test, configure `TestClient` with `raise_server_exceptions=False` so the test inspects the actual 500 response. Also keep a propagation test using the normal behavior: returning a safe response must not swallow the original exception from the ASGI server/test harness.

The 500 handler must read request state for correlation and use the shared response builder. Test it with the real middleware arrangement; a bare handler unit test will miss the unwind/header issue.

After the fixture tests pass, call the registration function from `create_app`, after constructing the FastAPI instance. Preserve the database lifespan and health route. Configure safe production behavior with `debug=False`. Do not register the fixture routes in `create_app`, even with `include_in_schema=False`.

## 6. Correct diagnostics, redaction, and duplicate reports

This is part of the foundation's behavior, not an optional cleanup after its HTTP tests pass.

### 6a. Sanitized rendering

**Modify:** `apps/backend/src/inframeld_backend/shared/infrastructure/logging.py`.  
**New tests:** `apps/backend/tests/unit/shared/infrastructure/test_error_logging.py`.

First reproduce the observed leakage using synthetic secrets in locals, exception messages, notes, causes, and exception groups. Capture the actual final JSON or console output using the real configured processors. Do not load real secrets or call providers.

Replace default `dict_tracebacks` with an explicit transformer using `show_locals=False`. Construct a bounded safe diagnostic containing exception types, file/function/line locations, and cause/group relationships. Exclude raw messages, notes, source snippets, and locals throughout the nested structure. Bound both frames and nested/group breadth/depth; bounds applied only after traversing an enormous group do not bound extraction work. Use a small traversal with explicit budgets where the default transformer cannot meet this requirement.

Both output formats must consume this safe diagnostic. Do not allow the console renderer to format the original exception a second time. Verify standard-library log records too, including removal of raw `exc_info` and cached exception text after safe transformation. Retain the existing `ProcessorFormatter` bridge and JSON stdout output.

Developer experience comes from stack locations, exception types, stable event names, and explicit safe context. Do not rely on unrestricted exception strings to make a diagnostic useful.

### 6b. Reporting ownership

**New helper file:** `apps/backend/src/inframeld_backend/shared/infrastructure/error_reporting.py`.  
**Modify:** `apps/backend/src/inframeld_backend/shared/infrastructure/command_logging.py`, `apps/backend/src/inframeld_backend/shared/http/request_context.py`, and the error handlers.

Write failing tests for the real nested path: a fixture route enters the command scope and raises. The result must contain a command outcome and one request diagnostic, not two tracebacks.

Use a small reporting helper that logs approved fields with the sanitized traceback and marks the exact reported exception instance. The command scope records its outcome/code and operation ID without duplicating that traceback. The request boundary owns unexpected diagnostics. Known handled dependency failures can use the same helper from their handler. An unmapped application failure also needs unexpected diagnostics even though an application handler caught it.

If an outer 500 handler receives an error not yet reported by the request middleware, it reports it with explicit correlation fields from request state. A previously reported error is rendered without a second diagnostic. Do not make the domain exception constructor perform reporting or store request context.

For Uvicorn's re-raised exception record, add a narrowly scoped filter to `uvicorn.error` that ignores only the exact exception marked as already reported. Keep all unreported failures and other server logs. Test the selected server path before claiming one diagnostic per request; an in-process TestClient alone never exercises Uvicorn's protocol logger.

### 6c. Lifetime and operational checks

- Keep request context scoped and cleared. Verify isolated IDs under concurrent requests and mixed synchronous/asynchronous dependencies.
- Replace raw path logging with the matched route template where available; unmatched input must not become arbitrary URL text in logs.
- Record failures after response start without inventing a new 500 response or sending headers twice. Propagate cancellation without manufacturing an application failure response.
- Keep command operation metadata in its outcome record before its context exits. The request ID connects it to the diagnostic.
- In `apps/backend/src/inframeld_backend/shared/infrastructure/database.py`, add engine parameter hiding as defense in depth when implementing this step. Test rendering with synthetic SQL errors; parameter hiding alone does not make all driver text safe.
- Startup/migration failures use safe operator diagnostics. No HTTP handler catches a lifespan failure and turns startup into a successful ready state.

These checks need no real model calls. Only claim database/driver integration behavior after its owning real integration tests are run; this issue's sanitizer tests can use synthetic errors.

## 7. Declare the contract and qualify the whole path

Extend `apps/backend/tests/unit/contract/test_openapi_contract.py` using a test-only app that references the actual problem models and response definitions. Preserve issue 18's native schema and multipart tests.

1. Add a helper for shared error response declarations beside the HTTP problem definitions. Its output must describe `application/problem+json` explicitly and reference the Pydantic component. Verify that FastAPI does not accidentally also advertise an unsupported `application/json` error body for that definition. Prefer ordinary response metadata; do not replace the OpenAPI generator.
2. Declare the custom 422 schema on routes that validate inputs. Exception-handler registration does not replace FastAPI's default validation schema by itself.
3. Test that fixture runtime responses match declared statuses, media types, aliases, and required/nullable fields. Inspect the reusable `ProblemDetails` and `ValidationIssue` components and their field descriptions.
4. Document only applicable statuses on real routes. For example, the health route may document its generic unexpected 500; it does not need every application failure merely to include all types in the generated artifact.
5. Verify fixture-only paths never appear in the production schema. Do not expose test endpoints to demonstrate error behavior.
6. Run the focused HTTP/logging/contract tests, relevant existing unit suite, lint, and strict type checking. Check integration tests only where a real integration behavior was changed.

From the repository root, the existing check commands include:

```bash
pnpm --filter @inframeld/backend lint
pnpm --filter @inframeld/backend typecheck
pnpm --filter @inframeld/backend test
pnpm --filter @inframeld/backend openapi
pnpm --filter @inframeld/backend openapi:check
```

The `openapi` command writes the generated artifact and is an action for the implementing developer. Use it when the production declarations change. Never edit `contracts/openapi/v1/inframeld-v1.json` manually. These commands are instructions, not a record of checks executed by the documentation author.

When qualification passes, update the implementation-status notes in this document, the maintainer reference, architecture guide, backend README, and affected skill. Keep the RFC decision accepted regardless of implementation progress. Do not mark issue 19 complete until its separate pagination acceptance criteria also pass.

## Completion boundary

The error foundation is ready for subsequent feature work when a developer can raise an appropriate ordinary application exception, declare the relevant shared problem response, and obtain safe correlated output with behavioral test evidence. New features still own the meaning of new failures, authorization, transaction semantics, and whether recovery is safe. Those decisions cannot be inferred by a shared error library.

The [qualification checklist](error-handling.md#qualification-checklist) is the final behavioral checklist. It deliberately excludes automated tests of package layout, dependency rules, and composition construction, following `AGENTS.md`.
