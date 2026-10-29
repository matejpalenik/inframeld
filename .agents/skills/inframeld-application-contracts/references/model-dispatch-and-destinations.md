# Dispatch through the enforced model boundary

SupportBot calls a configured model while connection access or credentials change. The application must enforce the actual destination and current binding for each call, including nested library work and uncertain responses.

<a id="a-recorded-alias-is-not-proof-of-an-unchanged-external-model"></a>

### A recorded alias is not proof of an unchanged external model

Record the resolved model revision when the provider exposes it, and pin model revisions where supported.

An external gateway can change what an alias points to. The saved alias proves what Inframeld requested, not that the external model stayed unchanged. Keep that limit on reproducibility visible.

## Approved outbound enforcement

The accepted [PD-CONTRACTS-01](decision-gateway-enforcement.md#approved-resolution) combines a controlled embedded transport and supported host/network egress enforcement. Every model, metadata, probe, reranker and nested call uses an explicitly mapped and qualified adapter path. Actual resolved routes must match permitted destinations. Connection reuse remains bound to the approved origin and route. Reject unsupported bypasses before dispatch.

The initial profile disables automatic redirects, ambient proxies/credentials, router fallbacks and independent SDK/library retries. Preserve verified HTTPS/custom CAs, explicitly allowlisted private routes and the existing credential-free local Ollama HTTP exception. Known not-sent, known response/failure and uncertain dispatch remain distinct. A timeout or cancellation after a possible send never authorizes redispatch. Implementation and hostile-endpoint qualification remain pending.

<a id="approve-and-validate-a-destination"></a>

<a id="destinations"></a>

<a id="2-approve-and-validate-a-destination"></a>

## Approve and validate a destination

Custom endpoints could otherwise let a caller make the server contact arbitrary addresses. This is **server-side request forgery (SSRF)**. Approval and destination checks prevent a model request from becoming unrestricted network access.

There are two distinct configuration responsibilities:

| Who | What they may configure |
| --- | --- |
| **Deployment administrator** | Approves the allowed endpoint origins through deployment configuration. |
| **Human with the required project permission** | Creates a connection within that deployment policy. A project connection cannot expand it. |

A query or evaluation chooses an already configured connection. It cannot supply its own endpoint URL.

The same rule applies to [direct Pipeline queries](../../inframeld-pipelines/references/direct-queries.md#preview). Temporary overrides select authorized connection identities and model settings for that execution only. They neither edit shared access settings, rotate credentials nor save the Pipeline's working configuration. Observe current access revisions at admission and check them at dispatch as described below. Missing access, incompatible embedding semantics or unavailable required reranking fails visibly. Direct querying is not an unrestricted model proxy, and success remains narrowly scoped validation evidence rather than publication authority.

This permits approved private customer gateways without giving ordinary users unrestricted network access.

<a id="validate-both-the-configured-url-and-the-actual-destination"></a>

### Validate both the configured URL and the actual destination

| Boundary | Required behavior |
| --- | --- |
| **URL structure** | Validate the scheme, hostname, port, and normalized base path. Also validate the actual destination, not just the displayed URL. |
| **Remote transport** | Require TLS certificate verification. TLS protects the connection and verifies the endpoint's certificate. Mount a customer certificate authority (CA) when its private service requires custom trust. Do not disable verification. |
| **Local HTTP exception** | Explicitly operator-approved local Ollama over HTTP is allowed only without a provider credential or other authentication secret. Never attach a saved key or authorization header to this cleartext connection. If authentication is needed, create an approved HTTPS connection with certificate verification. This exception does not permit unverified remote endpoints. |
| **Credentials in URLs** | Reject URL user-info, such as an embedded username/password, and credential-bearing query strings. |
| **Redirects** | Disable automatic redirects in the initial supported profile. Configure the final endpoint explicitly. |
| **Forbidden destinations** | Reject link-local and cloud-metadata addresses. These are not made acceptable merely by supporting private endpoints. |
| **Private networks** | Permit private address ranges only through explicit deployment allowlisting. A blanket ban on private addresses would prevent the approved customer-gateway use case. |
| **Caller-controlled proxies** | Do not accept arbitrary proxy settings from API callers. |
| **DNS and network routing** | Revalidate destinations resolved through the Domain Name System (DNS), and enforce the permitted route through host/network egress restrictions. |

Checking the hostname once is insufficient because it may resolve to another address later. Application validation and host/network restrictions must enforce the permitted destination together.

<a id="resolve-a-credential-for-each-call"></a>

<a id="dispatch"></a>

<a id="5-resolve-a-credential-for-each-call"></a>

## Resolve a credential for each call

Saving or replacing a key sends plaintext through HTTPS to the API. TLS protects it in transit. The API encrypts it before storage, returns safe metadata only, and Studio clears the submitted value.

A TLS-terminating reverse proxy handles plaintext too. Exclude credential routes from request-body and header capture. The design does not claim that infrastructure processes never see the submitted value.

For model use, the API or worker follows this path:

```text
Admitted build, query, or evaluation
    -> Resolve the selected connection ID and its current access revision
        -> Check admitted-work revision and model compatibility
            -> Check the current credential state
                -> Decrypt inside the credential adapter
                    -> Dispatch through ModelGateway to the approved destination
                        -> Record safe actual access/model/credential observations
```

Resolve the key separately for each limited call. Avoid long-lived plaintext caches and unnecessary copies. Python cannot guarantee immediate erasure of every memory byte when a call finishes, so do not claim that guarantee.

<a id="dispatch-freshness"></a>

<a id="observe-current-settings-without-mixing-an-admitted-operation"></a>

### Observe current settings without mixing an admitted operation

New work observes current access revisions for its selected connections at admission. Before each relevant model dispatch, compare those observations with current committed state. A changed access revision blocks the remaining dispatches in that query, preparation, starter-generation or evaluation operation. Do not use the historical revision, silently restart against the new one, or mix responses from different access configurations into a supposedly fixed result. The user admits new work after reviewing the current settings. Metadata rename and credential-only rotation are separate: resolve the current usable credential for each call without restarting solely because its revision changed.

This is an operation precondition, not consumer pinning: an operation may stop when its observed revision is no longer current, but cannot request that old configuration. Queued jobs and resumed attempts obey the same rule. API and worker processes must not keep serving stale cached access settings after a successful freshness check. Qualification must establish the actual read/cache/dispatch boundary.

A call already sent may complete after an update and remains attributed to the revision actually used. No distributed transaction can retract that request. Recheck before any subsequent model call. Current permission and erasure checks still apply before disclosure. A final already-sent call may yield an accurately attributed result, but it cannot validate the newer revision or certify that a changed evaluation environment is still comparable. Preserve completed units and uncertainty rather than creating automatic paid retries. [Evaluation](../../inframeld-evaluation/references/gateway-and-jobs.md#connection-consistency) specifies run/comparison outcomes.

Check the transport again before dispatch. Reject a local HTTP call if it would carry a saved provider credential or another authentication secret, even if the connection was previously approved. A credential-free local endpoint may still be used through the narrow HTTP exception.

Keep keys out of provider debug output, exception messages, and traces. Jobs carry connection references. Plaintext never belongs in Pipeline or profile snapshots, benchmark or evaluator revisions, logs, evaluation evidence, answer receipts, or API responses.

<a id="check-removal-at-the-dispatch-boundary"></a>

### Check removal at the dispatch boundary

A wrong encryption key or altered encrypted record blocks dispatch. Removing the credential before the final resolution check also blocks a new call.

Removing it after dispatch cannot undo that call. The local database and remote provider do not participate in one transaction.

<a id="fail-explicitly-and-keep-retry-decisions-in-one-place"></a>

### Fail explicitly and keep retry decisions in one place

**A missing credential or provider failure must never trigger automatic fallback to another provider or model.** The selected connection and model are part of the requested behavior, not optional hints.

If a replacement is invalid, old evidence remains intact and new calls fail explicitly. Removing a required key has the same effect.

Follow the shared [retry policy](jobs-and-recovery.md). Disable independent library retries that could repeat a call whose response was lost after the provider may already have executed it.

A library doing the retry does not make it safe. Application and evaluation code must use the same central decision about whether work may repeat.

<a id="make-the-actual-data-path-visible"></a>

### Make the actual data path visible

Show the actual connection, operation, and outgoing data path, even when the customer manages the gateway.

| Activity | Data path that must be disclosed |
| --- | --- |
| **Build an index using OpenAI embeddings** | Newly embedded chunk text is sent to OpenAI. Across the build, this may cover the whole corpus, the selected body of documents. |
| **Ask a question** | The question is sent for embedding. Selected permitted excerpts and instructions are sent to the configured generation endpoint. |
| **Generate starter cases** | The frozen permitted passage sample and bounded persona guidance go to the selected generator through `ModelGateway`. Disclose extraction and synthesis calls before admission. |
| **Run the faithfulness judge** | The question, answer, and exact final generation context go through `ModelGateway` for claim extraction and support judgments. [Evaluation](../../inframeld-evaluation/references/metrics-and-evidence.md#metrics) defines inputs and failures. Disclose these separately from starter generation. Never add reference answers as supporting evidence. |
| **Store and search in Chroma** | Chroma receives embeddings and the configured chunk text/metadata. Local Chroma keeps them on the self-hosted server. Future Chroma Cloud is a separate external processor. |
| **Use a local model endpoint** | Model processing stays within the configured local environment. Identity setup or model-asset setup may still involve network activity. |

A local model alone does not establish “no egress” for the whole installation. The claim must match the actual operation, including any network activity elsewhere.

The local processing ports described earlier do not change this rule: any future remote processing must disclose its own data path.
