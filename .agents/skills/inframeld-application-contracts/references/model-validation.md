# Validate real model use without making probes mandatory

Alice saves a connection without buying a synthetic test call. Structural checks still apply. A later successful real call can record capability-specific evidence, while configuration save, validation and remote uncertainty keep distinct outcomes.

<a id="saving-a-replacement-does-not-certify-that-it-works"></a>

### Saving a replacement does not certify that it works

Initial setup and first publication do not require prior synthetic success or a validated-model marker under [ADR-0050](../../../../docs/adr/ADR-0050-make-model-preflight-optional-and-record-runtime-validation.md). Complete configuration, required usable credentials, verified materializations and the ordinary authorization/publication checks still apply. A successful probe or real call using an old key cannot validate its replacement.

Published versions may use a deliberately replaced key and report ordinary provider failures if it does not work. Do not silently restore the old secret or switch provider/model. Key rotation changes the ability to call the connection without rewriting historical pipeline configuration.

<a id="model-validation-evidence"></a>

<a id="record-validation-evidence-for-the-configuration-actually-used"></a>

### Record validation evidence for the configuration actually used

This is an accepted logical contract, not a new physical table or implemented schema. Successful optional preflight and successful real ModelGateway calls can establish the same role-specific compatibility evidence. The backend records it only after the full model result passes the required response checks.

| Evidence | Required meaning |
| --- | --- |
| **Scope and connection** | Owning project, stable connection identity and the access revision actually used. Evidence cannot be borrowed from another project, endpoint or newer revision. |
| **Credential revision** | The actual credential revision resolved for that call. A deliberately credential-free connection records that explicit configuration, not a fictional key or a missing required credential. |
| **Role and model** | The exact requested role/model and relevant immutable configuration or profile reference. Changing the selected model or relevant settings does not inherit another selection's evidence. |
| **Embedding facts** | Actual dimensions checked against the frozen profile and successful numerical/shape validation. One successful response does not establish a complete materialization. |
| **Source and time** | Whether the success came from synthetic preflight or real use, with its call/operation attribution and time. Record the resolved provider model revision when supplied. |
| **Outcome** | An accepted complete response, not merely HTTP success, a request being dispatched, or a partial/uncertain result. No plaintext credential or full input/output payload belongs in this evidence. |

The current selection is **Not tested** before it has been tried, and **Validated** when it has applicable successful evidence. These are display meanings, not a finalized storage enum. Explain stale prior evidence after credential/configuration changes. Report a failed or uncertain attempt explicitly rather than mislabelling it Not tested or validated. Neither validation label is an authorization decision or proof of current provider health. Keep later failed attempts visible separately without erasing historical successes or allowing a late earlier result to hide them.

Record evidence against the revisions captured by the actual call, not whatever revisions happen to be current when it finishes. A late result for credential revision 3 cannot validate revision 4 or restore a removed credential. Reading or replaying evidence cannot perform a new call, reattribute old success to new settings, or establish a new current success time. If evidence recording fails, never repeat a paid call merely to populate the marker or claim that unrecorded evidence was saved.

A successful generation call does not validate embeddings, every model on its connection, the overall query/build, answer quality or permission to release. [Model connections](#roles) owns saving, replacement, removal, optional probes, runtime response checks and the evidence-recording workflow. Operation recovery continues under the existing job/idempotency rules.

Migration [0002](../../../../apps/backend/migrations/versions/0002_idempotency_reservations.py) implements `idempotency_reservations`. Each row stores an opaque `operation_id`, stable `principal_id`, `organization_id`, optional `project_id`, HTTP `method`, logical `requested_route`, `request_key`, binary `request_fingerprint`, `state`, optional `replay_kind`, and creation and expiry times. A unique constraint covers principal, organization, project, method, route, and key, treating an absent project as one shared scope. A completed row classifies the safe replay outcome. It does not store an HTTP response body or plaintext secret.

The owning command saves its accepted change and required audit in the same transaction as the reservation. The implemented project grant command follows this rule. The admission helper also exercises shared outcome conversion, while other outcome kinds await their complete owning workflows. Fingerprints of secret-bearing requests use a separate protected HMAC key. [Jobs](jobs-and-recovery.md) owns replay and retention.

<a id="validate-the-selected-capabilities"></a>

<a id="roles"></a>

<a id="3-validate-the-selected-capabilities"></a>

## Validate the selected capabilities

Choose embedding and generation models separately. They may share one project connection and key when origin and authentication match. Otherwise use separate connections. A separate synthetic test, called a **preflight**, is recommended but optional under [ADR-0050](../../../../docs/adr/ADR-0050-make-model-preflight-optional-and-record-runtime-validation.md).

Sharing a connection does not require the roles to use the same model, and successful generation does not establish that embeddings work.

For example, a private gateway exposes both a chat model and an embedding model. Alice enters one key, chooses the two models and skips preflight. Both start as **Not tested**. Her first successful real embedding call validates only its embedding configuration. A later successful real generation call validates its generation configuration. Neither requires an extra synthetic request.

<a id="optional-preflight-mandatory-runtime-checks"></a>

### Optional preflight, mandatory runtime checks

An OpenAI-compatible label does not prove every operation or feature works. Offer explicitly authorized, bounded probes for the selected roles, with cost disclosure. Skipping these probes does not block setup, an otherwise valid build/query, or first publication solely because validation evidence is absent or stale. Do not silently insert a synthetic call into the first real operation.

Configuration must still be complete. Establish embedding model semantics and dimensions from supported metadata, explicit validated configuration or an optional probe before freezing its profile. Do not guess unknown dimensions, silently change a profile to fit a response, or reuse incompatible vectors. Missing required credentials, denied permissions, prohibited destinations and unusable dependencies still block their ordinary operations.

A usable saved credential means that current local checks permit its use and its value can be resolved/decrypted. It does not mean the remote provider has already accepted it. Remote acceptance is learned from a probe or real call, not made into another hidden prerequisite.

Reject wrong response shapes, unsupported operations, incorrect embedding dimensions, and non-finite numbers such as infinity or NaN. Candidate and citation IDs must name real application evidence, not invented sources.

These checks apply to every real call as well as optional probes. A previous success cannot waive them. Return defined error outcomes that the application and clients can recognize. Invalid responses must not be silently accepted. Index readiness still requires complete verified materializations. A validated embedding model is not proof that an entire build succeeded.

<a id="record-successful-real-use-without-another-request"></a>

### Record successful real use without another request

After a real ModelGateway call completes and its result passes all required response checks, automatically record successful validation for the configuration actually used. The owning backend operation records safe evidence from that call, not a second provider request. [Validation evidence](#model-validation-evidence) identifies the connection and credential revisions, role, model, relevant configuration, evidence source and time.

An HTTP success alone is insufficient. Incomplete, malformed, failed or uncertain calls must not mark a configuration validated. Validation of one model/role never validates every model sharing the connection. A valid model result can be recorded independently of a later failure elsewhere in a build or query. It does not turn that overall operation into success.

For an eligible success, display **Validated**, with whether it came from preflight or real use and when. If the current configuration has not been tried, display **Not tested** or explain that earlier validation no longer applies. An attempted failure or uncertain result must be reported as such, not labelled Not tested or treated as successful validation. Keep later failures visible alongside historical success. These labels describe observed compatibility, not current provider availability, grounded-answer quality, or release authority.

Replacing a key invalidates the applicability of earlier evidence to the new credential revision. The replacement starts untested but can be used by an otherwise valid operation without another synthetic probe. Removing a required key still blocks dispatch. Neither change rewrites Pipeline meaning. A late success using an older revision may record historical evidence only. It cannot validate the current replacement, restore a removed credential, or undo a newer failure in the status display.

If evidence recording fails, do not claim a persisted validation update or repeat the paid call to recreate evidence. Preserve the ordinary operation's result and recovery rules. Reading status or replaying an old result makes no new provider call and cannot validate a different configuration.

<a id="model-metadata"></a>

<a id="prefill-supported-settings-without-treating-suggestions-as-authority"></a>

### Prefill supported settings without treating suggestions as authority

**Status: accepted design, not implemented or qualified behavior.** Alice selects a known model whose catalogue entry suggests a 131,072-token context. Her company gateway is configured for 32,768 tokens. She reviews and saves 32,768. Future catalogue updates must not silently replace her selection. The numbers are illustrative, not model recommendations.

Keep three things separate: a **suggestion** proposes a value, **configuration** records the reviewed value used by the application, and **runtime evidence** records what an actual call demonstrated. A known catalog entry, successful metadata read or manually entered capability is not a successful generation/embedding test.

| Information source | Permitted use | Limitation |
| --- | --- | --- |
| Versioned local snapshot of LiteLLM's model catalog | Suggest available limits, prices and capabilities for an exactly identified supported provider/model | Community metadata can be incomplete or stale. Setup does not fetch an unreviewed remote catalog implicitly. |
| Supported metadata operation on the selected approved server | Suggest values whose meaning the adapter can interpret reliably | No universal discovery endpoint exists. Model listing is not proof of context size, tokenizer identity or access to inference. |
| Explicit user configuration | Override suggestions for supported configurable values, after ordinary validation | A declaration cannot add an unsupported adapter feature, bypass operator limits or rewrite observed facts. |

For example, [Ollama's show operation](https://docs.ollama.com/api-reference/show-model-details) exposes model details, parameters and capabilities. An architectural maximum context is not necessarily the server's configured context, and an internal model dimension is not automatically the embeddings API output size. The adapter must qualify each interpretation. The ordinary [OpenAI model list](https://developers.openai.com/api/reference/resources/models/methods/list) is not a token-limit or tokenizer discovery contract. Do not guess a private alias's meaning from a familiar-looking name.

The backend supplies these suggestions to the CLI and future Studio. Neither maintains a competing catalog. Apply this order:

1. Resolve the selected provider, connection, model and role under current authority. Inspect existing saved values first. Opening setup again does not replace them.
2. Offer exact-match catalog suggestions or qualified server observations with their source and snapshot/version or observation time. Conflicting or ambiguous observations remain visible. Do not silently pick a larger limit.
3. Let the user review and edit all supported configuration values, including applicable context/tokenizer declarations and role settings. Explicit configuration wins over suggestions. Missing required values require input. Unavailable optional information remains **Unknown**. Complete manual configuration remains possible when listing/discovery is unavailable.
4. Validate the candidate through its ordinary owner and save effective values with their provenance. Pipeline/profile/evaluator model settings remain with their consumers. Connection access/authentication remains shared-current. Exact public metadata fields and persistence representation are specification work, not a new model-registry resource.
5. A later refresh offers a diff against saved values. Applying it requires the normal authorized, revision-checked edit. Changed immutable processing/embedding meaning needs a new profile. Catalog refresh alone changes no saved configuration, live connection, index or release.

Metadata reads are bounded backend operations through the same approved connection, current authorization, destination, credential and transport boundary. They send only required model identifiers, not prompts, corpus text or synthetic inference. They never hide a model call, obtain a credential from another destination or let the CLI contact arbitrary provider URLs. Offline validation and descriptive dry-run do not perform provider discovery. Failure leaves suggestions unavailable and preserves saved work. Required execution bounds still must be established before use.

All supported values remain configurable through the qualified CLI/TOML contracts, not an arbitrary LiteLLM parameter bag. Unset/provider-controlled values retain their explicit meaning. Tokenizer choices require supported pinned assets, not executable code or automatic downloads. A generic tokenizer fallback is not an exact private-model count. An estimate cannot become an enforceable admission bound without qualification. Model metadata must be scoped to the actual connection/model context so one project's private alias cannot overwrite another's meaning through a library-global dictionary.

Actual usage, returned vector shape, provider failures and validation history are observations, not editable configuration. Real responses still undergo mandatory checks. Unknown pricing is not zero. A user-supplied rate does not establish free execution or bypass [spending admission](spending-and-accounting.md#spending). The versioned prefill snapshot does not freeze billing forever: estimates and reservations retain the qualified pricing source/rates at their own admission, and completed accounting is not repriced by a catalog update.

[LiteLLM documents](https://docs.litellm.ai/docs/completion/token_usage) its community-maintained cost map, local-map option, custom-tokenizer helpers and generic tokenizer fallback. These are inspected external capabilities, not evidence that Inframeld's adapter behaves correctly. Model metadata contracts still need exact field ownership, supported mappings, conflicting-source resolution, bounds and failures. Portability needs a corresponding reviewed representation. Qualify routing, overrides, round trips and first use. No new service, registry, permission identifier or wire schema is introduced here.

<a id="keep-provider-validation-outside-the-credential-save-outcome"></a>

### Keep provider validation outside the credential-save outcome

Credential saving and successful model use are separate outcomes. An explicitly requested preflight is a separate recorded operation. A successful ordinary model call can instead record validation under [the role contract](#roles). Successfully saving a key establishes neither outcome.

If a paid validation probe's response is lost, follow the normal [uncertain-call rule](jobs-and-recovery.md). Validation cannot conceal a second provider request as recovery.

<a id="configure-models-with-optional-preflight"></a>

<a id="models"></a>

<a id="3-configure-models-with-optional-preflight"></a>

## Configure models with optional preflight

Saving a provider key does not prove it works. Testing text generation also does not prove that the same connection can create embeddings for search.

The simplest form accepts one connection and key, then separate embedding and generation model IDs. Share the connection when both use the same origin and authentication. An **origin** is the scheme, host, and port. Otherwise configure separate connections without copying a saved secret to another origin.

Use the same role, model and connection screens for generation, embeddings and hosted reranking. [Metadata suggestions](#model-metadata) may prefill supported settings from either an identified versioned local catalogue entry or a qualified metadata read from the selected approved server. Show where the suggestion came from, let the user edit it and save the reviewed values.

For a private model alias with no reliable metadata, leave unknown settings unknown until the user supplies the necessary supported configuration. If model listing fails, still allow manual model input. Do not run an inference probe to fill the gap.

For example, Alice changes a suggested context of 131,072 tokens to her gateway's configured 32,768, reuses `company-gateway`'s saved key and skips testing. Resuming setup retains those saved choices even after a catalog update. It does not re-prompt for the key or mark the role Validated. Model settings belong to the Pipeline/profile, not a new connection variant. A refresh requires a reviewed ordinary edit. Human and noninteractive paths expose the same values, provenance and unresolved requirements. Scripts do not silently choose a newer suggestion.

[Provider authentication](../../inframeld-access-models/references/provider-credential-storage.md#provider-authentication) is separate from login: users provide a raw provider key once through the protected connection workflow, and the backend supplies the supported authentication header when calling that destination. Incoming Hydra tokens and Inframeld application keys never travel upstream. A credential-free approved local Ollama connection skips irrelevant key entry. Authentication-method support, safe metadata discovery and exact field contracts still require qualification.

Offer a small synthetic test of the selected roles, but let Alice continue without it. This **preflight** can catch configuration problems before larger processing costs occur. It is not a prerequisite for ordinary model use or first publication. A user may instead save configuration and exit. Separate paid probes require explicit approval, and skipping them never silently schedules one later.

Before a selected role/model has been tried, show it as **Not tested**, not invalid or ready merely because a key was saved. When a real call completes and passes all required response checks, automatically mark its actual configuration **Validated**, recording real use as the evidence source. Report a failed or uncertain attempt explicitly rather than calling it untested or validated. Generation success validates only generation. A successful embedding call validates only that embedding configuration and its actual dimensions. Neither makes an incomplete build ready or certifies answer quality.

For example, Alice skips both tests. Her real document-embedding work establishes embedding validation, and the complete verified index can become ready for authorized publication while generation remains Not tested. Her first real answer then establishes generation validation if its response passes the required checks. If generation fails, report the ordinary query failure without changing provider, fabricating an answer or erasing completed embedding work.

Configuration and runtime checks remain mandatory even when Alice skips the probe. Establish embedding meaning and dimensions before freezing the profile, using supported metadata, explicit validated configuration or an optional probe. Resolve missing dimensions rather than guess them.

Every real call goes through ModelGateway's permission, credential, destination, transport and response checks. First publication still needs complete valid configuration, a ready version with verified materializations, all required local dependencies and normal release permission.

Local credential checks establish only that a required key is present, permitted and decryptable. They do not prove that the provider accepts it. **Absence of prior model-validation evidence is not itself a readiness or publication blocker.**

Replacing a key makes the new credential revision untested. A late success using the old key cannot validate the replacement. Removing a required key still blocks dispatch. After setup, connection management can change shared current access settings through [guarded review](model-connection-changes.md#shared-current), including explicit credential provision for a changed origin. Incompatible or unproven existing embedding dependencies reject the update. Another connection and ordinary preparation/query/Build support isolated migration. Setup does not silently edit a reused connection. Validation status is historical evidence, not an availability guarantee. Show later failures without hiding them behind an earlier successful check.

[Model connections](#roles) owns these runtime and evidence rules, and [ADR-0050](../../../../docs/adr/ADR-0050-make-model-preflight-optional-and-record-runtime-validation.md) supersedes the former separate-probe prerequisite. Neither optional preflight nor runtime evidence adds an offline benchmark, judge or certification process.

Save application-entered credentials using the accepted [PostgreSQL/PyNaCl mechanism](model-gateway-and-connections.md). Missing setup cannot be bypassed with a fabricated valid connection.
