# Connecting models and protecting provider credentials

Alice configures Support's model connection so the application can create search embeddings and generate answers. This guide explains where those calls may go, how the provider key is saved, and what changes when it is replaced. SupportBot can use an authorized query without being able to reveal that key.

[Access](access-control.md) owns permissions. The [supporting records](data-model.md#supporting-records) define connections, revisions, model roles, and the encrypted credential format.

Start with ModelGateway and approved destinations. Then follow saving a key, using it for a call, replacing it, and restarting with the same protected encryption key.

> **Design status:** These are accepted v1 boundaries. Route shapes and some size limits remain recommendations. The chosen adapters, credential storage, and security tests still need implementation and verification.

## Contents

| Reader’s question | Start here |
| --- | --- |
| What does ModelGateway own? | [1. One model boundary, several roles](#model) |
| How do private endpoints stay safe? | [2. Approve and validate a destination](#destinations) |
| Does working chat prove embeddings work? | [3. Validate the selected capabilities](#roles) |
| Who may manage which secret? | [4. Save and replace a provider key](#credentials) |
| When can removal stop a call? | [5. Resolve a credential for each call](#dispatch) |
| What happens after a lost save response? | [6. Commit a change and its retry result together](#coordination) |
| What happens on restart or key loss? | [7. Protect the persistent encryption key](#root-key) |
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
| **Run the v1 faithfulness judge** | A model call through `ModelGateway`, even when an evaluation library coordinates it. |
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

The local cross-encoder uses a separate Reranker interface to reorder retrieved excerpts by relevance.

Docling uses DocumentProcessor and Chunker to convert files and divide them into search excerpts.

Neither silently calls a remote language model. A future remote processor must explicitly describe which data leaves the installation and where it goes.

Save the connection's model and endpoint settings separately from its replaceable secret. A Pipeline keeps its exact settings while using the connection's current usable key. Changing the approved origin must never forward the old key to a different destination automatically.

<a id="destinations"></a>

## 2. Approve and validate a destination

Custom endpoints could otherwise let a caller make the server contact arbitrary addresses. This is **server-side request forgery (SSRF)**. Approval and destination checks prevent a model request from becoming unrestricted network access.

There are two distinct configuration responsibilities:

| Who | What they may configure |
| --- | --- |
| **Deployment administrator** | Approves the allowed endpoint origins through deployment configuration. |
| **Human with the required project permission** | Creates a connection within that deployment policy. A project connection cannot expand it. |

A query or evaluation chooses an already configured connection. It cannot supply its own endpoint URL.

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

Choose embedding and generation models separately and test each role. They may share one project connection and key when origin and authentication match. Otherwise use separate connections.

Sharing a connection does not require the roles to use the same model, and successful generation does not establish that embeddings work.

For example, a private gateway exposes both a chat model and an embedding model. Alice enters one key and chooses the two models. Inframeld still tests both capabilities and checks embedding dimensions.

### Test what the selected role actually needs

An OpenAI-compatible label does not prove every operation or feature works. Run limited probes for the chat and embedding capabilities the configuration actually needs.

Reject wrong response shapes, unsupported operations, incorrect embedding dimensions, and non-finite numbers such as infinity or NaN. Candidate and citation IDs must name real application evidence, not invented sources.

Return defined error outcomes that the application and clients can recognize. Invalid responses must not be silently accepted.

Replacing or removing a key invalidates earlier role-validation results. A test of the old key cannot validate the new one. This changes whether the connection is usable, without rewriting a Pipeline's saved configuration.

### Evaluation setup is not a prerequisite for the first answer

[First-use setup](onboarding.md) needs working embeddings and generation. Alice needs neither a judge nor a benchmark of evaluation cases before asking her first question.

V1 evaluation still requires a faithfulness judge. OpenEvals and configurable GPT-6 Luna are the selected starting point to test under [Evaluation](evaluation.md). Their selection is not evidence of passed tests.

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
| **Connection validation command** | Run bounded, explicitly requested role probes through `ModelGateway` using the saved credential. Record sanitized results against the semantic connection revision, credential revision, and tested role/model. Never echo provider headers or raw error bodies. |

The idempotency key identifies a retry, while the expected credential revision detects someone else's intervening change. [Saving changes and retry outcomes](model-connections.md#coordination) explains how they work together.

### Accept a credential value, not arbitrary outbound configuration

Accept a small, opaque API-key or token value. **16 KiB of UTF-8 text** is a proposed byte limit, not yet finalized. UTF-8 defines how text is encoded into bytes.

The provider adapter chooses its known authentication header. This field cannot configure arbitrary headers or proxies. All [destination and SSRF checks](model-connections.md#destinations) still apply.

An explicitly configured local endpoint that needs no credential is a supported distinction. It is not the same as a required key being unexpectedly missing.

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
    -> Resolve the exact permitted connection revision and model role
        -> Check the current credential state
            -> Decrypt inside the credential adapter
                -> Dispatch through ModelGateway to the approved destination
                    -> Record only safe credential-revision attribution
```

Resolve the key separately for each limited call. Avoid long-lived plaintext caches and unnecessary copies. Python cannot guarantee immediate erasure of every memory byte when a call finishes, so do not claim that guarantee.

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
| **Run the faithfulness judge** | The judge’s configured answer/evidence payload goes through `ModelGateway` to its connection. [Evaluation](evaluation.md#metrics) defines the exact rubric inputs. Disclose these additional model calls. |
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

Validation is a separate recorded operation. Successfully saving a key does not prove the provider accepts it.

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
| **Credential lifecycle** | Test persistent storage and rotation. Replacing/removing a credential invalidates old role-validation status without rewriting pipeline semantics. |
| **No implicit rerouting** | Verify that missing credentials and provider failures do not select another provider/model, and that an origin change does not implicitly forward an existing key. |
| **Gateway ownership** | Test evaluator attempts to bypass `ModelGateway`. No independent provider client or framework retry may evade the shared rules. |

These are acceptance requirements, not claims that implementation qualification has already passed.

### Qualify the adapter and connection use cases together

Place the focused security tests with the credential adapter and connection operations. The table records requirements, not results already collected.

| Area | Required verification |
| --- | --- |
| **Persistence and model roles** | Save a key, restart the API/worker, and use the same saved key for real bounded embedding and generation calls through one connection. Keep failures in the two role validations distinct. |
| **Integrity and resource binding** | Tamper with ciphertext, nonce, project/connection binding, credential revision, and key ID. Each case must prevent dispatch. Missing or wrong root keys must not generate replacement material. |
| **Concurrent changes and retries** | Race replacements and repeat a lost-response request. Verify one conditional mutation, correct idempotency behavior, and metadata-only responses. |
| **Removal** | Remove a credential and deny subsequent dispatch without claiming to cancel a call already sent. Do not reuse a cached old plaintext value or fall back to another provider. |
| **Authorization and disclosure** | Exercise unauthorized management/use, cross-project references, request-validation failures, provider exceptions, and library debug paths. Assert that submitted/saved keys never appear in responses, persisted jobs, receipts, snapshots, logs, or the parser's environment/mounts. |

These checks are necessary before relying on provider credentials and are intended to remain manageable for one developer. They imply no performance result, completed security audit, or tested image lock.

<a id="decision-map"></a>

## 9. Decision and reference map

Route shapes and the 16 KiB limit remain recommendations. Saving and validating a key remain separate. LiteLLM and private-endpoint compatibility need tests. Root-key replacement is future controlled maintenance, not an online key-management product.

| Decision | Rationale |
| --- | --- |
| [ADR-0023](../adr/ADR-0023-route-every-model-request-through-modelgateway.md) | Route every model request through ModelGateway. |
| [ADR-0024](../adr/ADR-0024-approve-outbound-destinations-before-model-calls.md) | Approve outbound destinations before model calls. |
| [ADR-0025](../adr/ADR-0025-separate-connection-meaning-from-replaceable-credentials.md) | Separate connection meaning from replaceable credentials. |
| [ADR-0048](../adr/ADR-0048-encrypt-outbound-credentials-in-postgresql-using-pynacl.md) | Encrypt outbound credentials in PostgreSQL using PyNaCl. |
