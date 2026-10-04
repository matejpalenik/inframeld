# Connecting models and protecting provider credentials

Alice configures Support's model connection so the application can create search embeddings and generate answers. This guide explains where those calls may go, how the provider key is saved, and what changes when it is replaced. SupportBot can use an authorized query without being able to reveal that key.

[Access](access-control.md) owns permissions. The [supporting records](data-model.md#supporting-records) define connections, revisions, model roles, and the encrypted credential format.

Start with ModelGateway and approved destinations. Then follow saving a key, using it for a call, replacing it, and restarting with the same protected encryption key.

> **Design status:** These are accepted v1 boundaries. Route shapes and some size limits remain recommendations. The chosen adapters, credential storage, and security tests still need implementation and verification.

## Contents

| Reader’s question | Start here |
| --- | --- |
| What does ModelGateway own? | [1. One model boundary, several roles](#model) |
| What changes for every consumer when I edit a connection? | [Shared current connections](#shared-current) |
| Can a shared update invalidate stored embeddings? | [Compatibility before activation](#connection-compatibility) |
| How do private endpoints stay safe? | [2. Approve and validate a destination](#destinations) |
| Does working chat prove embeddings work? | [3. Validate the selected capabilities](#roles) |
| Where do suggested limits come from, and can I change them? | [Reviewed model metadata](#model-metadata) |
| Which credential authenticates a model call? | [Provider authentication](#provider-authentication) |
| Who may manage which secret? | [4. Save and replace a provider key](#credentials) |
| When can removal stop a call? | [5. Resolve a credential for each call](#dispatch) |
| What if shared access changes after work starts? | [Dispatch freshness](#dispatch-freshness) |
| What happens after a lost save response? | [6. Commit a change and its retry result together](#coordination) |
| What happens on restart or key loss? | [7. Protect the persistent encryption key](#root-key) |
| How do estimates and spending limits work? | [Costs and spending controls](#spending) |
| What needs security and adapter qualification? | [8. Maintainer checks](#maintainer-checks) |
| Why these choices, and what remains open? | [9. Decision and reference map](#decision-map) |

<a id="model"></a>

## 1. One model boundary, several roles

A **port** describes what the application needs from another component. An **adapter** supplies that capability using a library or service.

ModelGateway is Inframeld's port for generation and embeddings. Business modules pass application-defined requests and receive application-defined results, keeping provider clients outside their contracts.

| Operation | Required path |
| --- | --- |
| **Generate an answer to a user query** | Generation through `ModelGateway`. |
| **Embed a query for search** | Embeddings through `ModelGateway`. |
| **Embed document chunks while building an index** | Embeddings through `ModelGateway`. A chunk is a document excerpt prepared for retrieval. |
| **Generate answers during an evaluation** | Generation through `ModelGateway`. |
| **Generate starter evaluation cases** | Keyphrase extraction and synthesis through `ModelGateway`, using the explicitly selected generator connection. |
| **Run the v1 faithfulness judge** | Claim extraction and support judgments through `ModelGateway`, using the explicitly selected judge connection. |
| **Classify content using an LLM** | The same gateway rule applies whenever classification uses a large language model (LLM). |

The initial path is:

```text
Query, indexing, or evaluation use case
    -> ModelGateway: application-owned interface
        -> Embedded LiteLLM Python adapter
            -> Configured OpenAI, Ollama, or approved compatible endpoint
```

All roles use this interface, but may select different configured models and endpoints.

The initial adapter supports OpenAI, Ollama, and operator-approved OpenAI-compatible endpoints. Compatibility means implementing the relevant OpenAI-style operations, not every feature. A customer's enterprise gateway uses this same path.

LiteLLM runs as an embedded Python library. No separate LiteLLM Proxy service is required. Other adapters may implement ModelGateway, but application modules cannot bypass it.

Evaluation libraries must also use ModelGateway rather than create their own provider clients.

### Keep custom model access in OSS and local processing separate

The open-source product includes custom and private-network endpoints, customer language models, custom certificate-authority trust, customer-supplied keys (BYOK), and the core release workflow.

These work under Apache-2.0 without `/ee`, a licensing server, or a provider account funded by Inframeld. Future enterprise routing or administration features must not remove them from OSS.

### Not every model-related component is a remote LLM call

The selected Ettin 32M local cross-encoder uses a separate bounded Reranker interface to reorder retrieved excerpts by relevance. Explicit hosted reranking uses the same Reranker contract but dispatches through ModelGateway and embedded LiteLLM. [ADR-0056](../adr/ADR-0056-support-explicit-local-hosted-or-disabled-reranking.md) selects local, hosted or explicit none; no failure fallback is permitted. Exact provider/model support and local asset/resource behavior still need qualification.

Docling uses DocumentProcessor and Chunker to convert files and divide them into search excerpts.

Neither silently calls a remote language model. A future remote processor must explicitly describe which data leaves the installation and where it goes.

Keep the connection's access settings and replaceable secret separate from each consumer's model selection. A Pipeline keeps its selected connection identity and model parameters, but uses that connection's current approved access settings and usable credential under [ADR-0054](../adr/ADR-0054-use-shared-current-model-connections.md). This changes access-configuration pinning, not the requirement to send every remote model call through ModelGateway.

<a id="shared-current"></a>

### Operate one current connection, not several consumer-selected revisions

Alice uses `company-gateway` for Contracts and Support. Updating its supported access settings changes future calls from both Pipelines, including already released versions. It does not edit their prompts, change their selected model IDs, create versions or move Deployment pointers. Manual release mode controls Pipeline publication, not shared connection administration.

| Owner | Settings and identity |
| --- | --- |
| **Connection** | Stable project-owned ID, name/display name and one current supported provider/access configuration: endpoint/base path, provider API version and authentication method where applicable. No arbitrary provider-parameter, header or proxy bag. |
| **Credential slot** | Current protected credential and its independent revision. Reusing a connection reuses this slot without revealing or copying its value. |
| **Pipeline** | Selected generation/reranking connection IDs, model identifiers, supported parameters, prompts and retrieval settings. Built-in local reranking needs no remote credential. |
| **Embedding profile** | Expected provider/model identity and vector-space settings, plus its selected connection ID. Indexing owns compatibility with prepared data. |
| **Evaluation configuration** | Explicit generator/judge connection IDs and model/settings, separate from Pipeline answer-generation choices. |

**Current** means the complete committed access configuration, not unsaved editor input or the newest historical row. Keep non-secret access revisions for audit, comparison and actual call attribution. Consumers cannot select an old revision for execution. Metadata-only rename does not advance the access revision or invalidate admitted work. Credentials continue to have their own revision.

### Review and commit a shared update

1. Resolve the stable connection ID within the effective project and check current connection-management authority. This authority includes live impact; it does not additionally require Manage releases on each affected Deployment. Pipeline Edit or model-use authority alone never grants connection management. Exact permission identifiers remain API delivery work, not invented by this guide.
2. Validate the complete proposed configuration against supported provider contracts, operator destination policy and the compatibility rule below. No model call is hidden in review, dry-run, import or save. Optional paid preflight remains a separately authorized operation.
3. Review the diff, effective target/project, current access revision and affected Pipelines, live Deployments, retained embedding dependencies and active work. Show only permitted names/details; a filtered list cannot establish that no hidden dependency exists. Backend safety checks examine all relevant dependencies regardless of the manager's inspection rights.
4. If live consumers are affected, require deliberate typed acknowledgment in the CLI and an explicit machine equivalent. The backend binds acknowledgment to the reviewed identity, revision and impact, not to a generic `yes`. Connection restoration and explicit import updates use the same operation. Any changed proposal, authorization or relevant dependency state requires fresh review, not silently broadened consent.
5. In a short coordinated write, recheck those conditions and commit the whole configuration, any required credential transition, audit and idempotent outcome together. Coordinate this check with new consumer bindings and embedding-work admission so a concurrent new dependency cannot escape the review. The exact locking/storage mechanism is implementation work; a check performed only before the prompt is insufficient.

Rejected updates leave both access settings and credentials unchanged. A no-op makes no new access revision. A lost response is recovered from the original operation's metadata-only outcome, never by blindly applying the change again. Current permissions still protect replay. No provider network wait belongs inside the write transaction.

Changing origin, provider authentication destination or authentication method must not implicitly reuse a saved secret. Require explicit provision for the reviewed destination through protected input, even if the operator deliberately supplies the same value, and commit it with the access change. An explicitly permitted credential-free configuration clears the old slot atomically. A required new credential that is missing blocks activation; ordinary new-connection setup may still save an incomplete, non-usable connection. Same-destination edits preserve the credential only when its authentication binding remains applicable. This introduces no additional provider authentication mechanism.

<a id="connection-compatibility"></a>

### Reject incompatible shared embedding changes before activation

An index contains vectors produced under an embedding profile, not merely an array length. Before updating a connection, ask Indexing about all prepared or in-progress embedding dependencies, including retained versions and work not visible to the manager. If the proposal changes their vector meaning or compatibility cannot be established, **reject the shared update**. Do not save it and then disable consumers, accept a force confirmation, rewrite profiles or automatically re-embed data.

V1 compares the explicit expected provider/model identity and vector settings and uses supported identity evidence when available. A matching alias, matching dimensions or a successful probe is not proof of equivalent embeddings. In particular, do not assume that another provider, endpoint/base path or provider API version preserves existing vector meaning. Where supported evidence cannot establish that, the update is blocked. Credential-only replacement preserving the access/model contract and metadata-only rename do not require re-embedding.

The recovery path is another connection and the appropriate new embedding profile, then ordinary query/Build preparation and deliberate release. This still permits selecting a different embedding model for a direct query. [Indexing](indexing.md#embedding-compatibility) owns the exact mismatch and readiness outcomes. Unannounced changes inside an external service cannot always be detected; record provider identity where available and never claim the checks certify the provider's internal implementation.

### Migrate gradually or restore settings deliberately

For isolation, create `company-gateway-next`, supply its credential explicitly and select it on the Pipeline's working configuration. Query the Pipeline directly, evaluate if desired, save successful overrides, then Build and release under the ordinary policy. Other consumers remain on the original connection. This needs neither a second gateway service nor a gateway-release framework.

Restoring an earlier connection revision creates a new current access revision through the same reviewed update. It does not make old revisions selectable, restore historical secrets or waive current destination/embedding rules. Pipeline rollback restores Pipeline settings and selected connection identities, **not** connection access settings. An old version that selects `company-gateway` still uses its current configuration.

Project configuration export captures one current non-secret definition per included connection. Import can explicitly reuse an equivalent destination connection or create a new one; a same-name mismatch is not overwrite authority. Explicit updates reuse this guarded operation. Exporting a historical Pipeline's settings does not recreate its historical connectivity. The [shared-connection administration ticket](https://github.com/matejpalenik/inframeld/issues/31) distinguishes portable settings, destination credentials and execution history.

<a id="destinations"></a>

## 2. Approve and validate a destination

Custom endpoints could otherwise let a caller make the server contact arbitrary addresses. This is **server-side request forgery (SSRF)**. Approval and destination checks prevent a model request from becoming unrestricted network access.

There are two distinct configuration responsibilities:

| Who | What they may configure |
| --- | --- |
| **Deployment administrator** | Approves the allowed endpoint origins through deployment configuration. |
| **Human with the required project permission** | Creates a connection within that deployment policy. A project connection cannot expand it. |

A query or evaluation chooses an already configured connection. It cannot supply its own endpoint URL.

The same rule applies to [direct Pipeline queries](pipelines-and-releases.md#preview). Temporary overrides select authorized connection identities and model settings for that execution only; they neither edit shared access settings, rotate credentials nor save the Pipeline's working configuration. Observe current access revisions at admission and check them at dispatch as described below. Missing access, incompatible embedding semantics or unavailable required reranking fails visibly. Direct querying is not an unrestricted model proxy, and success remains narrowly scoped validation evidence rather than publication authority.

This permits approved private customer gateways without giving ordinary users unrestricted network access.

### Validate both the configured URL and the actual destination

| Boundary | Required behavior |
| --- | --- |
| **URL structure** | Validate the scheme, hostname, port, and normalized base path. Also validate the actual destination, not just the displayed URL. |
| **Remote transport** | Require TLS certificate verification. TLS protects the connection and verifies the endpoint's certificate. Mount a customer certificate authority (CA) when its private service requires custom trust. Do not disable verification. |
| **Local HTTP exception** | Explicitly operator-approved local Ollama over HTTP is allowed only without a provider credential or other authentication secret. Never attach a saved key or authorization header to this cleartext connection. If authentication is needed, create an approved HTTPS connection with certificate verification. This exception does not permit unverified remote endpoints. |
| **Credentials in URLs** | Reject URL user-info, such as an embedded username/password, and credential-bearing query strings. |
| **Redirects** | Reject redirects to a different origin. |
| **Forbidden destinations** | Reject link-local and cloud-metadata addresses. These are not made acceptable merely by supporting private endpoints. |
| **Private networks** | Permit private address ranges only through explicit deployment allowlisting. A blanket ban on private addresses would prevent the approved customer-gateway use case. |
| **Caller-controlled proxies** | Do not accept arbitrary proxy settings from API callers. |
| **DNS and network routing** | Revalidate destinations resolved through the Domain Name System (DNS), and enforce the permitted route through host/network egress restrictions. |

Checking the hostname once is insufficient because it may resolve to another address later. Application validation and host/network restrictions must enforce the permitted destination together.

<a id="roles"></a>

## 3. Validate the selected capabilities

Choose embedding and generation models separately. They may share one project connection and key when origin and authentication match. Otherwise use separate connections. A separate synthetic test, called a **preflight**, is recommended but optional under [ADR-0050](../adr/ADR-0050-make-model-preflight-optional-and-record-runtime-validation.md).

Sharing a connection does not require the roles to use the same model, and successful generation does not establish that embeddings work.

For example, a private gateway exposes both a chat model and an embedding model. Alice enters one key, chooses the two models and skips preflight. Both start as **Not tested**. Her first successful real embedding call validates only its embedding configuration. A later successful real generation call validates its generation configuration. Neither requires an extra synthetic request.

### Optional preflight, mandatory runtime checks

An OpenAI-compatible label does not prove every operation or feature works. Offer explicitly authorized, bounded probes for the selected roles, with cost disclosure. Skipping these probes does not block setup, an otherwise valid build/query, or first publication solely because validation evidence is absent or stale. Do not silently insert a synthetic call into the first real operation.

Configuration must still be complete. Establish embedding model semantics and dimensions from supported metadata, explicit validated configuration or an optional probe before freezing its profile. Do not guess unknown dimensions, silently change a profile to fit a response, or reuse incompatible vectors. Missing required credentials, denied permissions, prohibited destinations and unusable dependencies still block their ordinary operations.

A usable saved credential means that current local checks permit its use and its value can be resolved/decrypted. It does not mean the remote provider has already accepted it. Remote acceptance is learned from a probe or real call, not made into another hidden prerequisite.

Reject wrong response shapes, unsupported operations, incorrect embedding dimensions, and non-finite numbers such as infinity or NaN. Candidate and citation IDs must name real application evidence, not invented sources.

These checks apply to every real call as well as optional probes. A previous success cannot waive them. Return defined error outcomes that the application and clients can recognize. Invalid responses must not be silently accepted. Index readiness still requires complete verified materializations; a validated embedding model is not proof that an entire build succeeded.

### Record successful real use without another request

After a real ModelGateway call completes and its result passes all required response checks, automatically record successful validation for the configuration actually used. The owning backend operation records safe evidence from that call, not a second provider request. [Validation evidence](data-model.md#model-validation-evidence) identifies the connection and credential revisions, role, model, relevant configuration, evidence source and time.

An HTTP success alone is insufficient. Incomplete, malformed, failed or uncertain calls must not mark a configuration validated. Validation of one model/role never validates every model sharing the connection. A valid model result can be recorded independently of a later failure elsewhere in a build or query; it does not turn that overall operation into success.

For an eligible success, display **Validated**, with whether it came from preflight or real use and when. If the current configuration has not been tried, display **Not tested** or explain that earlier validation no longer applies. An attempted failure or uncertain result must be reported as such, not labelled Not tested or treated as successful validation. Keep later failures visible alongside historical success. These labels describe observed compatibility, not current provider availability, grounded-answer quality, or release authority.

Replacing a key invalidates the applicability of earlier evidence to the new credential revision. The replacement starts untested but can be used by an otherwise valid operation without another synthetic probe. Removing a required key still blocks dispatch. Neither change rewrites Pipeline meaning. A late success using an older revision may record historical evidence only; it cannot validate the current replacement, restore a removed credential, or undo a newer failure in the status display.

If evidence recording fails, do not claim a persisted validation update or repeat the paid call to recreate evidence. Preserve the ordinary operation's result and recovery rules. Reading status or replaying an old result makes no new provider call and cannot validate a different configuration.

### Evaluation setup is not a prerequisite for the first answer

[First-use setup](onboarding.md) needs working embeddings and generation. Alice needs neither a judge nor a benchmark of evaluation cases before asking her first question.

Optional starter generation and evaluation use embedded Ragas under [ADR-0051](../adr/ADR-0051-use-ragas-for-generated-tests-and-faithfulness-evaluation.md). Select generator and judge connections explicitly and independently of pipeline generation settings. Offer reuse of an existing authorized connection without another key; no provider or model is mandatory and no fallback is implicit. Generation needs no judge until the user explicitly requests evaluation.

[Evaluation's adapter contract](evaluation.md#gateway) covers structured-output conversion, every nested extraction/synthesis/judging/repair call, and optional future embeddings. Ragas receives no provider credentials or independent clients. ModelGateway keeps destination approval, authorization, credential resolution, limits, retry decisions, and usage accounting. Successful ordinary chat does not establish compatibility with the evaluation role's schemas or context limits. Source inspection supports this design; runtime qualification remains required, without making optional preflight mandatory.

<a id="model-metadata"></a>

### Prefill supported settings without treating suggestions as authority

**Status: accepted design, not implemented or qualified behavior.** Alice selects a known model whose catalogue entry suggests a 131,072-token context. Her company gateway is configured for 32,768 tokens. She reviews and saves 32,768. Future catalogue updates must not silently replace her selection. The numbers are illustrative, not model recommendations.

Keep three things separate: a **suggestion** proposes a value, **configuration** records the reviewed value used by the application, and **runtime evidence** records what an actual call demonstrated. A known catalog entry, successful metadata read or manually entered capability is not a successful generation/embedding test.

| Information source | Permitted use | Limitation |
| --- | --- | --- |
| Versioned local snapshot of LiteLLM's model catalog | Suggest available limits, prices and capabilities for an exactly identified supported provider/model | Community metadata can be incomplete or stale. Setup does not fetch an unreviewed remote catalog implicitly. |
| Supported metadata operation on the selected approved server | Suggest values whose meaning the adapter can interpret reliably | No universal discovery endpoint exists. Model listing is not proof of context size, tokenizer identity or access to inference. |
| Explicit user configuration | Override suggestions for supported configurable values, after ordinary validation | A declaration cannot add an unsupported adapter feature, bypass operator limits or rewrite observed facts. |

For example, [Ollama's show operation](https://docs.ollama.com/api-reference/show-model-details) exposes model details, parameters and capabilities. An architectural maximum context is not necessarily the server's configured context, and an internal model dimension is not automatically the embeddings API output size. The adapter must qualify each interpretation. The ordinary [OpenAI model list](https://developers.openai.com/api/reference/resources/models/methods/list) is not a token-limit or tokenizer discovery contract. Do not guess a private alias's meaning from a familiar-looking name.

The backend supplies these suggestions to the CLI and future Studio; neither maintains a competing catalog. Apply this order:

1. Resolve the selected provider, connection, model and role under current authority. Inspect existing saved values first; opening setup again does not replace them.
2. Offer exact-match catalog suggestions or qualified server observations with their source and snapshot/version or observation time. Conflicting or ambiguous observations remain visible; do not silently pick a larger limit.
3. Let the user review and edit all supported configuration values, including applicable context/tokenizer declarations and role settings. Explicit configuration wins over suggestions. Missing required values require input; unavailable optional information remains **Unknown**. Complete manual configuration remains possible when listing/discovery is unavailable.
4. Validate the candidate through its ordinary owner and save effective values with their provenance. Pipeline/profile/evaluator model settings remain with their consumers; connection access/authentication remains shared-current. Exact public metadata fields and persistence representation are specification work, not a new model-registry resource.
5. A later refresh offers a diff against saved values. Applying it requires the normal authorized, revision-checked edit. Changed immutable processing/embedding meaning needs a new profile. Catalog refresh alone changes no saved configuration, live connection, index or release.

Metadata reads are bounded backend operations through the same approved connection, current authorization, destination, credential and transport boundary. They send only required model identifiers, not prompts, corpus text or synthetic inference. They never hide a model call, obtain a credential from another destination or let the CLI contact arbitrary provider URLs. Offline validation and descriptive dry-run do not perform provider discovery. Failure leaves suggestions unavailable and preserves saved work; required execution bounds still must be established before use.

All supported values remain configurable through the qualified CLI/TOML contracts, not an arbitrary LiteLLM parameter bag. Unset/provider-controlled values retain their explicit meaning. Tokenizer choices require supported pinned assets, not executable code or automatic downloads. A generic tokenizer fallback is not an exact private-model count; an estimate cannot become an enforceable admission bound without qualification. Model metadata must be scoped to the actual connection/model context so one project's private alias cannot overwrite another's meaning through a library-global dictionary.

Actual usage, returned vector shape, provider failures and validation history are observations, not editable configuration. Real responses still undergo mandatory checks. Unknown pricing is not zero; a user-supplied rate does not establish free execution or bypass [spending admission](#spending). The versioned prefill snapshot does not freeze billing forever: estimates and reservations retain the qualified pricing source/rates at their own admission, and completed accounting is not repriced by a catalog update.

[LiteLLM documents](https://docs.litellm.ai/docs/completion/token_usage) its community-maintained cost map, local-map option, custom-tokenizer helpers and generic tokenizer fallback. These are inspected external capabilities, not evidence that Inframeld's adapter behaves correctly. #121 must specify exact field ownership, supported mappings, conflicting-source resolution, bounds and failures; #151 specifies portable representation; #37/#155/#185 qualify routing, overrides, round trips and first use. No new service, registry, permission identifier or wire schema is introduced here.

<a id="credentials"></a>

## 4. Save and replace a provider key

Inframeld must recover a provider secret to send it to that provider. It only needs to verify an incoming application key. These different uses require different storage:

| Secret | Purpose | Storage and ownership |
| --- | --- | --- |
| **Outbound provider credential** | Authorizes Inframeld to call a customer's model endpoint. | The gateway must recover its original value. Store authenticated ciphertext and a safe reference. Decrypt only for authorized dispatch. A one-way hash is insufficient. |
| **Inframeld-issued integration credential** | Authenticates an incoming customer application or supported Model Context Protocol (MCP) client. | Inframeld only verifies the high-entropy value presented by the caller. Keep its cryptographic verifier/hash, safe prefix, ownership, scope, expiry, and revocation metadata. Return plaintext once under [Background jobs, retries, and competing changes](jobs-and-idempotency.md). |
| **Human passwords and sessions** | Authenticate people using Inframeld. | Kratos continues to own them. They do not move into the provider-credential store. |

**High entropy** means enough randomness to resist guessing. A **verifier** checks a submitted secret without recovering the original value.

The encrypted store is for outbound model credentials only. It does not change the existing integration-key or human-session design.

### Keep authorization, connection ownership, and encryption separate

Credential storage is a supporting application capability behind its own interface. It does not add a seventh business domain. The table separates permission decisions from storage and encryption details.

| Owner | Responsibility |
| --- | --- |
| **Model-connection commands** | Own the stable credential reference and the behavior for replacement and removal. |
| **Access** | Decides who can manage a connection, use it for a particular action, or inspect its safe metadata. |
| **Credential-store infrastructure adapter** | Owns the ciphertext format and interaction with the encryption library. |
| **Domain entities and pipeline snapshots** | Refer to the connection/configuration without containing plaintext or encryption-library objects. |

Each project-owned provider connection has one credential slot. V1 does not create a shared installation-wide pool of provider secrets.

Permission to use a model lets accepted builds, queries, or evaluations call the permitted connection through ModelGateway. It never permits reading the saved key.

Ordinary query integrations cannot manage provider credentials. Access's defaults assign management to the appropriate initial project administrator. There is no general secret-reader role.

### Expose a narrow, metadata-only management API

The recommended resource path is:

```text
/v1/projects/{projectId}/model-connections/{connectionId}/credential
```

These routes are recommended implementation details, not existing endpoints. Their required behavior is defined below.

| Operation | Required behavior |
| --- | --- |
| **`PUT`** | Create or replace a bounded opaque provider value. Require credential-management authority, an `Idempotency-Key`, and the expected credential revision. Revision **0** means no credential exists. Return only credential/connection identity, revision, presence, and timestamps. |
| **`GET`** | Return authorized safe metadata and the current revision. There is no reveal flag, encrypted-value download, or plaintext field. |
| **`DELETE`** | Require the same management authority, idempotency key, and expected revision. Mark the credential unavailable and remove its ciphertext in one transaction. Retain the non-secret identity needed to explain existing references. |
| **Connection validation command** | Run bounded, explicitly requested role probes through `ModelGateway` using current access settings and the saved credential. Record sanitized results against the actual access revision, credential revision, and tested role/model. Never echo provider headers or raw error bodies. |

The idempotency key identifies a retry, while the expected credential revision detects someone else's intervening change. [Saving changes and retry outcomes](model-connections.md#coordination) explains how they work together.

### Accept a credential value, not arbitrary outbound configuration

Accept a small, opaque API-key or token value. **16 KiB of UTF-8 text** is a proposed byte limit, not yet finalized. UTF-8 defines how text is encoded into bytes.

The provider adapter chooses its known authentication header. This field cannot configure arbitrary headers or proxies. All [destination and SSRF checks](model-connections.md#destinations) still apply.

An explicitly configured local endpoint that needs no credential is a supported distinction. It is not the same as a required key being unexpectedly missing.

<a id="provider-authentication"></a>

### Supply the provider key once, not with every query

Alice creates `company-gateway` at `https://models.company.example/v1`, selects the supported API-key Bearer method and enters the raw key through hidden input. Inframeld saves it using the encrypted store above. When she later queries a Pipeline, her CLI sends her Inframeld credential to Inframeld; the backend resolves the saved provider key and constructs the provider header. She never attaches the provider key to an ordinary query.

```text
CLI -- Inframeld human token or application key --> Inframeld API
Backend -- selected connection's provider credential --> model server
```

These are different trust boundaries. Ory authenticates the human Inframeld path; it neither issues nor verifies the external provider's key. Inframeld-issued `ifm_app_` keys likewise never become upstream model credentials. The selected provider/gateway operator supplies that upstream credential.

For a supported OpenAI-compatible API-key method, the adapter sends `Authorization: Bearer <key>`; users enter the key value, not a header or a `Bearer` prefix. [OpenAI documents this convention](https://developers.openai.com/api/reference/overview#authentication). Compatibility of request/response shapes alone does not guarantee identical authentication. Other supported providers use their qualified adapter's known method. Unsupported authentication fails explicitly, not through arbitrary headers, ambient credentials, a fabricated key, provider fallback or an invented OAuth exchange.

The explicitly approved local Ollama connection can be credential-free, consistent with [Ollama's local API](https://docs.ollama.com/api/authentication). This is not a claim that hosted/cloud Ollama is unauthenticated. A required key that is missing or undecryptable blocks dispatch; a provider authentication rejection is reported safely without trying another credential. All outbound calls carrying an authentication secret require certificate-verified HTTPS, including metadata reads. Destination/auth-method changes retain explicit credential binding and atomic activation; no old key is forwarded implicitly.

Reuse a connection for eligible model selections without revealing or copying its key. A different key uses a separate connection, unless the user deliberately requests shared credential replacement. Hidden human entry and protected file/stdin input for noninteractive authorized administration remain the same workflow; no secrets in argv, environment, TOML, ordinary results, traces or logs. Exact supported authentication methods and error mappings remain #121/#32/#35/#37 implementation and qualification obligations, not blanket cloud-IAM support.

### Show the impact of removal without preserving a hidden old key

Before removing a key, show safe references to the affected current and retained Pipeline versions. Removal can deliberately stop their future model calls.

Do not keep hidden old plaintext to make rollback appear healthy. Deleting Inframeld's copy neither revokes the provider's key nor recalls a call already sent.

<a id="dispatch"></a>

## 5. Resolve a credential for each call

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

### Observe current settings without mixing an admitted operation

New work observes current access revisions for its selected connections at admission. Before each relevant model dispatch, compare those observations with current committed state. A changed access revision blocks the remaining dispatches in that query, preparation, starter-generation or evaluation operation. Do not use the historical revision, silently restart against the new one, or mix responses from different access configurations into a supposedly fixed result. The user admits new work after reviewing the current settings. Metadata rename and credential-only rotation are separate: resolve the current usable credential for each call without restarting solely because its revision changed.

This is an operation precondition, not consumer pinning: an operation may stop when its observed revision is no longer current, but cannot request that old configuration. Queued jobs and resumed attempts obey the same rule. API and worker processes must not keep serving stale cached access settings after a successful freshness check. Qualification must establish the actual read/cache/dispatch boundary.

A call already sent may complete after an update and remains attributed to the revision actually used. No distributed transaction can retract that request. Recheck before any subsequent model call; current permission and erasure checks still apply before disclosure. A final already-sent call may yield an accurately attributed result, but it cannot validate the newer revision or certify that a changed evaluation environment is still comparable. Preserve completed units and uncertainty rather than creating automatic paid retries. [Evaluation](evaluation.md#connection-consistency) specifies run/comparison outcomes.

Check the transport again before dispatch. Reject a local HTTP call if it would carry a saved provider credential or another authentication secret, even if the connection was previously approved. A credential-free local endpoint may still be used through the narrow HTTP exception.

Keep keys out of provider debug output, exception messages, and traces. Jobs carry connection references. Plaintext never belongs in Pipeline or profile snapshots, benchmark or evaluator revisions, logs, evaluation evidence, answer receipts, or API responses.

### Check removal at the dispatch boundary

A wrong encryption key or altered encrypted record blocks dispatch. Removing the credential before the final resolution check also blocks a new call.

Removing it after dispatch cannot undo that call. The local database and remote provider do not participate in one transaction.

### Fail explicitly and keep retry decisions in one place

**A missing credential or provider failure must never trigger automatic fallback to another provider or model.** The selected connection and model are part of the requested behavior, not optional hints.

If a replacement is invalid, old evidence remains intact and new calls fail explicitly. Removing a required key has the same effect.

Follow the shared [retry policy](jobs-and-idempotency.md). Disable independent library retries that could repeat a call whose response was lost after the provider may already have executed it.

A library doing the retry does not make it safe. Application and evaluation code must use the same central decision about whether work may repeat.

### Make the actual data path visible

Show the actual connection, operation, and outgoing data path, even when the customer manages the gateway.

| Activity | Data path that must be disclosed |
| --- | --- |
| **Build an index using OpenAI embeddings** | Newly embedded chunk text is sent to OpenAI. Across the build, this may cover the whole corpus—the selected body of documents. |
| **Ask a question** | The question is sent for embedding. Selected permitted excerpts and instructions are sent to the configured generation endpoint. |
| **Generate starter cases** | The frozen permitted passage sample and bounded persona guidance go to the selected generator through `ModelGateway`. Disclose extraction and synthesis calls before admission. |
| **Run the faithfulness judge** | The question, answer, and exact final generation context go through `ModelGateway` for claim extraction and support judgments. [Evaluation](evaluation.md#metrics) defines inputs and failures. Disclose these separately from starter generation; never add reference answers as supporting evidence. |
| **Store and search in Chroma** | Chroma receives embeddings and the configured chunk text/metadata. Local Chroma keeps them on the self-hosted server. Future Chroma Cloud is a separate external processor. |
| **Use a local model endpoint** | Model processing stays within the configured local environment. Identity setup or model-asset setup may still involve network activity. |

A local model alone does not establish “no egress” for the whole installation. The claim must match the actual operation, including any network activity elsewhere.

The local processing ports described earlier do not change this rule: any future remote processing must disclose its own data path.

<a id="coordination"></a>

## 6. Commit a change and its retry result together

Encryption runs locally. In one PostgreSQL transaction, reserve the request key, update only the expected credential revision, save ciphertext, and record the safe result for retries.

```text
One PostgreSQL transaction
    -> Reserve the request's idempotency key
    -> Apply the expected credential-revision check
    -> Store the ciphertext and updated credential state
    -> Record the metadata-only outcome
    -> Commit together, or roll back together
```

If the transaction fails, none of these changes becomes current. There is no separate vault write that can succeed while its database reference fails.

### Fingerprint the submitted secret without saving it in retry metadata

Include the submitted secret in the request's [domain-separated HMAC fingerprint](jobs-and-idempotency.md), using a separate protected key and a label for this purpose. Never keep the raw request or an ordinary hash of a possibly guessable secret in retry metadata.

| Situation | Required behavior |
| --- | --- |
| **Same key and equivalent request** | After current authorization checks, return the safe recorded outcome without another mutation or revealing the saved value. |
| **Same key with a different secret** | Conflict: this is not an equivalent retry. |
| **Successful save response is lost** | Retrying can recover the metadata-only outcome. Decryption is never part of response replay. |
| **Two genuine changes expect the same credential revision** | Only one conditional mutation succeeds. The other receives a stale-revision conflict. |
| **An old completed command is replayed after later edits** | Return that command's historical safe outcome without reverting current state. |

### Worked example: two operators replace revision 3

Alice and Bob both read credential revision **3** and request a replacement.

Alice saves revision 4. Bob's request still expects 3, so it returns `409 stale_revision`. He reads current metadata and makes a fresh decision. His outdated request cannot overwrite Alice's key.

If Alice loses her response, repeating her original request returns its recorded safe result. Even if revision 5 now exists, that reply describes her earlier change and does not restore revision 4.

### Keep provider validation outside the credential-save outcome

Credential saving and successful model use are separate outcomes. An explicitly requested preflight is a separate recorded operation; a successful ordinary model call can instead record validation under [the role contract](#roles). Successfully saving a key establishes neither outcome.

If a paid validation probe's response is lost, follow the normal [uncertain-call rule](jobs-and-idempotency.md). Validation cannot conceal a second provider request as recovery.

<a id="root-key"></a>

## 7. Protect the persistent encryption key

Generate the root encryption key once with a cryptographically secure random generator. Keep it in a protected host-managed file outside source control, container images, and the application database.

One-time setup may create the file exclusively, with restricted permissions and no secret printed to the terminal. Exclusive creation refuses to overwrite an existing file. Later starts reuse that exact file.

**Never generate a replacement key on every container start or when a configured key file is missing.** Container recreation must not change the key needed to decrypt existing rows.

Mount the file read-only into only the API and worker. Neither the parser nor Studio's web container gets it or direct credential-store access.

### Keep the encryption key and request-fingerprint key distinct

| Deployment key | Purpose |
| --- | --- |
| **Provider-credential encryption key** | Encrypts and decrypts saved provider credentials. |
| **Idempotency HMAC fingerprint key** | Supports [Background jobs, retries, and competing changes](jobs-and-idempotency.md)'s protected request fingerprints for detecting equivalent secret-bearing commands. It must be a **different** protected key. |

HMAC uses a secret key to authenticate a hash. Its key and the credential-encryption key are separate because they serve different purposes.

Protect and recover both keys under the existing deployment-state rules. This adds no separate backup system or schedule. PostgreSQL stores key IDs, never the root encryption key itself.

### Missing or wrong key material must fail visibly

Missing, malformed, or unknown key material disables decryption and protected credential writes with a safe dependency error. Replacing the file with the wrong key cannot decrypt existing records.

Do not erase the ciphertext, fall back to plaintext, invent another key, or switch providers to make the request appear successful.

### Prepare for controlled root-key replacement without building key-management software

Store key IDs now so future maintenance can replace the root key without changing connection references. Selecting a new active ID alone does not re-encrypt old records.

Future root-key replacement must keep the old key until re-encryption is complete and verified. Work in limited batches and check each record's revision so maintenance cannot overwrite a simultaneous credential edit.

V1 needs no online key-management UI or hierarchy of separate keys for every record. Replacing a provider secret in the application does not replace this deployment encryption key.

### State exactly what this encryption boundary protects

Encryption protects a stolen copy of the credential table only if the attacker lacks the deployment key. It does not protect secrets from a compromised API or worker that can decrypt them, or a host administrator controlling those processes.

A separate vault would have the same limitation if the compromised caller could still retrieve keys from it. Encrypted storage is not protection against every compromise of a running system.

Inframeld still owns the practical safeguards: protecting the root key, binding ciphertext to its resource, checking current permissions, limiting plaintext lifetime, returning safe errors, handling competing edits, and testing these boundaries.

The [data model](data-model.md#supporting-records) defines PyNaCl encryption fields, nonces, and resource binding. Mounted files suit root and infrastructure secrets. Merely mounting provider-secret references would not supply the required in-app credential management.

<a id="maintainer-checks"></a>

## 8. Maintainer checks

Choose and pin LiteLLM during implementation, then test that version. This guide does not claim an untested release is qualified.

| Area | Required verification |
| --- | --- |
| **Private endpoint support** | Exercise an OpenAI-compatible private test server using a custom CA and configured egress allowlists. |
| **Local HTTP exception** | Permit an approved local Ollama endpoint without credentials. Reject configuration and dispatch that would send a provider key or authorization header over HTTP. |
| **Provider mappings** | Exercise the selected OpenAI and Ollama mappings through the embedded adapter. |
| **Response validation** | Reject malformed or incompatible responses, wrong embedding dimensions, non-finite values, invalid identities, and unsupported operations. |
| **Independent role validation** | Verify chat and embeddings separately. Successful generation must not be treated as proof of working embeddings or correct dimensions. |
| **Optional preflight and real use** | Skip all synthetic calls, admit complete configurations, and record validation only after each real role call passes its response checks. Malformed, incomplete and uncertain calls must not create successful evidence. |
| **Credential lifecycle** | Test persistent storage and rotation. Replacing/removing a credential invalidates old role-validation status without rewriting pipeline semantics. |
| **Evidence races and recovery** | Finish an old call after key replacement/removal or a newer failure. Preserve its exact historical attribution without validating a new revision or hiding the later outcome. Evidence-write failure must not trigger another provider call. |
| **No implicit rerouting** | Verify that missing credentials and provider failures do not select another provider/model, and that an origin change does not implicitly forward an existing key. |
| **Gateway ownership** | Test evaluator attempts to bypass `ModelGateway`. No independent provider client or framework retry may evade the shared rules. |
| **Shared update and admission races** | Race connection updates with consumer creation, embedding preparation, credential rotation and a changed review. Either admit compatible work against the committed state or reject the stale mutation; never leave a newly incompatible dependency behind. Hidden consumers must constrain the result without disclosure. |
| **Current dispatch and recovery** | Change access configuration after admission, while queued, between calls and before evaluation finalization or conditional publication. Stop new sends and preserve partial outcomes. Test API/worker cache freshness, lost update responses and already-dispatched results without silent rebinding or replay. |
| **Embedding compatibility** | Reject a different model/vector space and unknown endpoint equivalence before changing access settings or credentials. Equal dimensions, aliases and successful probes are insufficient proof. Verify the separate-connection/profile preparation route remains usable. |

These are acceptance requirements, not claims that implementation qualification has already passed.

### Qualify the adapter and connection use cases together

Place the focused security tests with the credential adapter and connection operations. The table records requirements, not results already collected.

| Area | Required verification |
| --- | --- |
| **Persistence and model roles** | Save a key, restart the API/worker, and use the same saved key for real bounded embedding and generation calls through one connection. Keep failures in the two role validations distinct. |
| **Integrity and resource binding** | Tamper with ciphertext, nonce, project/connection binding, credential revision, and key ID. Each case must prevent dispatch. Missing or wrong root keys must not generate replacement material. |
| **Concurrent changes and retries** | Race replacements and repeat a lost-response request. Verify one conditional mutation, correct idempotency behavior, and metadata-only responses. |
| **Removal** | Remove a credential and deny subsequent dispatch without claiming to cancel a call already sent. Do not reuse a cached old plaintext value or fall back to another provider. |
| **Destination transition** | Change origin or authentication binding with an explicitly provisioned credential, and separately test an allowed credential-free transition. Access and credential changes commit together or neither does; an omitted key cannot forward the old secret. |
| **Authorization and disclosure** | Exercise unauthorized management/use, cross-project references, request-validation failures, provider exceptions, and library debug paths. Assert that submitted/saved keys never appear in responses, persisted jobs, receipts, snapshots, logs, or the parser's environment/mounts. |

These checks are necessary before relying on provider credentials and are intended to remain manageable for one developer. They imply no performance result, completed security audit, or tested image lock.

<a id="spending"></a>

## Cost Estimates and Spending Admission

Alice gives a project a USD 20 calendar-month allowance and an evaluation a USD 1 limit. Customer queries running at the same time consume the same project budget. Both limits are optional. Never select an amount silently.

The project period begins at midnight UTC on the first of each month. The operation limit instead follows that operation across retries, continuation and month boundaries. Changing CLI context or rotating credentials resets neither accounting record.

Inframeld owns spending accounting. It uses qualified LiteLLM pricing, token-counting and usage utilities without deploying a separate model gateway.

Show a best-effort estimate before upload, refine it after processing and summarize observed usage afterward. Include where the prices came from, how recent they are and the assumptions used. Private-model pricing may be unavailable. Local Ollama has no external model API charge, but still consumes compute. An estimate is neither a provider invoice nor a conservative upper bound used to reserve spending.

Before each chargeable model call:

1. Prepare the actual payload within its limits. For generation, enforce a maximum output allowance and include every applicable billable category. Average answer length is not an upper bound.
2. In one PostgreSQL transaction, reserve enough allowance against every applicable limit. Count both confirmed costs and existing reservations, called **holds**, so concurrent calls cannot each spend the same remaining allowance.
3. Close the transaction before contacting the provider.

Every model role, optional probe and repair call follows this process. Available budget never substitutes for permission to make the call.

After a call, record its cost once using trustworthy usage and the captured rates. This is **settlement**. Release only the unused part of its hold. Use fixed-precision decimal amounts and qualified conservative rounding.

Release a hold when the call is known not to have been sent. Keep it unresolved when dispatch may have happened but the outcome is unknown, including timeouts, cancellation, missing usage or a lost acknowledgment. Restarting a worker or letting its lease expire does not prove the provider charged nothing.

Record any overage honestly and stop further affected spending until it is resolved. A late settlement belongs to the project's original admission period. The operation's cumulative limit still applies.

With a monetary limit enabled, do not dispatch if prices are unavailable or a conservative bound cannot cover the billable work. An authorized policy or pricing change must make the call admissible first. If accounting itself is unavailable, capped work cannot start.

Without a cap, unknown pricing need not block otherwise supported and authorized use, but disclose that uncertainty. A familiar model alias or an arbitrary zero rate does not prove that execution is free and local.

When the budget is exhausted, stop new calls and keep completed work. Do not shrink the corpus or switch models to continue. Use ordinary job failure and recovery outcomes, not a new paused-job system. A new month does not automatically restart failed work.

Changing a shared limit requires its own current permission and audit record. [The delivery plan](cli-delivery-plan.md) assigns exact management and recovery contracts, transactional accounting and tests for concurrency, rounding and providers. This design is not an invoice-level spending guarantee or evidence that those tests ran.

<a id="budget-policy-authority"></a>

### Manage the policy separately from enforcing it

Alice sets a USD 20 monthly project budget. SupportBot runs evaluations until a new model call cannot fit. The call is refused; the bot cannot raise the limit to keep itself running. An explicitly authorized human may review and change the limit to USD 50. That change saves policy only: eligible work must be resumed explicitly through the ordinary recovery operation.

V1 separates three actions:

| Action | Permission boundary |
| --- | --- |
| Inspect budget information | Humans and applications may read only the information they are currently permitted to see. |
| Execute model work | Authorized workloads may spend within all applicable limits. |
| Set, increase, decrease or remove a project limit | Only an active human with the project's budget-management permission may do this. Being human is not enough. Applications cannot receive this capability through model-use or import grants. |

The [Access contract](https://github.com/matejpalenik/inframeld/issues/116) owns exact actions and targets, coordinated with the [model contract](https://github.com/matejpalenik/inframeld/issues/121). [Budget management](https://github.com/matejpalenik/inframeld/issues/190) implements them.

Apply that same rule in setup, ordinary management and configuration import. An application import may keep the destination budget while recreating otherwise authorized resources. If it explicitly requests a budget change, report the human-only restriction before executing the known-invalid plan; do not silently drop that step, borrow a human login or claim the requested plan succeeded.

Current authority and expected state are rechecked when a permitted mutation commits. If authority is lost after earlier import work committed, preserve those completed outcomes and stop the affected unfinished work under ordinary recovery rules. This choice does not change cumulative operation-limit behavior or decide authority for other project policies.

Alice changes the project's monthly limit from USD 20 to USD 10 after USD 12 has already been settled and USD 1 remains reserved. The update changes the policy, not the ledger: it does not erase spending, release the hold or make the available allowance positive. Further calls that cannot fit are refused. Already-dispatched calls retain normal settlement and uncertainty handling.

One application-layer capability exposes authorized inspection and human-only setting, replacement and explicit removal of the project limit. Here, application-layer means backend business orchestration, not permission for an application account to mutate policy. CLI setup/management and TOML import use this capability; none writes a separate copy of policy. Recheck current human eligibility/change authority and the reviewed policy revision, coordinate mutation with concurrent reservations, and commit policy/audit together. The exact coordination protocol and request schemas must be reviewed before implementation. A lost acknowledgment recovers the original mutation rather than applying it over a newer policy.

Increasing or removing a limit also preserves consumed amounts and unresolved obligations. It neither changes existing operation limits nor resumes stopped work. Setup retains the current policy by default; import preserves destination policy unless its explicit apply choice is separately authorized. A model-use grant, generic import approval or `--yes` is not budget-administration authority. No monetary default is prefilled, and no provider test or model call follows saving a policy. V1 has only project and operation limits; account, user, connection and organization budget hierarchies remain deferred.

Connection TOML exports only current supported non-secret access settings and authentication requirements. Credentials are separately provisioned and consumer model settings remain with profiles/pipelines/evaluators. [Configuration portability](configuration-portability.md) preserves ordinary live-impact and embedding guards during import.

<a id="decision-map"></a>

## 9. Decision and reference map

Route shapes and the 16 KiB limit remain recommendations. Saving and validating a key remain separate. LiteLLM and private-endpoint compatibility need tests. Root-key replacement is future controlled maintenance, not an online key-management product.

| Decision | Rationale |
| --- | --- |
| [ADR-0023](../adr/ADR-0023-route-every-model-request-through-modelgateway.md) | Route every model request through ModelGateway. |
| [ADR-0024](../adr/ADR-0024-approve-outbound-destinations-before-model-calls.md) | Approve outbound destinations before model calls. |
| [ADR-0025](../adr/ADR-0025-separate-connection-meaning-from-replaceable-credentials.md) | Preserve the original rationale for credential separation; consumer-pinned access is superseded by ADR-0054. |
| [ADR-0054](../adr/ADR-0054-use-shared-current-model-connections.md) | Use shared current connectivity with guarded changes, embedding compatibility and honest execution attribution. |
| [ADR-0050](../adr/ADR-0050-make-model-preflight-optional-and-record-runtime-validation.md) | Make preflight optional and record successful real calls as revision-specific validation. |
| [ADR-0048](../adr/ADR-0048-encrypt-outbound-credentials-in-postgresql-using-pynacl.md) | Encrypt outbound credentials in PostgreSQL using PyNaCl. |
