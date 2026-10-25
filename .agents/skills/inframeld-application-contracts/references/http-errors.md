# Translate failures into safe HTTP problems

<a id="translate-failures-into-safe-http-problems"></a>

Alice requests an unavailable resource. The application reports a transport-neutral failure and the HTTP boundary selects a safe public problem. Domain rejection, dependency failure and an unexpected bug require different handling.

> **Status:** accepted behavior is stated separately from proposed representations and qualification work. Existing Python types, generated OpenAPI and migrations own implemented shapes. Pending decisions are not accepted by this reference.

<a id="make-failure-and-retry-behavior-explicit"></a>

## Choose a focused reading task

- For delivered HTTP representation, read [Http problem contract](http-problem-contract.md).
- For translation and response boundary handling, read [Http error adapters](http-error-adapters.md).

## Make failure and retry behavior explicit

Errors use RFC 9457 `application/problem+json`: a stable type and code, a safe explanation, and a `requestId`. Domain and application code raise ordinary Python exceptions. Only reviewed exception mappings become public problems. The [error guide](./http-errors.md) explains which exception to use and lists the problems. Its [maintainer reference](./http-errors.md) covers handlers, logging, and OpenAPI.

The [pagination reference](pagination.md) defines list parameters, cursor syntax, and response fields. Each feature chooses a stable ordering, checks what its cursor means, and checks current access on every page.

Clients need to distinguish several outcomes. The first successful query returns an answer, while recovery after a lost response returns its receipt. Accepted background work returns `202`, while a duplicate synchronous request still running can return a conflict. An external call whose result is unknown cannot be treated as safe to repeat. **Expected revisions** detect competing edits, while **idempotency keys** identify repeated requests. [Jobs and idempotency](jobs-and-recovery.md) explains these cases.

MCP uses those same query and receipt outcomes through its [two tools](mcp-transport.md#tools).

<a id="the-rule-to-remember"></a>

<a id="1-the-rule-to-remember"></a>

## The rule to remember

**Raise an exception where the failure's meaning is clear. Catch it only to recover deliberately or explain that meaning to the next caller. Otherwise, let it pass through.**

In Python, “try/catch” is written `try/except`. An exception automatically travels back through callers until an appropriate handler catches it. You do not need to catch it in every function. See [Python exception handling](https://docs.python.org/3/tutorial/errors.html).

```text
A provider rejects a call as unavailable
    → Its adapter raises DependencyUnavailableError, preserving the cause
    → The application use case lets that exception pass through
    → The route lets that exception pass through
    → The shared HTTP handler returns one safe 503 problem
```

The HTTP handler **builds a response**. It does not raise another wrapper exception.

For example, `ProviderError → RepositoryError → ServiceError → ControllerError` adds little if every name just means “something failed.” Add a new exception only when the distinction changes what a caller should do.

<a id="which-error-should-i-use"></a>

<a id="2-which-error-should-i-use"></a>

## Which error should I use?

These shared application exceptions belong in `shared/application/errors/application_errors.py`. Their base remains in `shared/application/errors/application_error.py`.

| Situation | Raise | Shared HTTP mapping |
| --- | --- | --- |
| Parsed input is invalid for this operation | `InvalidInputError` | 422 |
| A requested resource is unavailable within the caller's permitted scope | `ResourceNotFoundError` | 404 |
| An authorization check has denied an operation | `AccessDeniedError` | 403 |
| Current state prevents the requested operation | `ConflictError` | 409 |
| A new command uses an expected revision that is no longer current | `StaleRevisionError` | 409 `stale_revision` |
| An idempotency key is reused for a different request | `IdempotencyKeyReusedError` | 409 |
| The same request is retried while its synchronous operation is unfinished | `IdempotencyInProgressError` | 409 |
| An adapter has identified a required dependency's availability failure | `DependencyUnavailableError` | 503 |
| A bug or an unclassified failure occurs | Let the original exception propagate | Safe 500 |

The statuses belong to the **HTTP mapper**, not to these Python classes. The same application code must also work for MCP and workers.

**A valid result is not an error.** Alice's document list can be empty. A query can find insufficient evidence. But a required search shard failing is a real failure, because the application could not finish the search.

FastAPI raises `RequestValidationError` when incoming fields are malformed. Business code must not manufacture one. A Pydantic error inside the application may indicate a bug rather than bad input from the caller.

Authentication establishes who called. Permission checks decide what that caller may do. `AccessDeniedError` expresses a completed permission decision and does not verify credentials. Missing or invalid caller credentials belong to the authentication adapter. A model provider rejecting Inframeld's provider key does not automatically mean our caller should receive HTTP 401.

<a id="everyday-examples"></a>

<a id="3-everyday-examples"></a>

## Everyday examples

<a id="a-reject-a-missing-resource-without-a-try-block"></a>

### A. Reject a missing resource without a try block

**Application use-case excerpt:** `find_visible` represents a read that enforces the verified actor's project and document scope.

```python
from inframeld_backend.shared.application.errors.application_errors import ResourceNotFoundError

# Inside the read use case; actor comes from verified authentication.
document = await documents.find_visible(actor, project_id, document_id)

if document is None:
    raise ResourceNotFoundError("Document unavailable to this operation.")

return document
```

There is nothing to catch here. If the database read fails, let that failure continue. Returning `None` would turn an outage into a misleading 404.

The exception itself does not check access. The feature must decide when to hide a resource's existence so it cannot reveal another tenant's document.

<a id="b-translate-a-domain-rejection-only-at-the-operation-that-understands-it"></a>

### B. Translate a domain rejection only at the operation that understands it

Domain errors live in the owning domain package. Shared bases are in `shared/domain/errors/domain_errors.py`. They do not inherit from `ApplicationError` or import FastAPI.

**Domain method excerpt:** a rollback cannot proceed while a candidate is attached.

```python
from inframeld_backend.shared.domain.errors.domain_errors import InvalidStateTransitionError

# Inside the deployment's rollback method.
if self.candidate is not None:
    raise InvalidStateTransitionError("Rollback requires no active candidate.")
```

**Application use-case excerpt:** this particular rejection means the caller requested an operation that conflicts with current state.

```python
from inframeld_backend.shared.application.errors.application_errors import ConflictError
from inframeld_backend.shared.domain.errors.domain_errors import InvalidStateTransitionError

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

<a id="stable-domain-error-mapping"></a>

<a id="keep-translated-application-messages-stable"></a>

#### Keep translated application messages stable

When a service translates a recognized domain rejection, it owns the application error type and message. Do not use `ConflictError(str(error))` or another wrapper that copies arbitrary domain exception text. Domain wording can change independently of the application's failure contract. Preserve the original exception with `raise ... From error` for controlled diagnostics. The transport's shared handler still owns the safe response fields and does not expose exception messages or chained causes by default.

The implemented [`ProjectGrantChangeService.assign_use_only()`](../../../../apps/backend/src/inframeld_backend/access/application/services/project_grant_change_service.py) catches `ProjectGrantAlreadyExistsError` only around the membership's assignment method. It raises `ConflictError("This project action grant already exists.")` with the original error as its cause. Loading, persistence, audit and completion failures remain outside that catch and propagate to the transaction owner.

The [grant service regression test](../../../../apps/backend/tests/unit/access/application/services/test_project_grant_change_service.py) named `test_duplicate_conflict_message_is_independent_of_domain_wording` injects different domain wording. It checks the exact application message, preserved cause, absence of saving/completion and rollback. When adding a similar translation, test its application meaning and failure effects. Do not make all domain errors conflicts or catch every exception to produce one convenient message. The [service-writing guide](../../inframeld-coding-standards/references/services-and-use-cases.md#service-writing-guide) places this boundary in the complete operation.

<a id="c-translate-a-known-provider-failure-in-its-adapter"></a>

### C. Translate a known provider failure in its adapter

All model calls go through ModelGateway. This **illustrative excerpt for a future non-streaming LiteLLM adapter** runs after the gateway has checked admission, credentials, destination, budget, and retry policy. `approved_call_options` represents the options it prepared.

```python
import litellm

from inframeld_backend.shared.application.errors.application_errors import DependencyUnavailableError

try:
    provider_response = await litellm.acompletion(**approved_call_options)
except litellm.ServiceUnavailableError as exc:
    raise DependencyUnavailableError("Model provider unavailable.") from exc

# Validate and translate provider output after the protected call.
# An invalid response is not automatically an availability failure.
```

The recorded [LiteLLM mapping reference](https://docs.litellm.ai/docs/exception_mapping) describes this availability exception. The selected provider and version still need a test proving which exception they emit. This example covers one failure, not a complete adapter.

Do not broaden this to `except Exception`. Bad configuration, rejected credentials, provider policy decisions, timeouts, and bugs need handling based on their actual meaning. Even an SDK error named “connection error” may be a catch-all category rather than proof of an outage.

This code makes **no retry decision**. A provider may have performed paid work even when its response was lost. Keep the original operation and follow its recovery rules. Do not silently retry, switch provider, or invent a fallback answer here.

<a id="d-let-the-route-stay-simple"></a>

### D. Let the route stay simple

**HTTP route-body excerpt:** authentication, dependency injection, request models, and response declarations are configured around this body.

```python
result = await use_case.execute(command)
return result
```

Do not add a route-level `try/except` just to return a 404 or 409. The shared handlers already own that conversion.

<a id="when-should-i-create-a-new-exception"></a>

<a id="4-when-should-i-create-a-new-exception"></a>

## When should I create a new exception?

**Reuse an existing class unless someone needs to distinguish the new failure.** A separate `DocumentNotFoundError`, `CollectionNotFoundError`, and `PipelineNotFoundError` is unnecessary when all require identical handling.

A deployment revision conflict is a useful exception to that rule. Another change has happened since the client read the Deployment. The client must reload it and make a fresh decision, rather than retry the old decision against newer state.

**Proposed feature example , not an additional accepted starter type:** place this in the Releases application package.

```python
from typing import ClassVar

from inframeld_backend.shared.application.errors.application_errors import ConflictError

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

1. Add its stable code to `ProblemCode` in `apps/backend/src/inframeld_backend/shared/http/types/problem_code.py`. This HTTP enum is separate from the application exception's `ClassVar[str]` code. Application code must not import it.
2. Add a frozen `ProblemDefinition` in that file. Its `code` is the enum member, and its `type_uri`, `title`, `status`, and `detail` are reviewed public metadata. Document the new URI anchor in this guide's problem catalogue before using it.
3. In `apps/backend/src/inframeld_backend/shared/http/mappers/problem_mapper.py`, add the concrete exception class to `_APPLICATION_PROBLEMS`, pointing to the new or reused definition.
4. Declare the applicable response on the feature route with `problem_responses(definition)` and test its runtime response and OpenAPI contract.

`problem_mapper.for_application_error()` matches the **exact exception class**. If it is not registered, the mapper uses `INTERNAL_ERROR_PROBLEM` and reports a 500. That also applies to an unregistered subclass of a class mapped to 409. Neither its name, `exc.code`, nor `str(exc)` defines the public response.

<a id="declare-the-actual-route-contract"></a>

### Declare the actual route contract

Runtime handlers build the response, but each route still has to describe its possible responses in OpenAPI. Use `problem_responses(definition)` for each applicable status, including `VALIDATION_ERROR_PROBLEM` for input-validation 422s. One status has one declaration. Deliberately combine failures sharing a status rather than accidentally replacing a dictionary entry.

See [the production health route](../../../../apps/backend/src/inframeld_backend/shared/http/routes/health_routes.py) and [test-only JSON/multipart contract fixtures](../../../../apps/backend/tests/unit/contract/test_openapi_contract.py). Regenerate the native contract when production declarations change. The [maintainer reference](http-error-adapters.md#openapi-and-client-compatibility) owns the narrow media-type hook and handler installation.

<a id="common-mistakes"></a>

### Common mistakes

| Do not do this | Do this instead |
| --- | --- |
| Catch every exception and raise `ApplicationError("Failed")` | Catch only a failure whose meaning you understand |
| Catch a dependency error and return `[]`, `None`, or a fabricated answer | Propagate the failure unless a fallback is explicitly part of the result contract |
| Map all `ValueError`, `IntegrityError`, or Pydantic errors to 422/409 | Classify narrowly. Unknown failures remain 500 |
| Return `str(exc)` or `exc.detail` to the client | Use the reviewed problem definition |
| Log the same traceback in the adapter, use case, and route | Report once at the execution boundary |
| Use `assert` for a business precondition | Use an explicit condition and meaningful exception |

<a id="adding-a-failure"></a>

## Adding a failure

First decide whether the outcome is valid or a failure. Reuse an accurate exception, or add the smallest meaningful one in the owning package. Explain its meaning and relevant failure handling where that adds information beyond its name and base contract. Do not add a boilerplate docstring to every error subclass. Translate it only where its meaning is understood, preserving the original cause.

Then explicitly map any public failure, declare the route's applicable responses, and test the real behavior. Regenerate OpenAPI through the existing exporter when the production declarations change. Do not hand-edit the contract artifact.

<a id="a-concrete-http-test"></a>

### A concrete HTTP test

The existing [handler tests](../../../../apps/backend/tests/unit/shared/http/handlers/test_error_handlers.py) use the real middleware and handlers in a test-only app. The example below is a complete illustrative file at `apps/backend/tests/unit/shared/http/test_feature_error_example.py`. That file does not exist in the repository. It needs no database startup or provider calls.

```python
from fastapi import FastAPI
from fastapi.testclient import TestClient

from inframeld_backend.shared.application.errors.application_errors import ConflictError
from inframeld_backend.shared.http.handlers.error_handlers import register_error_handlers
from inframeld_backend.shared.http.middleware.request_context_middleware import (
    RequestContextMiddleware,
)


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

<a id="qualification-checklist"></a>

## Qualification checklist

For a feature change, verify its rejection, public mapping, absence of secret disclosure, applicable OpenAPI response, and unchanged transactional/recovery behavior. Do not add tests that merely assert exception inheritance or file placement.

For changes to the shared foundation, use the [full qualification checklist](#qualification-checklist). Passing error-handling checks does not qualify future feature behavior, including a list endpoint's cursor-content validation.

<a id="transactions-and-recovery"></a>

## Transactions and recovery

Commands own short database transactions and make external calls outside them. Let exceptions leave transaction contexts before the HTTP handler builds the response, so rollback can happen. The handler must not commit, authorize, retry, migrate, or resume uncertain paid work.

Translate a database constraint failure only when the adapter recognizes the exact structured driver or constraint condition. Do not parse message text or treat every `IntegrityError` as a user conflict. Verify the selected driver's representation in the adapter and its integration tests.

Let `CancelledError`, `KeyboardInterrupt`, and `SystemExit` continue. Use context managers or `finally` for cleanup without hiding errors. A provider timeout does not establish whether work happened. Neither HTTP 503 nor `DependencyUnavailableError` authorizes a retry. Follow the [job and idempotency rules](jobs-and-recovery.md).

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

Use `TestClient(..., raise_server_exceptions=False)` to inspect unexpected 500 responses. Also keep a normal test proving that the server-error path still propagates the exception. To test secret disclosure, capture the **final rendered logs through production processors**. Bare `structlog.testing.capture_logs()` disables those processors and cannot establish safety by itself. See [structlog testing](https://www.structlog.org/en/stable/testing.html).

HTTP and schema fixtures require no production credentials, provider calls, or database. PostgreSQL integration tests use isolated temporary databases on the Compose test service. Follow the repository's scaffold → behavioral red test → implementation → focused tests sequence where adding behavior. The existing test setup requires the non-production `apps/backend/.env.test`.

Regression coverage lives in:

- [HTTP unit tests](../../../../apps/backend/tests/unit/shared/http): models, builders, mappings, validation, handlers, correlation, late failures, and cancellation.
- [Infrastructure unit tests](../../../../apps/backend/tests/unit/shared/infrastructure): rendered diagnostic sanitization and reporting ownership.
- [OpenAPI contract tests](../../../../apps/backend/tests/unit/contract/test_openapi_contract.py): media types, components, aliases, field constraints, multipart requests, drift, and exclusion of fixture routes.
- [Uvicorn integration test](../../../../apps/backend/tests/integration/observability/test_error_reporting_uvicorn.py): server-path diagnostic deduplication.
- [Database integration tests](../../../../apps/backend/tests/integration/postgres/test_database_postgres.py) and [migration integration tests](../../../../apps/backend/tests/integration/postgres/test_migrations_postgres.py): transactions, lifecycle, engine parameter hiding, and migration-command disclosure.

From the repository root, run the relevant checks after changing the foundation:

```bash
pnpm --filter @inframeld/backend lint
pnpm --filter @inframeld/backend format:check
pnpm --filter @inframeld/backend typecheck
pnpm --filter @inframeld/backend test
pnpm --filter @inframeld/backend openapi:check
pnpm test:integration
```

After changing production declarations, run `pnpm --filter @inframeld/backend openapi` before checking drift. It writes the generated contract. Integration tests require the local Compose database, migrate the non-production `.env.test` database, and exercise actual PostgreSQL behavior. CI uses the same complete integration command as local development.

Review dependency boundaries and repository organization manually. Do not add automated architecture, import-boundary, or composition-construction tests. Test observable behavior rather than importability or inheritance alone.

Use approachable docstrings where they explain failure meaning, safe attributes, handling, or ownership that a maintainer would otherwise have to infer. Shared contracts belong on protocols. Straightforward error subclasses do not need repetitive descriptions. Keep the important distinctions on their base or on errors with different handling. Preserve public response fields and OpenAPI descriptions.

When the foundation changes, update affected guides, architecture, backend README, and skills together. List endpoints also need their own checks of cursor contents and authorization on every page.
