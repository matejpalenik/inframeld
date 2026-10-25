# Read the delivered HTTP problem contract

Alice receives a safe problem response with a request ID. The implemented Pydantic types and catalogue own its exact representation. This reference explains required semantics without another handwritten response model.

<a id="ownership-and-implementation-scope"></a>

## Ownership and implementation scope

The [authentication extension accepted on 2026-10-04](../../../../docs/development/error-handling.md#authentication-contract) now has inspected human cookie/bearer dispatch and verification, `invalid_authentication_request` definition/catalogue support and route declarations. See [Access implementation status](../../inframeld-access-models/references/credential-dispatch.md#implemented-human-authentication) and [the problem catalogue](../../../../apps/backend/src/inframeld_backend/shared/http/definitions/problem_catalogue.py). Preserve the established generic bodies, 400 type/title/detail/code and trusted Bearer realm/challenge literals. Application-key verification, complete generated-client delivery and full account-UI/CLI/recovery production qualification remain unfinished. Reading source is not evidence that their tests were rerun. New Access bodies, maintenance input and private recovery callbacks have [separate bounds](../../inframeld-access-models/references/grant-contracts.md#mutation-profile). The [HTTP draft](../../inframeld-access-models/references/grant-contracts.md#http-operation-matrix) defines safe 413/415 and per-profile declarations for final review. Maintenance has its own bounded stdout/error/exit contract. Private callbacks use ordinary safe problems without product authentication.

All paths below are relative to `apps/backend/src/inframeld_backend/`.

| Location | Responsibility |
| --- | --- |
| [shared/domain/errors/domain_errors.py](../../../../apps/backend/src/inframeld_backend/shared/domain/errors/domain_errors.py) | `DomainError` and `InvalidStateTransitionError`. No automatic HTTP mapping |
| [shared/application/errors/application_error.py](../../../../apps/backend/src/inframeld_backend/shared/application/errors/application_error.py) | Transport-neutral `ApplicationError` and its diagnostic-only message |
| [shared/application/errors/application_errors.py](../../../../apps/backend/src/inframeld_backend/shared/application/errors/application_errors.py) | Reviewed application failures, including transport-neutral authentication rejection |
| [shared/http/responses/problem_details.py](../../../../apps/backend/src/inframeld_backend/shared/http/responses/problem_details.py) | Published `ProblemDetails` response |
| [shared/http/responses/validation_issue.py](../../../../apps/backend/src/inframeld_backend/shared/http/responses/validation_issue.py) | Sanitized `ValidationIssue` response component |
| [shared/http/types/problem_field_types.py](../../../../apps/backend/src/inframeld_backend/shared/http/types/problem_field_types.py) | Bounded field aliases and output limits |
| [shared/http/types/problem_code.py](../../../../apps/backend/src/inframeld_backend/shared/http/types/problem_code.py) | Public `ProblemCode` vocabulary |
| [shared/http/definitions/problem_definition.py](../../../../apps/backend/src/inframeld_backend/shared/http/definitions/problem_definition.py) | Immutable catalogue entry used by mappers and builders |
| [shared/http/definitions/problem_catalogue.py](../../../../apps/backend/src/inframeld_backend/shared/http/definitions/problem_catalogue.py) | Reviewed public problem catalogue |
| [shared/http/mappers/problem_mapper.py](../../../../apps/backend/src/inframeld_backend/shared/http/mappers/problem_mapper.py) | Exact-type application mapping and generic HTTP-status definitions |
| [shared/http/builders/problem_response.py](../../../../apps/backend/src/inframeld_backend/shared/http/builders/problem_response.py) | `build_problem_response()`: serialization, correlation, and allowed headers |
| [shared/http/openapi/problem_openapi.py](../../../../apps/backend/src/inframeld_backend/shared/http/openapi/problem_openapi.py) | `problem_responses()` declarations and the narrow OpenAPI media-type hook |
| [shared/http/validation/request_validation_translator.py](../../../../apps/backend/src/inframeld_backend/shared/http/validation/request_validation_translator.py) | `issues_from_request_error()`: bounded, sanitized validation issues |
| [shared/http/handlers/error_handlers.py](../../../../apps/backend/src/inframeld_backend/shared/http/handlers/error_handlers.py) | `register_error_handlers()`: request validation, application, HTTP, and unexpected failures |
| [shared/http/middleware/request_context_middleware.py](../../../../apps/backend/src/inframeld_backend/shared/http/middleware/request_context_middleware.py) | Request IDs, scoped log context, summaries, and request-boundary diagnostics |
| [shared/infrastructure/diagnostics/error_reporting.py](../../../../apps/backend/src/inframeld_backend/shared/infrastructure/diagnostics/error_reporting.py) | Report and mark the exact exception instance once |
| [shared/infrastructure/diagnostics/safe_exception_diagnostic.py](../../../../apps/backend/src/inframeld_backend/shared/infrastructure/diagnostics/safe_exception_diagnostic.py) | Bounded serialization of exception structure without messages, locals, or source text |
| [shared/infrastructure/logging/logging_configuration.py](../../../../apps/backend/src/inframeld_backend/shared/infrastructure/logging/logging_configuration.py) | Configure JSON/console rendering and stdlib/Uvicorn integration |
| [shared/infrastructure/logging/command_logging.py](../../../../apps/backend/src/inframeld_backend/shared/infrastructure/logging/command_logging.py) | Command outcomes and operation metadata without duplicate tracebacks |
| [shared/infrastructure/resources/database.py](../../../../apps/backend/src/inframeld_backend/shared/infrastructure/resources/database.py) | API database lifecycle and SQLAlchemy parameter hiding |
| [shared/infrastructure/migrations/migration_runner.py](../../../../apps/backend/src/inframeld_backend/shared/infrastructure/migrations/migration_runner.py) and [migrate.py](../../../../apps/backend/src/inframeld_backend/migrate.py) | Migration locking/execution and the operator failure-reporting boundary |
| [bootstrap/application_factory.py](../../../../apps/backend/src/inframeld_backend/bootstrap/application_factory.py) | Install handlers, request middleware, and OpenAPI correction |

The separate Alembic engine in `apps/backend/migrations/env.py` also hides SQLAlchemy parameters. `RequestId` is a UUID value object in application and request state. HTTP/logging explicitly serialize its value. `OperationId` remains validated opaque text. `ApplicationErrorCode` is a typed application vocabulary. `AuthenticationRequiredError` maps to the existing generic 401 `http_error` response.

Keep feature exceptions in the domain or application package that owns their meaning. Application interfaces define which failures an infrastructure adapter may expose. Domain and application code must not import HTTP models, FastAPI, database exceptions, or structlog. `DomainError` remains separate from `ApplicationError`.

`DatabaseStartupError`, `DatabaseSchemaCompatibilityError`, and `MigrationLockError` stay in their infrastructure modules. They report startup or operator failures, not request rejections. Failed startup must prevent readiness. An incompatible schema needs operator action. A migration cannot proceed without acquiring its lock.

Ordinary classes and functions are sufficient. Do not add an error bus, metaclass/decorator registry, generic result framework, hierarchy of infrastructure wrappers, or worker engine to maintain this foundation.

<a id="http-representation"></a>

## HTTP representation

[RFC 9457](https://www.rfc-editor.org/rfc/rfc9457.html) supplies the response format. The exact required fields, naming, cache rules, limits, and UUID convention below are **Inframeld's contract**, not extra requirements imposed by the RFC.

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
