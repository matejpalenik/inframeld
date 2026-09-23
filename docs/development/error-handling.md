# Error handling: a practical guide

**For:** engineers adding an Inframeld backend feature.  
**Status — 22 September 2026:** this is the accepted design, not a report of completed implementation. The supplied implementation plan says `ApplicationError` exists; the shared errors, HTTP handlers, response models, and safe diagnostic changes still belong to issue 19. Check that foundation before relying on these examples.

Read this guide for everyday feature work. Use the [maintainer reference](error-handling-reference.md) when changing the shared machinery, and the existing [implementation walkthrough](error-handling-implementation.md) when building it.

Examples below are new teaching examples based on the supplied architecture. Feature method names and local variables are illustrative; they are not claims about existing repository symbols. Code labelled **excerpt** belongs inside the corresponding function. They show error handling, not complete authorization, persistence, or retry implementations.

## 1. The rule to remember

**Raise where you understand the failure. Catch only to recover deliberately or translate its meaning. Otherwise, let it propagate.**

In Python, “try/catch” is written `try/except`. An exception automatically travels back through callers until an appropriate handler catches it. You do not need to catch it in every function. See [Python exception handling][python-errors].

```text
A provider rejects a call as unavailable
    → Its adapter raises DependencyUnavailableError, preserving the cause
    → The application use case lets that exception pass through
    → The route lets that exception pass through
    → The shared HTTP handler returns one safe 503 problem
```

The HTTP handler **builds a response**. It does not raise another wrapper exception.

Avoid chains such as `ProviderError → RepositoryError → ServiceError → ControllerError` when each wrapper only means “something failed.” A new name is useful only when it tells a caller something different.

## 2. Which error should I use?

These shared application exceptions belong in `shared/application/errors.py`. Their base remains in `shared/application/application_error.py`.

| Situation | Raise | Shared HTTP mapping |
| --- | --- | --- |
| Parsed input is invalid for this operation | `InvalidInputError` | 422 |
| A requested resource is unavailable within the caller's permitted scope | `ResourceNotFoundError` | 404 |
| An authorization check has denied an operation | `AccessDeniedError` | 403 |
| Current state prevents the requested operation | `ConflictError` | 409 |
| An adapter has identified a required dependency's availability failure | `DependencyUnavailableError` | 503 |
| A bug or an unclassified failure occurs | Let the original exception propagate | Safe 500 |

The statuses belong to the **HTTP mapper**, not to these Python classes. The same application code must also work for MCP and workers.

**Do not raise an error for a valid alternative outcome.** An empty document list is a list result. Insufficient evidence is an explicit query result, not an infrastructure failure. Conversely, a required search shard failing is not “no evidence”: the operation failed.

FastAPI handles malformed request fields through `RequestValidationError`; do not manufacture one in business code. An internal Pydantic validation failure is not automatically the caller's mistake.

Authentication is separate from permission checks. `AccessDeniedError` does not verify credentials. A missing or invalid incoming credential belongs to the authentication adapter; an upstream provider rejecting its own credential is not automatically an HTTP 401 to our caller.

## 3. Everyday examples

### A. Reject a missing resource without a try block

**Application use-case excerpt:** `find_visible` represents a read that enforces the verified actor's project and document scope.

```python
from inframeld_backend.shared.application.errors import ResourceNotFoundError

# Inside the read use case; actor comes from verified authentication.
document = await documents.find_visible(actor, project_id, document_id)

if document is None:
    raise ResourceNotFoundError("Document unavailable to this operation.")

return document
```

There is nothing to catch here. A failed database read must not become `None`; that would incorrectly turn an outage into a 404.

The error does not perform authorization. The owning feature decides when to conceal existence, so the response cannot reveal another tenant's document.

### B. Translate a domain rejection only at the operation that understands it

Domain errors live in the owning domain package. Shared bases are in `shared/domain/errors.py`. They do not inherit from `ApplicationError` or import FastAPI.

**Domain method excerpt:** a rollback cannot proceed while a candidate is attached.

```python
from inframeld_backend.shared.domain.errors import InvalidStateTransitionError

# Inside the deployment's rollback method.
if self.candidate is not None:
    raise InvalidStateTransitionError("Rollback requires no active candidate.")
```

**Application use-case excerpt:** this particular rejection means the caller requested an operation that conflicts with current state.

```python
from inframeld_backend.shared.application.errors import ConflictError
from inframeld_backend.shared.domain.errors import InvalidStateTransitionError

# Inside the authorized command's short transaction.
# The full command also checks idempotency, expected revision,
# previous-version availability, and the other release rules.
try:
    deployment.rollback()
except InvalidStateTransitionError as exc:
    raise ConflictError("Requested rollback is not allowed.") from exc

# Deliberately outside the try: a persistence failure is not this rejection.
await deployments.save(deployment)
```

`from exc` retains the original cause for controlled diagnostics. It does not put the cause into the HTTP response.

Do not put loading, rollback, and saving inside the same catch. An invalid domain state discovered while loading persisted data may indicate corruption or a bug. **There is no global `DomainError → 409` rule.**

A feature can also explicitly expose and map a particular domain error as part of its use-case contract. Do not add an application wrapper merely to satisfy a layer diagram.

### C. Translate a known provider failure in its adapter

All model calls remain inside ModelGateway. The following is an **excerpt from its non-streaming LiteLLM adapter**, after admission, credential, destination, budget, and retry-policy checks. `approved_call_options` stands for options prepared by that gateway.

```python
import litellm

from inframeld_backend.shared.application.errors import DependencyUnavailableError

try:
    provider_response = await litellm.acompletion(**approved_call_options)
except litellm.ServiceUnavailableError as exc:
    raise DependencyUnavailableError("Model provider unavailable.") from exc

# Validate and translate provider output after the protected call.
# An invalid response is not automatically an availability failure.
```

LiteLLM documents this availability exception, but mappings vary by provider. Test the exception actually emitted by the selected provider/version; this is one supported branch, not a complete adapter. See [LiteLLM's mapping reference][litellm-errors].

Do not replace that catch with `except Exception`. Invalid configuration, rejected credentials, provider policy rejections, timeouts, and programming mistakes need their own understood handling. Even a broadly named SDK connection error may be a fallback category rather than proof of an outage.

This branch makes **no retry decision**. A lost model response can leave paid work uncertain. Preserve the original operation and use its recovery rules; never add a retry, another provider, or a fallback answer here.

### D. Let the route stay simple

**HTTP route-body excerpt:** authentication, dependency injection, request models, and response declarations are configured around this body.

```python
result = await use_case.execute(command)
return result
```

Do not add a route-level `try/except` just to return a 404 or 409. The shared handlers already own that conversion.

## 4. When should I create a new exception?

**Reuse an existing class unless someone needs to distinguish the new failure.** A separate `DocumentNotFoundError`, `CollectionNotFoundError`, and `PipelineNotFoundError` is unnecessary when all require identical handling.

A deployment revision conflict is a useful distinction: the client must reload current state and ask for a new decision, not silently retry against the newer revision.

**Proposed feature example — not an additional accepted starter type:** place this in the Releases application package.

```python
from typing import ClassVar

from inframeld_backend.shared.application.errors import ConflictError


class DeploymentRevisionConflictError(ConflictError):
    """Reject an update whose expected deployment revision is stale.

    Raise after the authorized update detects a revision mismatch.
    The caller must reload state and make a new decision before retrying.
    Do not use for every failed write or database constraint violation.

    Inherits ConflictError's diagnostic-only message constructor.
    The code identifies the failure; HTTP metadata is defined separately.
    """

    code: ClassVar[str] = "deployment_revision_conflict"
```

**Application use-case excerpt:** assume the authorized deployment has been loaded under an appropriate database lock held through the write.

```python
if deployment.revision != command.expected_revision:
    raise DeploymentRevisionConflictError("Deployment revision changed.")
```

Without that lock, enforce the revision in an atomic conditional update instead. A Python comparison followed by an unprotected write is not sufficient. A zero-row conditional update may also mean the resource is missing or outside the permitted scope; distinguish that from an actual revision mismatch.

Next, add a reviewed HTTP definition and register the exact class. The planned foundation uses a frozen `ProblemDefinition` holding these five values:

```python
# HTTP-owned metadata; illustrative addition to the planned definitions.
DEPLOYMENT_REVISION_CONFLICT = ProblemDefinition(
    type_uri=f"{TYPE_PREFIX}#deployment-revision-conflict",
    code="deployment_revision_conflict",
    title="Deployment revision conflict",
    status=409,
    detail="Reload the deployment and review its current state before submitting a new action.",
)
```

Add this entry to the existing explicit mapping, alongside the five shared concrete application errors:

```python
# Entry in the HTTP mapper's ordinary dictionary, not a registration framework.
DeploymentRevisionConflictError: DEPLOYMENT_REVISION_CONFLICT,
```

The lookup is by exact type:

```python
def problem_for(exc: ApplicationError) -> ProblemDefinition:
    return APPLICATION_PROBLEMS.get(type(exc), INTERNAL_ERROR)
```

Here the definition constants, mapping name, and helper name illustrate the planned implementation. An unregistered subclass must become a reported 500, even when its parent has a 409 mapping. Do not infer public behavior from `exc.code`, the class name, or `str(exc)`.

A distinct internal error can reuse an existing public definition when callers need no new public distinction. Creating an exception does not always require creating a new HTTP problem type.

## 5. What the HTTP client receives

RFC 9457 is the **response format**, not an exception hierarchy. Inframeld's profile adds required fields and limits beyond the RFC. [RFC 9457][rfc9457] defines the standard format; the following shape is our project contract.

```http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json
Cache-Control: no-store
X-Request-ID: c66a2044-4e4f-4c07-983e-a3c221c7b1ad

{
  "type": "https://github.com/matejpalenik/inframeld/blob/main/docs/development/error-handling.md#conflict",
  "title": "Operation conflicts with current state",
  "status": 409,
  "detail": "The operation cannot be completed in the current state.",
  "code": "conflict",
  "requestId": "c66a2044-4e4f-4c07-983e-a3c221c7b1ad"
}
```

`type` identifies the problem kind. `code` is its documented Inframeld shorthand. `title` and `detail` are reviewed display text, not exception messages. `requestId` identifies this request and matches the response header. Our initial profile omits `instance`.

There is no enclosing `error` or `detail` object and no extra top-level `message`. Clients must tolerate unfamiliar types and extensions; they must not parse display text for control flow.

A request-validation problem also contains sanitized issues, for example:

```json
"errors": [
  {
    "location": "query",
    "path": ["limit"],
    "code": "out_of_range",
    "message": "Use a value within the permitted range."
  }
]
```

This is an excerpt from a problem object, not a separate response. Preserve only verified public field names and safe indices; submitted dictionary keys can contain secrets. Never return FastAPI/Pydantic's raw error dictionaries. At most 20 issues are returned; the list may be incomplete.

### The foundation does this once

`register_error_handlers(application)` is installed from composition. It handles request validation, supported application errors, Starlette HTTP exceptions, and unexpected exceptions. The shared builder constructs and serializes `ProblemDetails`, sets the media type and safe headers, and coordinates diagnostics.

Routes declare their applicable error responses using `problem_responses(definition)` from `shared/http/problem_openapi.py`. Routes that validate input must declare `VALIDATION_ERROR_PROBLEM` for HTTP 422. Handler registration does not update OpenAPI automatically. See [FastAPI's response documentation][fastapi-responses].

Composition installs `configure_problem_openapi(application)` once. FastAPI generates the model components; the hook changes only explicitly marked problem responses to `application/problem+json`. Successful response media types remain unchanged. Regenerate the committed OpenAPI artifact whenever production response declarations change.

## 6. Logging, cleanup, and retries

**Feature code raises; the execution boundary reports.** Do not add `logger.exception()` before every re-raise. The request boundary owns unexpected-failure diagnostics; command logging records a bounded outcome and operation identity without another traceback. Known dependency failures also receive operational reporting. Routine client rejections normally need no traceback.

Messages passed to exceptions must be controlled developer text. Neither those messages nor chained SDK messages are automatically safe to log. Use approved context such as request ID, operation ID, route template, and stable failure category—not document text, prompts, keys, SQL parameters, or provider bodies.

**Cleanup is not recovery.** Prefer context managers. Let an exception leave the transaction so rollback runs before the HTTP handler produces a response. Do not return a success result from an `except` or `finally` block after a failed command. Keep external calls outside short SQL transactions. When a catch is genuinely needed and the exception stays unchanged, re-raise with bare `raise`.

**Cancellation is not a normal 500.** Do not catch `BaseException`; let cancellation, `KeyboardInterrupt`, and `SystemExit` propagate. Use `finally` for necessary cleanup without suppressing the original failure. See [asyncio cancellation][python-cancellation].

**A 503 is not permission to repeat an operation.** Idempotency, uncertain paid calls, recorded job state, and expected revisions retain their existing application rules. Never “fix” a revision conflict by replacing the client's revision and retrying automatically.

### Common mistakes

| Do not do this | Do this instead |
| --- | --- |
| Catch every exception and raise `ApplicationError("Failed")` | Catch only a failure whose meaning you understand |
| Catch a dependency error and return `[]`, `None`, or a fabricated answer | Propagate the failure unless a fallback is explicitly part of the result contract |
| Map all `ValueError`, `IntegrityError`, or Pydantic errors to 422/409 | Classify narrowly; unknown failures remain 500 |
| Return `str(exc)` or `exc.detail` to the client | Use the reviewed problem definition |
| Log the same traceback in the adapter, use case, and route | Report once at the execution boundary |
| Use `assert` for a business precondition | Use an explicit condition and meaningful exception |

## Adding a failure

Choose whether the outcome is a valid result or a failure. Reuse an accurate exception or add the smallest meaningful class in its owner. Document its meaning and important `Raises` cases using Google-style docstrings. Translate only at an understood boundary, preserving the cause.

Then explicitly map any public failure, declare the route's applicable responses, and test the real behavior. Regenerate OpenAPI through the existing exporter when the production declarations change. Do not hand-edit the contract artifact.

### A concrete HTTP test

`error_test_app` below is a **test-only fixture to implement with issue 19**. It installs the real request-context middleware and shared handlers, without database startup or provider calls. It is not the product application.

```python
from fastapi import FastAPI
from fastapi.testclient import TestClient

from inframeld_backend.shared.application.errors import ConflictError


def test_conflict_is_safe_and_correlated(error_test_app: FastAPI) -> None:
    @error_test_app.get("/_test/conflict")
    async def fail() -> None:
        raise ConflictError("synthetic-secret-must-not-leak")

    with TestClient(error_test_app, raise_server_exceptions=False) as client:
        response = client.get("/_test/conflict")

    body = response.json()
    assert response.status_code == body["status"] == 409
    assert response.headers["content-type"] == "application/problem+json"
    assert response.headers["cache-control"] == "no-store"
    assert body["code"] == "conflict"
    assert body["requestId"] == response.headers["x-request-id"]
    assert "synthetic-secret-must-not-leak" not in response.text
    assert "errors" not in body
```

Also test the feature that actually raises the error, not just this fixture route. For example, a rejected rollback leaves the deployment unchanged; a dependency failure does not become an empty result. The foundation needs separate tests for unexpected 500s, raw-log disclosure, cancellation, and correlation under concurrency.

## Qualification checklist

For a feature change, verify its rejection, public mapping, absence of secret disclosure, applicable OpenAPI response, and unchanged transactional/recovery behavior. Do not add tests that merely assert exception inheritance or file placement.

For changes to the shared foundation, use the [full qualification checklist](error-handling-reference.md#qualification-checklist). The examples in this guide do not establish that issue 19 has passed it.

## Problem catalogue

The seven named starter definitions below retain the accepted type fragments and exact public wording. Append each heading's fragment to this fixed `TYPE_PREFIX`:

```text
https://github.com/matejpalenik/inframeld/blob/main/docs/development/error-handling.md
```

Keep these identities stable even if documentation moves. They become published when merged; the server does not fetch them at runtime.

### Validation error

**422 · `validation_error` · `#validation-error`**  
Title: **Request validation failed**  
Detail: **One or more request fields are invalid.**

For FastAPI `RequestValidationError`, with sanitized `errors`. The initial project convention includes malformed JSON in this 422 category.

### Invalid input

**422 · `invalid_input` · `#invalid-input`**  
Title: **Invalid input**  
Detail: **The supplied input is not valid for this operation.**

For supported application input rejections; no raw Pydantic error list.

### Resource not found

**404 · `resource_not_found` · `#resource-not-found`**  
Title: **Resource not found**  
Detail: **The requested resource is not available.**

Does not reveal resources outside the caller's permitted scope.

### Access denied

**403 · `access_denied` · `#access-denied`**  
Title: **Access denied**  
Detail: **You are not allowed to perform this operation.**

Represents an already-made permission decision, not authentication.

### Conflict

**409 · `conflict` · `#conflict`**  
Title: **Operation conflicts with current state**  
Detail: **The operation cannot be completed in the current state.**

The caller must resolve the relevant state conflict; unchanged retries are not automatically useful or safe.

### Dependency unavailable

**503 · `dependency_unavailable` · `#dependency-unavailable`**  
Title: **Dependency unavailable**  
Detail: **A required service is unavailable.**

For an identified availability failure. No generic `retryable` flag or invented `Retry-After` header.

### Internal error

**500 · `internal_error` · `#internal-error`**  
Title: **Internal server error**  
Detail: **An unexpected error occurred.**

For unexpected or unmapped failures. Report safe diagnostics with the request ID.

### Generic HTTP error

Use `type: "about:blank"`, `code: "http_error"`, the actual error status, its HTTP status phrase as the title, and fixed safe detail selected by status. This includes native router 404/405 responses. Do not automatically echo `HTTPException.detail`.

Preserve trusted protocol headers such as `Allow`, an appropriate `WWW-Authenticate` challenge, and an intentionally supplied `Retry-After`. The authentication producer supplies the challenge; the shared handler does not invent one.

[rfc9457]: https://www.rfc-editor.org/rfc/rfc9457.html
[python-errors]: https://docs.python.org/3/tutorial/errors.html
[python-cancellation]: https://docs.python.org/3/library/asyncio-exceptions.html
[litellm-errors]: https://docs.litellm.ai/docs/exception_mapping
[fastapi-responses]: https://fastapi.tiangolo.com/advanced/additional-responses/
