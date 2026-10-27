# HTTP problem catalogue

<a id="http-problem-catalogue"></a>

Alice can use a stable problem code to decide whether to correct input, sign in again or inspect an operation. The public response contains a safe explanation, not provider internals. This path and its published fragments are part of the HTTP contract.

The [implemented catalogue](../../apps/backend/src/inframeld_backend/shared/http/definitions/problem_catalogue.py) owns emitted type URIs, codes, titles, details and status pairings. Native [OpenAPI](../../contracts/openapi/v1/inframeld-v1.json) declares each delivered operation. For translating a new failure, read [HTTP errors](../../.agents/skills/inframeld-application-contracts/references/http-errors.md).

<a id="what-the-http-client-receives"></a>

<a id="5-what-the-http-client-receives"></a>

## What the HTTP client receives

[RFC 9457](https://www.rfc-editor.org/rfc/rfc9457.html) defines the HTTP error response format. It does not prescribe Python exception classes. Inframeld adds the required fields and limits described here:

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

<a id="accepted-authentication-outcomes-for"></a>

<a id="authentication-contract"></a>

<a id="accepted-authentication-outcomes-for-116"></a>

### Accepted authentication outcomes for

The implemented [consent API](../../.agents/skills/inframeld-access-models/references/human-cli-consent.md#human-oauth-consent) has an explicit precedence rule. After HTTP credential selection and POST CSRF, unsupported Hydra client/access returns 403 before browser verification, including when the supplied cookie is invalid. Supported requests keep the usual invalid-session 401, policy-denial 403 and unavailable-dependency 503 outcomes. This ordering initializes no credential state for unsupported requests.

The [Access dispatch contract](../../.agents/skills/inframeld-access-models/references/credential-dispatch.md#credential-dispatch) selects one verifier before provider I/O. The following extension was accepted on 2026-10-04. Human cookie/bearer dispatch, verification adapters, the `invalid_authentication_request` catalogue entry and route declarations now have inspected implementation, described in [Access](../../.agents/skills/inframeld-access-models/references/credential-dispatch.md#implemented-human-authentication). Application-key authentication and complete account-UI/CLI/recovery production qualification remain unfinished. This status correction reports source inspection, not tests rerun here:

| Status | Condition | Public problem contract |
| --- | --- | --- |
| 400 | Malformed Authorization header syntax, duplicate Authorization headers or competing Kratos session cookie and Authorization | New accepted code `invalid_authentication_request`, with the exact reviewed definition below. Reject before provider I/O. |
| 401 | Missing, invalid, expired, revoked or route-unsupported credential family | Preserve the existing generic `http_error` problem body. Supply an appropriate trusted Bearer challenge when applicable. |
| 403 | Verified human or application is locally ineligible, including an unadmitted/recovery-blocked human or blocked application/account/project. Or an authenticated principal has the wrong kind or lacks the requested action | Preserve existing safe authentication/permission problem mappings. No token or protected-account detail in the body. |
| 404 | Missing resource or resource hidden from this caller under the ordinary visibility rule | Preserve hidden-resource semantics. A visible resource with denied action instead returns 403. |
| 409 | Stale reviewed revision or conflicting use of an idempotency key | Preserve existing stale-state/idempotency problem mappings. Never turn conflict into a fresh mutation. |
| 422 | Invalid request fields | Preserve the existing bounded validation problem contract. |
| 503 | Required provider verification is unavailable or its response cannot be validated | Preserve the existing safe authentication 503 body. Do not admit stale/cached success. |

A malformed complete credential value with otherwise valid header syntax is a failed credential (401), rather than a malformed request (400). Invalid credential bindings, expiry and revocation likewise return 401. A verified application credential still cannot admit a currently ineligible account/project (403). Application keys at the human-session operation are an unsupported family (401). A verified application at an ordinary human-only operation fails principal eligibility (403). No failed verifier falls back to another family.

The new 400 definition uses these accepted literal values, within the existing `ProblemDetails` representation:

| Field | Value |
| --- | --- |
| `type` | `https://github.com/matejpalenik/inframeld/blob/main/docs/development/error-handling.md#invalid-authentication-request` |
| `title` | `Invalid authentication request` |
| `status` | `400` |
| `code` | `invalid_authentication_request` |
| `detail` | `Use one supported authentication method with correctly formatted credentials.` |

<a id="invalid-authentication-request"></a>

<a id="invalid-authentication-request-and-trusted-challenges"></a>

#### Invalid authentication request and trusted challenges

`requestId` remains the generated correlation ID matching `X-Request-ID`. Omit `instance` and validation-only `errors`. This definition is accepted design and is implemented by [the problem catalogue](../../apps/backend/src/inframeld_backend/shared/http/definitions/problem_catalogue.py). Source presence does not qualify every authentication lifecycle. Existing 401/403/503 problem bodies and codes remain unchanged.

Use realm `inframeld` for applicable Bearer challenges. A missing credential receives `WWW-Authenticate: Bearer realm="inframeld"` without an `error` attribute. A failed bearer credential receives `Bearer realm="inframeld", error="invalid_token"`. For a malformed/competing Bearer authentication request, use `Bearer realm="inframeld", error="invalid_request"` with the 400 response where that Bearer challenge applies. Keep challenge production with the authentication adapter, not the shared problem handler.

[RFC 6750](https://www.rfc-editor.org/rfc/rfc6750.html#section-3) supplies the Bearer error meanings. Inframeld's problem `code` is a separate vocabulary. Local grants are not OAuth scope strings: do not manufacture `insufficient_scope` challenges for ordinary product authorization denial. Do not copy provider error text into problems or treat a 403 as a refresh/identity-fallback instruction. Route declarations and runtime challenge behavior still need qualification alongside the new adapters.

<a id="problem-catalogue"></a>

## Problem catalogue

The named problem definitions below retain their type fragments and exact public wording. Append each heading's fragment to this fixed `TYPE_PREFIX`:

```text
https://github.com/matejpalenik/inframeld/blob/main/docs/development/error-handling.md
```

Keep these identities stable if the documentation moves. They become published when merged. The server does not fetch them while handling a request.

<a id="validation-error"></a>

### Validation error

**422 · `validation_error` · `#validation-error`**  
Title: **Request validation failed**  
Detail: **One or more request fields are invalid.**

For FastAPI `RequestValidationError`, with sanitized `errors`. The initial project convention includes malformed JSON in this 422 category.

<a id="invalid-input"></a>

### Invalid input

**422 · `invalid_input` · `#invalid-input`**  
Title: **Invalid input**  
Detail: **The supplied input is not valid for this operation.**

For supported application input rejections. Do not include a raw Pydantic error list.

<a id="resource-not-found"></a>

### Resource not found

**404 · `resource_not_found` · `#resource-not-found`**  
Title: **Resource not found**  
Detail: **The requested resource is not available.**

Does not reveal resources outside the caller's permitted scope.

<a id="access-denied"></a>

### Access denied

**403 · `access_denied` · `#access-denied`**  
Title: **Access denied**  
Detail: **You are not allowed to perform this operation.**

Represents an already-made permission decision, not authentication.

<a id="conflict"></a>

### Conflict

**409 · `conflict` · `#conflict`**  
Title: **Operation conflicts with current state**  
Detail: **The operation cannot be completed in the current state.**

The caller must resolve the state conflict. Repeating the same request is not automatically useful or safe.

<a id="stale-revision"></a>

### Stale revision

**409 · `stale_revision` · `#stale-revision`**\
Title: **Revision is no longer current**\
Detail: **Reload the current state before making a new change.**

A new command supplied an expected revision that another accepted change has advanced. The caller must reload the current state and make a fresh decision. A retry with the original idempotency key instead recovers the original operation. It does not become a new stale command.

<a id="idempotency-key-reused"></a>

### Idempotency key reused

**409 · `idempotency_key_reused` · `#idempotency-key-reused`**\
Title: **Idempotency key reused**\
Detail: **This key was already used for a different request.**

The caller reused a key within the same request scope for different meaningful input. The original reservation remains authoritative. A different intended operation needs a new key. Do not include request bodies or fingerprints in the public response.

<a id="idempotency-in-progress"></a>

### Idempotency in progress

**409 · `idempotency_in_progress` · `#idempotency-in-progress`**\
Title: **Operation in progress**\
Detail: **The original request is still in progress.**

The response includes the original `operationId` and a `Retry-After` header. The caller may retry with the same key after that delay. An accepted asynchronous job instead replays its original `202` and job identity.

<a id="dependency-unavailable"></a>

### Dependency unavailable

**503 · `dependency_unavailable` · `#dependency-unavailable`**  
Title: **Dependency unavailable**  
Detail: **A required service is unavailable.**

For an identified availability failure. No generic `retryable` flag or invented `Retry-After` header.

<a id="internal-error"></a>

### Internal error

**500 · `internal_error` · `#internal-error`**  
Title: **Internal server error**  
Detail: **An unexpected error occurred.**

For unexpected or unmapped failures. Report safe diagnostics with the request ID.

<a id="generic-http-error"></a>

### Generic HTTP error

Use `type: "about:blank"`, `code: "http_error"`, the actual error status, its HTTP status phrase as the title, and fixed safe detail selected by status. This includes native router 404/405 responses. Do not automatically echo `HTTPException.detail`.

Preserve trusted protocol headers such as `Allow`, an appropriate `WWW-Authenticate` challenge, and an intentionally supplied `Retry-After`. The authentication producer supplies the challenge. The shared handler does not invent one.

[rfc9457]: https://www.rfc-editor.org/rfc/rfc9457.html
[python-errors]: https://docs.python.org/3/tutorial/errors.html
[python-cancellation]: https://docs.python.org/3/library/asyncio-exceptions.html
[litellm-errors]: https://docs.litellm.ai/docs/exception_mapping
[fastapi-responses]: https://fastapi.tiangolo.com/advanced/additional-responses/

<a id="stable-domain-error-mapping"></a>

## Stable domain-error mapping

The owning service translates a recognized business rejection to a stable application failure. The HTTP boundary maps that failure through the implemented catalogue. Unexpected errors keep the generic internal problem. See [HTTP error translation](../../.agents/skills/inframeld-application-contracts/references/http-errors.md).
