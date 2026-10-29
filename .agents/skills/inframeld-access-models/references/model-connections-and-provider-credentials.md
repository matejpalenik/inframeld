# Model connections and provider credentials

<a id="model-connections-and-provider-credentials"></a>

Alice connects a provider so SupportBot can answer questions. The bot's incoming application key identifies the caller. The saved provider key authenticates a later outbound model call. Keeping them separate prevents an integration credential from becoming authority to choose arbitrary endpoints or expose provider secrets.

<a id="concepts-and-owners"></a>

## Apply accepted ADR-0123

Accepted [ADR-0123](../../inframeld-application-contracts/references/model-metadata-and-validation.md#accepted-metadata-and-reference-contract) selects this workflow's detailed contract. A model catalogue can suggest settings without proving that a private server supports them. Separately, deleting a shared connection is safe only when no retained executable configuration still needs it. Apply its exact bounds, current-state checks and failure outcomes. Native implementation and qualification remain separate.

## Concepts and owners

A connection has one current access configuration. Consumers select stable connection IDs and model-role settings. They cannot execute an old access revision. A separately replaceable provider credential has its own revision and secret lifecycle.

For example, replacing the key for Alice's connection does not give SupportBot a different identity or change its grants. ModelGateway owns approved dispatch, runtime checks, retries and spending enforcement. Access owns who may manage the resources.

<a id="review-and-activate-a-change"></a>

## Review and activate a change

1. Require current connection-management authority. Pipeline Edit does not grant this power. Authorized connection managers can approve shared live impact without acquiring per-Deployment release rights.
2. Review current consumer impact and dependencies. Backend-bound acknowledgement, expected revisions, authorization and dependency checks are enforcement, not a client prompt.
3. Reject incompatible or unproven prepared/in-progress embedding dependencies before mutation, including retained or hidden dependencies. Matching aliases, dimensions or a probe does not establish unchanged numerical meaning.
4. For origin or authentication-destination changes, require explicit destination-bound credential provision and activate atomically. Never forward an old secret implicitly. Another connection provides an isolated migration path. Restoration is a new guarded update, not recovery of an old secret.
5. Each admitted operation observes current access revisions. Relevant changes stop later dispatch instead of mixing settings, executing old revisions or rebinding the original operation. Record the actual revisions used by already dispatched calls. Key-only rotation and metadata rename remain distinct from changes to model/access meaning.

Manual release mode and Pipeline rollback do not freeze or restore shared connection settings. Credential-only replacement preserves the access/model contract and does not itself require new vectors. Provider-side alias drift cannot always be detected.

<a id="protect-credentials-and-model-access"></a>

## Protect credentials and model access

PostgreSQL/PyNaCl authenticated encryption with a separate persistent root key is accepted. Authenticated encryption protects saved secret contents and detects tampering. Bind ciphertext to the documented resource context, and keep plaintext resolution narrow.

Missing or wrong key material must fail closed. Root encryption keys and keyed request-fingerprint keys serve different purposes. Secrets do not enter exports, access-history, receipts, logs or replay payloads.

Any connection requiring an authentication secret uses certificate-verified HTTPS. The operator-approved local Ollama HTTP exception is credential-free. Approved destinations and supported adapters remain mandatory. Do not add arbitrary headers, a new registry or ambient laptop credentials by inference.

<a id="validation-records-an-observation"></a>

## Validation records an observation

All remote embeddings, generation, judges, extraction, synthesis, repairs and optional probes use ModelGateway. A separate synthetic preflight is optional. This is a test call made before ordinary work. Valid complete configuration can execute without it, while security checks, spending admission and response validation remain mandatory.

After response checks, a successful real call records validation only for its actual role/model/configuration and connection/credential revisions. It does not validate every model sharing a key, certify answer quality, prove current health or make an incomplete index ready.

A replaced credential begins untested but is not blocked solely for missing historical validation. A late old-key result cannot validate its replacement or revive a removed credential. Keep evidence source/time and later failures, and never repeat a paid request merely to record validation.

<a id="metadata-budgets-and-authority"></a>

## Metadata, budgets and authority

Model metadata provides sourced, editable suggestions for limits/tokenizers and settings. It is not a silent catalogue update or runtime proof. Qualified metadata reads share the approved backend connection boundary. Offline configuration validation makes no provider calls. Explicit settings still obey current authority, adapter support, spending and immutable-profile rules. The exact reviewed metadata and authentication contracts remain with their owning guides and historical tracking issues.

<a id="budget-changes-need-separate-authority"></a>

## Budget changes need separate authority

Budget-policy administration is a guarded human-only capability across setup, management and import. Eligible applications may inspect permitted budget information and do authorized work within limits. They cannot set, raise, lower or remove a project limit. Human identity still needs project-specific authority.

An import may preserve destination policy. A known-ineligible explicit apply is denied, not silently skipped or run as a saved human. Changes never reset usage, reservations or operation limits. Client estimates do not enforce budgets.

<a id="provider-keys-are-different"></a>

### Provider keys are different

Under [ADR-0054](../../../../docs/adr/ADR-0054-use-shared-current-model-connections.md), **connection-management authority includes the ability to approve shared live access changes**. Do not additionally require Manage releases on every affected Deployment, and do not grant this power through ordinary Pipeline Edit or model use. Keep any existing human-only administration restrictions. This is a capability contract, not a new permission identifier or an expanded application-account grant.

The owning operation must validate current management authority and bind live-impact acknowledgment to the reviewed connection state and affected dependencies. Recheck at commit. It may inspect all dependencies internally for safety, while disclosing only permitted names/details to the manager. Hidden consumers must not be ignored or leaked. Neither acknowledgment nor connection-management authority bypasses operator destination policy, credential isolation or the embedding-compatibility veto. [Model connections](../../inframeld-application-contracts/references/model-connection-changes.md#shared-current) owns that workflow, including explicit import updates and restoration.

Inframeld only needs to **verify** an incoming SupportBot key, so it stores a hash. It needs to **send** an outbound provider key when calling a model service, so that key must be recoverable. Provider keys are encrypted in PostgreSQL using PyNaCl and a separate root key.

ModelGateway obtains the appropriate provider secret only when needed. Plaintext must stay out of Studio reads, jobs, snapshots, logs, receipts, evidence, and document-parser environments. A missing required credential causes failure, not a silent fallback. [Model connections](../../inframeld-application-contracts/references/model-gateway-and-connections.md) owns provider-key management, endpoint changes, and validation for each model role.

<a id="authorization-failure-scenarios"></a>

## Authorization failure scenarios

| Situation | Required outcome |
| --- | --- |
| SupportBot can query a Deployment and inspect budget. | It cannot query the Pipeline, inspect traces, change budget/tracing policy or delete history without the corresponding eligible exact grant. |

| Situation | Required outcome |
| --- | --- |
| A provider exceeds the remaining authentication budget. | Admit no late success or cached success. Report unconfirmed verification without fallback. |
| SupportBot has budget inspection and Evaluation execution grants. | Permitted inspection/work does not permit human-only budget mutation or tracing administration. |

<a id="pending-decisions-for-dependent-implementation"></a>

## Decision references for dependent implementation

Apply the accepted entries below when their scope matches. Discuss only choices still explicitly marked pending:

- [PD-ACCESS-05 (accepted): Implement and qualify the selected provider-secret lifecycle](decision-provider-secret-lifecycle.md). When implementing protected provider-credential management, storage or deployment-key integration, and before claiming the complete secret boundary is qualified.
- [PD-CONTRACTS-01 (accepted): Enforce model policy on the actual outbound path](../../inframeld-application-contracts/references/decision-gateway-enforcement.md). Before implementing model adapters/metadata/probe dispatch or selecting the actual transport/egress mechanism.
- [PD-CONTRACTS-02 (accepted): Coordinate budget policy, reservations and uncertain settlement](../../inframeld-application-contracts/references/decision-spending-coordination.md). Before implementing budget mutation, reservation, settlement, usage normalization or unknown-charge recovery.

<a id="status-and-sources"></a>

## Status and sources

These are accepted connection, validation and storage boundaries. Exact public actions, wire/storage details and runtime qualification remain identified in the guides. Emergency suspension/restoration and scoped operator maintenance have separate delivery owners. Do not imply that ordinary membership management already implements them.

The reviewed metadata and provider-authentication contracts retain their historical tracking in [issue 121](https://github.com/matejpalenik/inframeld/issues/121) and [issue 151](https://github.com/matejpalenik/inframeld/issues/151). These links record context, not another registry or implementation claim.

- [Model connections](../../inframeld-application-contracts/references/model-gateway-and-connections.md), [shared current access](../../inframeld-application-contracts/references/model-connection-changes.md#shared-current), [provider authentication](provider-credential-storage.md#provider-authentication), [model metadata](../../inframeld-application-contracts/references/model-validation.md#model-metadata), [validation evidence](../../inframeld-application-contracts/references/model-validation.md#model-validation-evidence) and [spending](../../inframeld-application-contracts/references/spending-and-accounting.md#spending).
- [Embedding compatibility](../../inframeld-indexing/references/materialization-verification.md#embedding-compatibility), [connection records](../../inframeld-application-contracts/references/model-connection-changes.md#shared-current-connections), [metadata provenance](../../inframeld-application-contracts/references/model-metadata-and-validation.md#model-metadata-provenance), [budget authority](../../inframeld-application-contracts/references/spending-and-accounting.md#budget-policy-authority) and [import review](../../inframeld-application-contracts/references/configuration-import-review.md#destination-review).
- [ADR-0048](../../../../docs/adr/ADR-0048-encrypt-outbound-credentials-in-postgresql-using-pynacl.md), [ADR-0050](../../../../docs/adr/ADR-0050-make-model-preflight-optional-and-record-runtime-validation.md) and [ADR-0054](../../../../docs/adr/ADR-0054-use-shared-current-model-connections.md). ADR-0050 partially supersedes ADR-0025's separate-probe prerequisite. ADR-0054 replaces consumer-pinned access while preserving separate secrets and actual-revision evidence.
