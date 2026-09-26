# Error handling: a practical guide

Use this guide when adding a backend feature and deciding how to report a failure. Start with the exception-selection table, then follow the examples. [API contracts](api-contracts.md) explains the surrounding public interface. [ADR-0004](../adr/ADR-0004-use-rfc-9457-problem-details-for-http-errors.md) explains the error-format decision.

> **Status — 23 September 2026:** The shared error-handling foundation is implemented. The [maintainer reference](error-handling-reference.md#qualification-checklist) identifies its tests and verification commands. The separate [pagination guide](pagination.md) covers the implemented shared list contract. Each feature still validates its own cursor contents.

For changes to shared error handling, use the [maintainer reference](error-handling-reference.md). It owns the file map, exact response-field limits, diagnostics rules, and checks. [Documentation maintenance](documentation-maintenance.md) explains how to keep these sources aligned.

The feature examples are illustrative. They do not claim that these business operations are implemented. Each **excerpt** shows where error handling belongs, without providing a complete authorization, persistence, or retry implementation.

## Contents

| Reader's question | Start here |
| --- | --- |
| When should I catch a failure? | [The rule](#1-the-rule-to-remember) |
| Which exception fits? | [Selection table](#2-which-error-should-i-use) |
| How does this look in a feature? | [Examples](#3-everyday-examples) |
| When is a new exception justified? | [New exceptions](#4-when-should-i-create-a-new-exception) |
| What does a client receive? | [HTTP behavior](#5-what-the-http-client-receives) |
| How do cleanup and retries behave? | [Execution boundaries](#6-logging-cleanup-and-retries) |
| Which public types exist? | [Problem catalogue](#problem-catalogue) |

## 1. The rule to remember

**Raise an exception where the failure's meaning is clear. Catch it only to recover deliberately or explain that meaning to the next caller. Otherwise, let it pass through.**

In Python, “try/catch” is written `try/except`. An exception automatically travels back through callers until an appropriate handler catches it. You do not need to catch it in every function. See [Python exception handling][python-errors].

```text
A provider rejects a call as unavailable
    → Its adapter raises DependencyUnavailableError, preserving the cause
    → The application use case lets that exception pass through
    → The route lets that exception pass through
    → The shared HTTP handler returns one safe 503 problem
```

The HTTP handler **builds a response**. It does not raise another wrapper exception.

For example, `ProviderError → RepositoryError → ServiceError → ControllerError` adds little if every name just means “something failed.” Add a new exception only when the distinction changes what a caller should do.

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

**A valid result is not an error.** Alice's document list can be empty. A query can find insufficient evidence. But a required search shard failing is a real failure, because the application could not finish the search.

FastAPI raises `RequestValidationError` when incoming fields are malformed. Business code must not manufacture one. A Pydantic error inside the application may indicate a bug rather than bad input from the caller.

Authentication establishes who called. Permission checks decide what that caller may do. `AccessDeniedError` expresses a completed permission decision and does not verify credentials. Missing or invalid caller credentials belong to the authentication adapter. A model provider rejecting Inframeld's provider key does not automatically mean our caller should receive HTTP 401.

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

There is nothing to catch here. If the database read fails, let that failure continue. Returning `None` would turn an outage into a misleading 404.

The exception itself does not check access. The feature must decide when to hide a resource's existence so it cannot reveal another tenant's document.

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

`from exc` preserves the original cause for controlled diagnostics. It does not expose that cause in the HTTP response.

Keep loading and saving outside this catch. An invalid state found while loading stored data may indicate corruption or a bug, which is different from rejecting Alice's requested rollback. **Domain errors do not all map to HTTP 409.**

A use case can also document and directly expose a specific domain error. It need not add a wrapper solely to match a layer diagram.

### C. Translate a known provider failure in its adapter

All model calls go through ModelGateway. This **illustrative excerpt for a future non-streaming LiteLLM adapter** runs after the gateway has checked admission, credentials, destination, budget, and retry policy. `approved_call_options` represents the options it prepared.

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

The recorded [LiteLLM mapping reference][litellm-errors] describes this availability exception. The selected provider and version still need a test proving which exception they emit. This example covers one failure, not a complete adapter.

Do not broaden this to `except Exception`. Bad configuration, rejected credentials, provider policy decisions, timeouts, and bugs need handling based on their actual meaning. Even an SDK error named “connection error” may be a catch-all category rather than proof of an outage.

This code makes **no retry decision**. A provider may have performed paid work even when its response was lost. Keep the original operation and follow its recovery rules. Do not silently retry, switch provider, or invent a fallback answer here.

### D. Let the route stay simple

**HTTP route-body excerpt:** authentication, dependency injection, request models, and response declarations are configured around this body.

```python
result = await use_case.execute(command)
return result
```

Do not add a route-level `try/except` just to return a 404 or 409. The shared handlers already own that conversion.

## 4. When should I create a new exception?

**Reuse an existing class unless someone needs to distinguish the new failure.** A separate `DocumentNotFoundError`, `CollectionNotFoundError`, and `PipelineNotFoundError` is unnecessary when all require identical handling.

A deployment revision conflict is a useful exception to that rule. Another change has happened since the client read the Deployment. The client must reload it and make a fresh decision, rather than retry the old decision against newer state.

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

Hold that lock through the write, or put the revision check inside an atomic conditional database update. Comparing in Python and then writing without protection leaves room for another update in between. If a conditional update changes zero rows, establish why. The resource may be missing or outside the caller's scope rather than at a different revision.

Next, decide whether callers need a new public problem or whether the existing `CONFLICT_PROBLEM` accurately describes the outcome. A distinct internal exception can reuse an existing public definition.

If a new public problem is needed:

1. Add its stable code to `ProblemCode` in `apps/backend/src/inframeld_backend/shared/http/problem_definitions.py`. This HTTP enum is separate from the application exception's `ClassVar[str]` code. Application code must not import it.
2. Add a frozen `ProblemDefinition` in that file. Its `code` is the enum member, and its `type_uri`, `title`, `status`, and `detail` are reviewed public metadata. Document the new URI anchor in this guide's problem catalogue before using it.
3. In `apps/backend/src/inframeld_backend/shared/http/problem_mapper.py`, add the concrete exception class to `_APPLICATION_PROBLEMS`, pointing to the new or reused definition.
4. Declare the applicable response on the feature route with `problem_responses(definition)` and test its runtime response and OpenAPI contract.

`problem_mapper.for_application_error()` matches the **exact exception class**. If it is not registered, the mapper uses `INTERNAL_ERROR_PROBLEM` and reports a 500. That also applies to an unregistered subclass of a class mapped to 409. Neither its name, `exc.code`, nor `str(exc)` defines the public response.

## 5. What the HTTP client receives

[RFC 9457][rfc9457] defines the HTTP error response format. It does not prescribe Python exception classes. Inframeld adds the required fields and limits described here:

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

There is no surrounding `error` or `detail` object and no extra top-level `message`. Clients must tolerate unfamiliar problem types and extension fields. Use documented codes for decisions, never parsed display text.

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

This fragment belongs inside the problem object. Return at most 20 sanitized issues, so the list can be incomplete. Include only verified public field names and safe indices. Submitted dictionary keys may contain secrets. Never return raw FastAPI or Pydantic error dictionaries.

### Declare the actual route contract

Runtime handlers build the response, but each route still has to describe its possible responses in OpenAPI. Use `problem_responses(definition)` for each applicable status, including `VALIDATION_ERROR_PROBLEM` for input-validation 422s. One status has one declaration. Deliberately combine failures sharing a status rather than accidentally replacing a dictionary entry.

See [the production health route](../../apps/backend/src/inframeld_backend/shared/http/health.py) and [test-only JSON/multipart contract fixtures](../../apps/backend/tests/unit/contract/test_openapi_contract.py). Regenerate the native contract when production declarations change. The [maintainer reference](error-handling-reference.md#openapi-and-client-compatibility) owns the narrow media-type hook and handler installation.

## 6. Logging, cleanup, and retries

**Feature code raises the failure. The request boundary reports it.** Do not add `logger.exception()` before every re-raise. The request handler owns unexpected-failure diagnostics. Command logging records a limited outcome and operation ID without another traceback. Report known dependency failures too. Ordinary client rejections usually need no traceback.

Write exception messages as controlled developer text, but do not assume they or chained SDK messages are safe to log. Use approved fields such as request ID, operation ID, route template, and failure category. Exclude document text, prompts, keys, SQL parameters, and provider bodies.

**Cleaning up does not turn failure into success.** Prefer context managers and let exceptions leave the transaction so rollback happens before the HTTP response is built. Never return success from `except` or `finally` after a failed command. Keep external calls outside short SQL transactions. When a catch needs to pass on the same exception, use bare `raise`.

**Cancellation is not an ordinary 500.** Do not catch `BaseException`. Let cancellation, `KeyboardInterrupt`, and `SystemExit` continue. Use `finally` for necessary cleanup without hiding the original failure. See [asyncio cancellation][python-cancellation].

**A 503 is not permission to repeat an operation.** Idempotency, uncertain paid calls, recorded job state, and expected revisions retain their existing application rules. Never “fix” a revision conflict by replacing the client's revision and retrying automatically.

### Common mistakes

| Do not do this | Do this instead |
| --- | --- |
| Catch every exception and raise `ApplicationError("Failed")` | Catch only a failure whose meaning you understand |
| Catch a dependency error and return `[]`, `None`, or a fabricated answer | Propagate the failure unless a fallback is explicitly part of the result contract |
| Map all `ValueError`, `IntegrityError`, or Pydantic errors to 422/409 | Classify narrowly. Unknown failures remain 500 |
| Return `str(exc)` or `exc.detail` to the client | Use the reviewed problem definition |
| Log the same traceback in the adapter, use case, and route | Report once at the execution boundary |
| Use `assert` for a business precondition | Use an explicit condition and meaningful exception |

## Adding a failure

First decide whether the outcome is valid or a failure. Reuse an accurate exception, or add the smallest meaningful one in the owning package. Explain its meaning and relevant `Raises` cases in Google-style docstrings. Translate it only where its meaning is understood, preserving the original cause.

Then explicitly map any public failure, declare the route's applicable responses, and test the real behavior. Regenerate OpenAPI through the existing exporter when the production declarations change. Do not hand-edit the contract artifact.

### A concrete HTTP test

The existing [handler tests](../../apps/backend/tests/unit/shared/http/test_error_handlers.py) use the real middleware and handlers in a test-only app. The example below is a complete illustrative file at `apps/backend/tests/unit/shared/http/test_feature_error_example.py`. That file does not exist in the repository. It needs no database startup or provider calls.

```python
from fastapi import FastAPI
from fastapi.testclient import TestClient

from inframeld_backend.shared.application.errors import ConflictError
from inframeld_backend.shared.http.error_handlers import register_error_handlers
from inframeld_backend.shared.http.request_context import RequestContextMiddleware

def test_conflict_is_safe_and_correlated() -> None:
    application = FastAPI()
    register_error_handlers(application)
    application.add_middleware(RequestContextMiddleware)

    @application.get("/_test/conflict")
    async def fail() -> None:
        raise ConflictError("synthetic-secret-must-not-leak")

    with TestClient(application, raise_server_exceptions=False) as client:
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

Also test the feature that raises the failure. A rejected rollback must leave the Deployment unchanged. A failed dependency must not become an empty result. Preserve the shared tests for unexpected 500s, secret-free rendered logs, cancellation, and request IDs under concurrency.

## Qualification checklist

For a feature change, verify its rejection, public mapping, absence of secret disclosure, applicable OpenAPI response, and unchanged transactional/recovery behavior. Do not add tests that merely assert exception inheritance or file placement.

For changes to the shared foundation, use the [full qualification checklist](error-handling-reference.md#qualification-checklist). Passing error-handling checks does not qualify future feature behavior, including a list endpoint's cursor-content validation.

## Problem catalogue

The seven named starter definitions below retain the accepted type fragments and exact public wording. Append each heading's fragment to this fixed `TYPE_PREFIX`:

```text
https://github.com/matejpalenik/inframeld/blob/main/docs/development/error-handling.md
```

Keep these identities stable if the documentation moves. They become published when merged. The server does not fetch them while handling a request.

### Validation error

**422 · `validation_error` · `#validation-error`**  
Title: **Request validation failed**  
Detail: **One or more request fields are invalid.**

For FastAPI `RequestValidationError`, with sanitized `errors`. The initial project convention includes malformed JSON in this 422 category.

### Invalid input

**422 · `invalid_input` · `#invalid-input`**  
Title: **Invalid input**  
Detail: **The supplied input is not valid for this operation.**

For supported application input rejections. Do not include a raw Pydantic error list.

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

The caller must resolve the state conflict. Repeating the same request is not automatically useful or safe.

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

Preserve trusted protocol headers such as `Allow`, an appropriate `WWW-Authenticate` challenge, and an intentionally supplied `Retry-After`. The authentication producer supplies the challenge. The shared handler does not invent one.

[rfc9457]: https://www.rfc-editor.org/rfc/rfc9457.html
[python-errors]: https://docs.python.org/3/tutorial/errors.html
[python-cancellation]: https://docs.python.org/3/library/asyncio-exceptions.html
[litellm-errors]: https://docs.litellm.ai/docs/exception_mapping
[fastapi-responses]: https://fastapi.tiangolo.com/advanced/additional-responses/
