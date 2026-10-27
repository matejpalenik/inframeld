# Human and application session contracts

Alice checks who the backend recognizes before asking a protected question. A session result identifies a verified local principal. It does not freeze account state, grants or document access.

> **Status:** Human session is implemented. The separate application check is accepted design, not a delivered route.

<a id="transport-mapping"></a><a id="session-contracts"></a>

## Operations and current authority

| Operation | Supported credential | Result and status |
| --- | --- | --- |
| `GET /v1/session`, `getCurrentSession` | Kratos cookie or Hydra human bearer, selected once | Implemented `CurrentSessionResponse`, only `principalId`, 200. |
| `GET /v1/application-session`, `getCurrentApplicationSession` | Application-key bearer for the bound HTTP audience/adapter | Accepted `CurrentApplicationSessionResponse` design, only `principalId` and `projectId`, 200 when implemented. |

The implemented [CurrentSessionResponse](../../../../apps/backend/src/inframeld_backend/access/http/responses/current_session_response.py), [route](../../../../apps/backend/src/inframeld_backend/access/http/routes/current_session_routes.py) and [native OpenAPI](../../../../contracts/openapi/v1/inframeld-v1.json) own the delivered human representation. Keep its operation ID and fields unchanged.

Both checks require `Cache-Control: no-store`, the ordinary server-generated `X-Request-ID` and UUID-string resource IDs. Neither returns a status/permission snapshot, probes a model or writes local access. A later protected operation performs its own current authorization.

## Separate application-check design

**Design notation, not production implementation.** This is the documented complete response shape. UUID means its JSON string representation.

```python
from typing import TypedDict
from uuid import UUID

class CurrentApplicationSessionResponse(TypedDict):
    principalId: UUID
    projectId: UUID
```

A response with permissions, account status or another selected Project would violate this shape. Full key verification, expiry/revocation, installation/audience/adapter and current account/Project checks remain mandatory. A public prefix or key-ID lookup is not authentication. [PD-ACCESS-01](decision-key-currentness.md) still gates unresolved verifier inputs and currentness coordination.

<a id="session-checks"></a><a id="session-responses-and-authentication-budgets"></a>

## Bounded authentication

| Configurable budget | Accepted default | Scope |
| --- | --- | --- |
| One required provider call | Five seconds | At most the smaller of this budget and time remaining in the total. |
| Complete backend authentication | Ten seconds | Provider verification and current local identity/eligibility read. |
| CLI session-check HTTP request | Fifteen seconds | Backend authentication plus transport. Still unfinished CLI implementation/qualification. |

The cookie and bearer services enforce total deadlines through [HumanAuthenticationSettings](../../../../apps/backend/src/inframeld_backend/access/infrastructure/settings/human_authentication_settings.py). `INFRAMELD_HUMAN_AUTHENTICATION__PROVIDER_TIMEOUT_SECONDS` and `INFRAMELD_HUMAN_AUTHENTICATION__TOTAL_TIMEOUT_SECONDS` accept finite positive values. Defaults are starting limits, not measured latency guarantees.

If Hydra takes four seconds and Kratos another four, only two remain for local lookup under the ten-second default. A late successful response cannot authenticate. Required verification timeout is 503, not permission to reuse an earlier success. No cross-request positive authentication cache, blind verification retry or verifier fallback follows.

Provider waits occur outside database sessions. After verification, use independent short local reads. [Human bearer authentication](../../../../apps/backend/src/inframeld_backend/access/application/services/human_access_token_authentication_service.py) owns its implemented sequencing.

## Failure families and route declarations

Declare each protected operation's supported credential families before implementation. Choose one family through [credential dispatch](credential-dispatch.md). The scheme `Bearer` is case-insensitive. Credentials use Authorization or the supported cookie, never a URL or request-body substitute. Cookies require the existing CSRF marker and trusted Origin for writes. Bearer writes do not invoke cookie-only CSRF.

Identity-specific session checks return 401 for an unsupported family. Ordinary product operations first authenticate supported credentials, then return 403 for a verified principal ineligible for a human-only action. Do not turn human-only operations into application permissions. Malformed/competing credentials fail before provider I/O. Required verification uncertainty is 503 without protected identity details.

Native `KratosSession` and `HumanBearer` security alternatives mean cookie or bearer. They do not permit sending both. Runtime credential selection must reject competition even though the OpenAPI alternatives cannot express that rule alone. Current 400/401 responses retain safe problem bodies and optional `WWW-Authenticate` headers. Public health/documentation remains public and credential-free.

<a id="sessions-and-preserved-command"></a>

## Neighboring implemented operations

The preserved `POST /v1/projects/{project_id}/grants` still exposes `assignProjectUseOnlyGrant`, its existing request/response names, 201, `create-access-groups` and `canGrant: false`. It is not the new full-administration API.

Consent GET/POST at `/v1/oauth/consent` retain `inspectHumanOAuthConsent` and `decideHumanOAuthConsent`. They are cookie-only, non-cacheable and accept independently verified identities before admission. POST uses CSRF and returns a checked continuation rather than tokens. Read [consent](human-cli-consent.md) for exact current code contracts and recovery/version ordering.

## Sources and limitations

[Browser sessions](browser-sessions.md) and [human CLI login](human-cli-login.md) explain identity verification. [Authentication problems](../../../../docs/development/error-handling.md#authentication-contract) own public challenges and safe wording. Generated clients must consume actual native OpenAPI, never the unimplemented application-check name as if it were published.

Human OAuth credentials require their configured API audience and official client/scope. Application keys retain separate audience/adapter restrictions. MCP retains its separate two-tool application-key profile. Session checks do not add human OAuth tools, provisioning or a paid connection test.
