# Model contract examples

Alice creates `company-gateway`, then reviews settings for its private alias `private/Chat-A`. Saving the connection creates a stable Project resource. Saving model settings configures a consumer. Only an accepted call can establish applicable validation evidence.

The backend [model records](../../../../apps/backend/src/inframeld_backend/shared/application/dtos/model_metadata_dto.py) define typed metadata and effective settings. [#246](https://github.com/matejpalenik/inframeld/issues/246) implements connection creation, inspection and exact grants in native HTTP and the generated clients. [#32](https://github.com/matejpalenik/inframeld/issues/32) owns credential management. [#247](https://github.com/matejpalenik/inframeld/issues/247) and [#248](https://github.com/matejpalenik/inframeld/issues/248) own the remaining connection access and retirement workflows.

## Create and inspect a connection

| Method and path | Operation ID | Successful result |
| --- | --- | --- |
| `POST /v1/projects/{project_id}/model-connections` | `createModelConnection` | 201 original creation receipt |
| `GET /v1/projects/{project_id}/model-connections` | `listModelConnections` | 200 page of permitted current connections |
| `GET /v1/projects/{project_id}/model-connections/{model_connection_id}` | `getModelConnection` | 200 current connection |
| `GET /v1/projects/{project_id}/model-connections/{model_connection_id}/usage` | `listModelConnectionUsage` | 200 page of permitted consumer usage observations |

Use UUIDs for path identities and flat UUIDs in native HTTP representations. Application contracts wrap these as `ProjectId` and `ModelConnectionId`. Map operation IDs as opaque strings. The typed name is a Project selector and must follow the [ordinary Name rules](../../inframeld-architecture/references/resource-names-and-identity.md). The strict creation request requires `name`, `displayName` and one complete `access` object. The object contains the supported `provider`, exact `baseUrl` including any base path, nullable `apiVersion` and supported `authentication`. The pair of provider and authentication determines which fields and combinations are valid. Apply destination policy before activation and again at dispatch. Reject unsupported settings, extra fields, credential input and a consumer's settings at this route. Use one `Idempotency-Key`, the current credential and CSRF boundary, existing Problem Details, and private no-store responses.

The creation operation requires `apiVersion: null`. `openai` requires `api-key` and the approved `https://api.openai.com/v1` base URL. `openai-compatible` requires `api-key` and an exact deployment-approved HTTPS base URL. `ollama` requires `none` and an exact literal loopback HTTP base URL approved separately for local Ollama. Creation checks the configured values before saving. It performs no DNS resolution, credential exchange or provider request.

A creation request for the protected OpenAI-compatible profile can look like this:

```json
{
  "name": "company-gateway",
  "displayName": "Company gateway",
  "access": {
    "provider": "openai-compatible",
    "baseUrl": "https://models.example.test/v1",
    "apiVersion": null,
    "authentication": "api-key"
  }
}
```

A permitted current connection read and each connection-list item have this shape:

```json
{
  "projectId": "00000000-0000-0000-0000-000000000001",
  "modelConnectionId": "00000000-0000-0000-0000-000000000002",
  "name": "company-gateway",
  "displayName": "Company gateway",
  "access": {
    "provider": "openai-compatible",
    "baseUrl": "https://models.example.test/v1",
    "apiVersion": null,
    "authentication": "api-key"
  },
  "connectionAccessRevision": 0,
  "credential": { "present": false, "revision": 0 }
}
```

The 201 response has `connection` containing this original snapshot, `operationId`, `idempotencyExpiresAt`, `projectAccessRevision`, and `initialGrants`. Each initial grant has `target: {kind: "model-connection", modelConnectionId}`, `actionId` and literal `canGrant: true`. The four action IDs are `view-model-connection-configuration`, `use-model-connection`, `manage-model-connection` and `delete-model-connection`, all with `canGrant: true`. #246 commits creation, assignments, revision, audit and receipt together under the current human Project `create-model-connections` action. It makes no provider request. Completed replay checks current authority and returns the original receipt, including its original assignments and status. An assignment removed later stays removed.

Both list routes use the existing `limit` (default 25, range 1 to 100) and optional opaque `cursor`. They return `{ "items": [...], "nextCursor": null }` on their last permitted page. Scope a cursor to the exact Project, query, and connection when applicable. Reauthorize each page. Current Project membership and the exact permitted connection configuration determine what the connection routes can show. The delivered usage route checks current connection visibility and returns `{ "items": [], "nextCursor": null }` until consumer owners persist real usage. It issues no continuation cursor in that state. When a consumer supplies the facts and the caller can view them, an item can look like this:

```json
{
  "items": [
    {
      "consumerKind": "pipeline-version",
      "consumerId": "00000000-0000-0000-0000-000000000003",
      "role": "generation",
      "model": "private/Chat-A",
      "latestAttempt": {
        "outcome": "failed",
        "source": "real-use",
        "connectionAccessRevision": 7,
        "credentialRevision": 3,
        "observedAt": "2026-11-13T12:00:00Z"
      },
      "lastValidation": {
        "status": "validated",
        "source": "preflight",
        "connectionAccessRevision": 7,
        "credentialRevision": 3,
        "observedAt": "2026-11-13T11:00:00Z"
      }
    }
  ],
  "nextCursor": null
}
```

`latestAttempt` and `lastValidation` are independently nullable when their evidence is unavailable for disclosure. The latest attempt records `accepted`, `failed` or `uncertain`, with source `preflight` or `real-use`. A failed first attempt can have a null last validation, while a later failure can coexist with an earlier accepted result. `validated` requires accepted evidence for that exact current selection. A stale permitted historical observation can carry `status: "stale"` and keeps its original revisions and time. These facts establish neither current health nor validation of other consumers. Empty `items` means the caller received no permitted items. It cannot authorize a deletion or imply absence of hidden references. Return no total or completeness flag. Resolve all IDs within the authoritative Project and use safe unavailable-resource errors.

The [exact #246 grant routes](https://github.com/matejpalenik/inframeld/issues/246) remain:

| Method and path | Operation ID |
| --- | --- |
| `GET /v1/model-connections/{model_connection_id}/grants` | `listModelConnectionActionGrants` |
| `PUT /v1/model-connections/{model_connection_id}/grants/{recipient_principal_id}/{action_id}` | `setModelConnectionActionGrant` |
| `DELETE /v1/model-connections/{model_connection_id}/grants/{recipient_principal_id}/{action_id}` | `removeModelConnectionActionGrant` |
| `GET /v1/projects/{project_id}/grant-recipients?targetKind=model-connection&targetId=...&actionId=...` | `listProjectGrantRecipients` |

## Manage a provider credential

The `/credential` suffix extends `/v1/projects/{project_id}/model-connections/{model_connection_id}`. All three operations require current human Manage on that exact connection. Each successful response is private metadata with `Cache-Control: no-store`.

| Method | Operation ID | Input |
| --- | --- | --- |
| `GET` | `getModelConnectionCredential` | Project and connection path IDs |
| `PUT` | `putModelConnectionCredential` | `Idempotency-Key` and a JSON body with `expectedCredentialRevision` and write-only `value` |
| `DELETE` | `removeModelConnectionCredential` | `Idempotency-Key` and the `expectedCredentialRevision` query parameter |

The metadata contains `projectId`, `modelConnectionId`, `credentialId`, `revision`, `present`, and `changedAt`. A never-written slot has revision 0, `present: false`, and null identity and timestamp. An authorized removal retains the slot identity and advances its revision while clearing the encrypted value.

Mutations return `credential` metadata with `changed`, `replayed`, `operationId`, and `idempotencyExpiresAt`. Repeat the original protected request after a lost acknowledgment. The retained result describes the original revision and presence, with `replayed: true`. Saving and removal make no provider call. The [credential storage reference](../../inframeld-access-models/references/provider-credential-storage.md) owns input bounds and root-key setup.

## Review current access and retire safely

The following suffixes extend `/v1/projects/{project_id}/model-connections/{model_connection_id}`.

| Method and suffix | Operation ID | Request and successful result |
| --- | --- | --- |
| `POST /access/review` | `reviewModelConnectionAccess` | Complete proposed `access`, `expectedConnectionAccessRevision` and `expectedCredentialRevision`. Returns exact revisions, current and proposed access, `reviewId`, and `requiresLiveImpactAcknowledgment`. |
| `GET /access/reviews/{review_id}/impact` | `listModelConnectionAccessImpact` | Bounded cursor request. Returns only permitted `{consumerKind, consumerId, displayName}` items and `nextCursor`. |
| `PUT /access` | `updateModelConnectionAccess` | Repeat the reviewed access and expected revisions, with `reviewId`, a matching `liveImpactAcknowledgment` when required and a `credentialTransition`. Returns a 200 safe original outcome. |
| `DELETE` at the connection path | `deleteModelConnection` | No body. Query requires `expectedConnectionAccessRevision` and `expectedCredentialRevision`. Returns a 200 safe original retirement receipt. |

Review checks the current human `manage-model-connection` action, destination, compatibility and complete relevant dependencies without calling the provider. `reviewId` is an opaque binding to the exact proposal, identity, revisions and relevant dependency state. Its storage and encoding belong to #247. `liveImpactAcknowledgment` must explicitly repeat that reviewed identity when needed. The response may require acknowledgment without revealing why a particular consumer was included. It never reports hidden names, counts or a complete view of impact.

For example, Alice moves revision 7 to a different origin. In this request fragment the credential value is illustrative and would enter only through protected input:

```json
{
  "expectedConnectionAccessRevision": 7,
  "expectedCredentialRevision": 3,
  "reviewId": "reviewed-proposal-reference",
  "liveImpactAcknowledgment": "reviewed-proposal-reference",
  "access": {
    "provider": "openai-compatible",
    "baseUrl": "https://new-models.example.test/v1",
    "apiVersion": null,
    "authentication": "api-key"
  },
  "credentialTransition": { "kind": "replace", "value": "<protected input>" }
}
```

The closed transitions are `{"kind":"preserve"}` for the same approved authentication binding, `{"kind":"replace","value":"…"}` for explicit destination-bound provision, and `{"kind":"clear"}` for a permitted credential-free configuration. Use strict tagged input and reject extra fields. Never copy the stored key to a changed destination. Use #32's protected input and secret-bearing request fingerprint boundary. A changed body under the same key conflicts without leaking its bytes. Only safe presence/revision information can leave the operation. Standalone rotation and removal remain separate #32 operations.

The short activation transaction rechecks current authority, proposal, revisions, relevant dependency state and the Indexing compatibility decision under the shared liveness gate. When a retained embedding profile exists, the same alias, 1,536 dimensions and a successful probe at the new origin still leave compatibility unproven. Unknown or incompatible vector meaning refuses both access and credential changes. Supported identity evidence from Indexing can establish compatibility for the relevant dependencies. A new executable or retained dependency admitted after review can stale it. The client cannot override a refusal. A successful update returns `{projectId, modelConnectionId, operationId, idempotencyExpiresAt, outcome, connectionAccessRevision, credential}`, where `outcome` is `updated` or `unchanged`. A no-op advances no access revision. Historical restoration submits a fresh current proposal through the same review and cannot recover an old secret.

Deletion checks the exact current human `delete-model-connection` action and rechecks revisions, the empty credential slot and complete dependency state in the same gate. It can be delivered without #247's impact review. The caller can separately inspect #246 usage when authorized. A review ID or management authority is unnecessary for retirement. A retained PipelineVersion or active work can block deletion even when it was absent from the caller's usage page. Unknown dependency state also blocks deletion. If concurrent reference admission wins the gate, retirement refuses. If retirement wins, the permanent retired ID cannot accept that reference. Retain minimal non-executable call/accounting/audit attribution and the permanent non-content retired ID. Deletion does not revoke a provider key or cascade into consumers.

Both mutations use one `Idempotency-Key`. A stale review, denied authority or incompatible dependency uses the existing safe Problem Details boundary. An empty visible impact page never authorizes a write. After a lost response, check current eligibility and safe-result disclosure for the same original operation. Recover the original safe receipt before applying fresh live-object, revision or dependency checks. Those checks protect a new mutation. A retirement receipt has `{projectId, modelConnectionId, operationId, idempotencyExpiresAt, outcome: "retired"}`. Replaying it neither retires again nor admits work against the retired ID.

## Compare metadata, settings and actual observations

A bounded gateway read uses the exact selected Project, connection, access revision, provider, model and role. It resolves current authority, destination and credential, uses its owner's existing deadline and response-size bounds, and sends only the identifiers needed by its supported adapter. It has no universal discovery route and performs no inference. A timeout or unavailable optional property yields safe unavailable information. Consumers still need required execution facts from supported reviewed input or qualified evidence.

Each property has an explicit state. These are example native JSON property values using the application field names:

```json
{ "state": "unknown" }
```

```json
{
  "state": "conflict",
  "alternatives": [
    {
      "state": "known",
      "value": 131072,
      "source": {
        "kind": "catalogue",
        "reference": "pinned-model-catalogue",
        "revision": "2026-11-01",
        "observed_at": "2026-11-13T12:00:00Z"
      }
    },
    {
      "state": "known",
      "value": 32768,
      "source": {
        "kind": "selected-server",
        "reference": "gateway-metadata-adapter",
        "revision": "1.2",
        "observed_at": "2026-11-13T12:00:00Z"
      }
    }
  ]
}
```

An unambiguous qualified selected-server value can prefill 32,768 while retaining both alternatives. Alice can save her supported 32,768 value even without discovery. Refresh presents property differences and leaves effective settings and previous observations intact. Review records the exact adopted source for a suggested property. Other effective values, including an explicitly provider-controlled temperature, came from reviewed input. Explicit price overrides have their own category/unit rates and stay distinct from qualified prices. The selected alias keeps its exact case and can have different meaning on another connection. A generic token-count guess cannot provide a pinned exact or conservative upper bound. A missing required bound or embedding meaning leaves the settings incomplete. A selected-server pricing observation may carry exact category/unit rates or an explicitly qualified local no-external-charge observation. Use the native [generation settings input](../../../../apps/backend/src/inframeld_backend/shared/http/requests/generation_model_settings_request.py) and [price-rate input](../../../../apps/backend/src/inframeld_backend/shared/http/requests/model_rate_request.py) to parse exact decimal strings before mapping to the application. They reject JSON numbers to avoid binary rounding. A typed zero rate, catalogue entry or display label cannot certify that the selected server is local or free. #122 estimates and #123 applies the separate conservative admission/accounting rule.

Role settings are tagged as `generation`, `embedding` or `reranking`. All have reviewed context and qualified token-bound inputs. `context_tokens` is the combined cap. The owning adapter must establish any separate input ceiling and output accounting semantics before dispatch. Generation includes the output limit, explicit or provider-controlled temperature, and whether structured output is required. Embedding freezes the expected provider, selected model identity and supported model revision where known, dimensions, normalization, metric and exact document/query prefixes. Hosted reranking includes its candidate limit. The consumer and adapter qualify support before use. The stable consumer selection uses the connection ID. The observed provider and access revision belong to each metadata snapshot and call outcome. Gateway evidence records actual call/operation identity, outcome, access/credential and adapter revisions, time and safe observed facts. A failed or uncertain call can retain observed usage but cannot validate a selection. An accepted embedding result checks the expected shape. It never changes the profile.

## Preserve portable meaning

The model fragment of a complete configuration contains effective settings and a typed connection Name. This native JSON round-trip example describes the meaning that #151's complete TOML schema must preserve.

```json
{
  "connection_name": "company-gateway",
  "model": "private/Chat-A",
  "effective": {
    "context_tokens": 32768,
    "token_bound": {
      "kind": "exact",
      "implementation": "gateway-tokenizer",
      "revision": "v4"
    },
    "settings": {
      "role": "generation",
      "output_tokens": 1024,
      "temperature": null,
      "structured_output": false
    }
  }
}
```

`temperature: null` means explicitly provider-controlled. A decimal string `"0"` means an explicit zero. The full Pipeline definition also preserves prompt bytes, including spaces and newlines. Resolve the Model Connection Name to an exact destination ID before semantic comparison. A same-name mismatch requires deliberate destination remapping or an authorized owner update. Equal effective meaning requires the resolved destination binding, exact model, complete supported role settings and exact prompt. Labels and suggestion provenance can remain explanatory metadata. Credentials, current access revisions and validation/call history are excluded from the portable role settings.

[Focused backend cases](../../../../apps/backend/tests/unit/shared/application/dtos/test_model_contracts.py) exercise explicit state tags, sourced conflicts, positive limits, private alias scope, revision-specific evidence and explicit-zero/unset round trips. Strict parsing refuses unknown tags, credential fields, missing required settings and invalid integer types.
