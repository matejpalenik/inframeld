# Protect stored provider credentials

<a id="protect-stored-provider-credentials"></a>

Alice saves a model provider key so the backend can call that provider later. Unlike an incoming application key, its original value must be recoverable. Encryption, resource binding and current permission each protect a different boundary.

> **Status:** accepted behavior is stated separately from proposed representations and qualification work. Existing Python types, generated OpenAPI and migrations own implemented shapes. Pending decisions are not accepted by this reference.

## Approved management and qualification contract

Alice's revision-7 replacement cannot overwrite Bob's committed revision 8. Check the reviewed revision and current authority, then save the ciphertext/removal, resulting credential revision, required audit and safe original retry outcome together. A lost response recovers safe metadata without another mutation or secret echo. Missing/wrong deployment keys or damaged/swapped ciphertext stop affected calls explicitly, without a replacement key or old-secret fallback.

[PD-ACCESS-05](decision-provider-secret-lifecycle.md#approved-resolution), accepted in ADR-0103 on 2026-10-29, owns the complete logical input/result, failure and qualification contract. Implement in stages and require assembled management, dispatch and restore evidence before claiming the whole secret boundary is qualified. Existing Aead, associated-data binding and offline root-key lifecycle remain selected.

<a id="keep-current-access-and-credentials-separate"></a>

### Keep current access and credentials separate

The [shared connection access revisions](../../inframeld-application-contracts/references/model-connection-changes.md) record the connection's history. They do not freeze its endpoint for retained Pipeline versions. Selected model behavior still belongs to immutable consumer configuration, subject to the [external-alias limitation](../../inframeld-application-contracts/references/model-gateway-and-connections.md).

The credential slot changes independently. At call time, the gateway uses the selected connection's permitted **current access configuration and current credential**, while the Pipeline retains its selected connection ID and model settings. Relevant access changes stop further dispatches in already admitted work. Credential-only rotation does not by itself do so.

| Change | Required behavior |
| --- | --- |
| **Replace the provider key** | Keep the connection references and pipeline history. Advance the credential revision and invalidate role validation recorded for the old credential. The new value starts unvalidated. |
| **Remove the credential** | Make it unavailable for future required-key calls and invalidate its old validation status. Existing references remain explainable through non-secret identity metadata. |
| **Change the endpoint origin** | Apply the [guarded connection update](../../inframeld-application-contracts/references/model-connection-changes.md), including explicit destination-bound credential provision and atomic activation. Historical restoration never restores old credential bytes. |

The origin is the scheme, hostname, and port. A similar model name is not permission to send a saved key to a different origin.

<a id="encrypt-the-value-and-bind-it-to-the-correct-resource"></a>

### Encrypt the value and bind it to the correct resource

The selected encryption uses PyNaCl's `Aead` API with these recorded requirements:

| Encryption component | Selected behavior |
| --- | --- |
| **Algorithm** | XChaCha20-Poly1305 authenticated encryption. |
| **Key** | A separately supplied **32-byte** deployment encryption key. |
| **Nonce** | Let the library automatically generate a random **24-byte** nonce. Never derive it from a credential ID, timestamp, or retried command. |
| **Stored encrypted message** | Store the library's returned message, including its nonce and authentication tag. Do not invent a separate encryption/MAC construction. |

A **nonce** is the per-encryption value the algorithm needs. An **authentication tag** detects changes to the encrypted message. The selected API provides authenticated encryption already, so no separate message authentication code (MAC) construction is needed.

Store the **format version, algorithm identifier, key identifier, and encrypted message**. A key identifier names the separately supplied deployment key. It does not contain that key.

<a id="bind-ciphertext-to-its-organization-project-connection-and-revision"></a>

### Bind ciphertext to its organization, project, connection, and revision

**Authenticated associated data (AAD)** ties an encrypted credential to the record where it belongs. Encode these values unambiguously:

```text
fixed purpose and format version
    + organization ID
    + project ID
    + connection ID
    + credential ID
    + credential revision
```

The same values must always produce the same encoding. Reconstruct them from the authorized database record, never from caller-supplied encryption metadata.

If someone copies ciphertext to another project or changes its connection, reference, or revision, verification must fail and block the call. **Inframeld supplies this resource binding. PyNaCl cannot infer it.**

This has a limit: an attacker able to rewrite the entire database record could restore an older ciphertext together with all its matching values. AAD does not detect that complete rollback. Trust in the database and current permission checks remain necessary.

<a id="submitted-provider-credentials-are-never-echoed"></a>

### Submitted provider credentials are never echoed

A provider-credential submission never returns the submitted secret, so its safe status can be replayed.

The [PostgreSQL credential adapter](../../inframeld-application-contracts/references/model-gateway-and-connections.md) saves the encrypted secret, its credential revision, and the safe retry outcome in one transaction. **Ciphertext** is the encrypted value. Keeping these together avoids a separate vault write that could succeed while the database write fails, or vice versa.

The request uses the [shared keyed request fingerprint](../../inframeld-application-contracts/references/idempotency-and-replay.md). The API never returns the saved provider key.

<a id="save-and-replace-a-provider-key"></a>

<a id="credentials"></a>

<a id="4-save-and-replace-a-provider-key"></a>

## Save and replace a provider key

Inframeld must recover a provider secret to send it to that provider. It only needs to verify an incoming application key. These different uses require different storage:

| Secret | Purpose | Storage and ownership |
| --- | --- | --- |
| **Outbound provider credential** | Authorizes Inframeld to call a customer's model endpoint. | The gateway must recover its original value. Store authenticated ciphertext and a safe reference. Decrypt only for authorized dispatch. A one-way hash is insufficient. |
| **Inframeld-issued integration credential** | Authenticates an incoming customer application or supported Model Context Protocol (MCP) client. | Inframeld only verifies the high-entropy value presented by the caller. Keep its cryptographic verifier/hash, safe prefix, ownership, scope, expiry, and revocation metadata. Return plaintext once under [Background jobs, retries, and competing changes](../../inframeld-application-contracts/references/jobs-and-recovery.md). |
| **Human passwords and sessions** | Authenticate people using Inframeld. | Kratos continues to own them. They do not move into the provider-credential store. |

**High entropy** means enough randomness to resist guessing. A **verifier** checks a submitted secret without recovering the original value.

The encrypted store is for outbound model credentials only. It does not change the existing integration-key or human-session design.

<a id="keep-authorization-connection-ownership-and-encryption-separate"></a>

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

<a id="expose-a-narrow-metadata-only-management-api"></a>

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

The idempotency key identifies a retry, while the expected credential revision detects someone else's intervening change. [Saving changes and retry outcomes](#coordination) explains how they work together.

<a id="accept-a-credential-value-not-arbitrary-outbound-configuration"></a>

### Accept a credential value, not arbitrary outbound configuration

Accept a small, opaque API-key or token value. **16 KiB of UTF-8 text** is a proposed byte limit, not yet finalized. UTF-8 defines how text is encoded into bytes.

The provider adapter chooses its known authentication header. This field cannot configure arbitrary headers or proxies. All [destination and SSRF checks](../../inframeld-application-contracts/references/model-dispatch-and-destinations.md#destinations) still apply.

An explicitly configured local endpoint that needs no credential is a supported distinction. It is not the same as a required key being unexpectedly missing.

<a id="provider-authentication"></a>

<a id="supply-the-provider-key-once-not-with-every-query"></a>

### Supply the provider key once, not with every query

Alice creates `company-gateway` at `https://models.company.example/v1`, selects the supported API-key Bearer method and enters the raw key through hidden input. Inframeld saves it using the encrypted store above. When she later queries a Pipeline, her CLI sends her Inframeld credential to Inframeld. The backend resolves the saved provider key and constructs the provider header. She never attaches the provider key to an ordinary query.

```text
CLI -- Inframeld human token or application key --> Inframeld API
Backend -- selected connection's provider credential --> model server
```

These are different trust boundaries. Ory authenticates the human Inframeld path. It neither issues nor verifies the external provider's key. Inframeld-issued `ifm_app_` keys likewise never become upstream model credentials. The selected provider/gateway operator supplies that upstream credential.

For a supported OpenAI-compatible API-key method, the adapter sends `Authorization: Bearer <key>`. Users enter the key value, not a header or a `Bearer` prefix. [OpenAI documents this convention](https://developers.openai.com/api/reference/overview#authentication). Compatibility of request/response shapes alone does not guarantee identical authentication. Other supported providers use their qualified adapter's known method. Unsupported authentication fails explicitly, not through arbitrary headers, ambient credentials, a fabricated key, provider fallback or an invented OAuth exchange.

The explicitly approved local Ollama connection can be credential-free, consistent with [Ollama's local API](https://docs.ollama.com/api/authentication). This is not a claim that hosted/cloud Ollama is unauthenticated. A required key that is missing or undecryptable blocks dispatch. A provider authentication rejection is reported safely without trying another credential. All outbound calls carrying an authentication secret require certificate-verified HTTPS, including metadata reads. Destination/auth-method changes retain explicit credential binding and atomic activation. No old key is forwarded implicitly.

Reuse a connection for eligible model selections without revealing or copying its key. A different key uses a separate connection, unless the user deliberately requests shared credential replacement. Hidden human entry and protected file/stdin input for noninteractive authorized administration remain the same workflow. No secrets in argv, environment, TOML, ordinary results, traces or logs. Exact supported authentication methods and error mappings remain implementation and qualification obligations, not blanket cloud-IAM support.

<a id="show-the-impact-of-removal-without-preserving-a-hidden-old-key"></a>

### Show the impact of removal without preserving a hidden old key

Before removing a key, show safe references to the affected current and retained Pipeline versions. Removal can deliberately stop their future model calls.

Do not keep hidden old plaintext to make rollback appear healthy. Deleting Inframeld's copy neither revokes the provider's key nor recalls a call already sent.

<a id="commit-a-change-and-its-retry-result-together"></a>

<a id="coordination"></a>

<a id="6-commit-a-change-and-its-retry-result-together"></a>

## Commit a change and its retry result together

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

<a id="fingerprint-the-submitted-secret-without-saving-it-in-retry-metadata"></a>

### Fingerprint the submitted secret without saving it in retry metadata

Include the submitted secret in the request's [domain-separated HMAC fingerprint](../../inframeld-application-contracts/references/jobs-and-recovery.md), using a separate protected key and a label for this purpose. Never keep the raw request or an ordinary hash of a possibly guessable secret in retry metadata.

| Situation | Required behavior |
| --- | --- |
| **Same key and equivalent request** | After current authorization checks, return the safe recorded outcome without another mutation or revealing the saved value. |
| **Same key with a different secret** | Conflict: this is not an equivalent retry. |
| **Successful save response is lost** | Retrying can recover the metadata-only outcome. Decryption is never part of response replay. |
| **Two genuine changes expect the same credential revision** | Only one conditional mutation succeeds. The other receives a stale-revision conflict. |
| **An old completed command is replayed after later edits** | Return that command's historical safe outcome without reverting current state. |

<a id="worked-example-two-operators-replace-revision-3"></a>

### Worked example: two operators replace revision 3

Alice and Bob both read credential revision **3** and request a replacement.

Alice saves revision 4. Bob's request still expects 3, so it returns `409 stale_revision`. He reads current metadata and makes a fresh decision. His outdated request cannot overwrite Alice's key.

If Alice loses her response, repeating her original request returns its recorded safe result. Even if revision 5 now exists, that reply describes her earlier change and does not restore revision 4.

<a id="protect-the-persistent-encryption-key"></a>

<a id="root-key"></a>

<a id="7-protect-the-persistent-encryption-key"></a>

## Protect the persistent encryption key

Generate the root encryption key once with a cryptographically secure random generator. Keep it in a protected host-managed file outside source control, container images, and the application database.

One-time setup may create the file exclusively, with restricted permissions and no secret printed to the terminal. Exclusive creation refuses to overwrite an existing file. Later starts reuse that exact file.

**Never generate a replacement key on every container start or when a configured key file is missing.** Container recreation must not change the key needed to decrypt existing rows.

Mount the file read-only into only the API and worker. Neither the parser nor Studio's web container gets it or direct credential-store access.

<a id="keep-the-encryption-key-and-request-fingerprint-key-distinct"></a>

### Keep the encryption key and request-fingerprint key distinct

| Deployment key | Purpose |
| --- | --- |
| **Provider-credential encryption key** | Encrypts and decrypts saved provider credentials. |
| **Idempotency HMAC fingerprint key** | Supports [Background jobs, retries, and competing changes](../../inframeld-application-contracts/references/jobs-and-recovery.md)'s protected request fingerprints for detecting equivalent secret-bearing commands. It must be a **different** protected key. |

HMAC uses a secret key to authenticate a hash. Its key and the credential-encryption key are separate because they serve different purposes.

Protect and recover both keys under the existing deployment-state rules. This adds no separate backup system or schedule. PostgreSQL stores key IDs, never the root encryption key itself.

<a id="missing-or-wrong-key-material-must-fail-visibly"></a>

### Missing or wrong key material must fail visibly

Missing, malformed, or unknown key material disables decryption and protected credential writes with a safe dependency error. Replacing the file with the wrong key cannot decrypt existing records.

Do not erase the ciphertext, fall back to plaintext, invent another key, or switch providers to make the request appear successful.

<a id="prepare-for-controlled-root-key-replacement-without-building-key-management-software"></a>

### Prepare for controlled root-key replacement without building key-management software

Store key IDs now so future maintenance can replace the root key without changing connection references. Selecting a new active ID alone does not re-encrypt old records.

Future root-key replacement must keep the old key until re-encryption is complete and verified. Work in limited batches and check each record's revision so maintenance cannot overwrite a simultaneous credential edit.

V1 needs no online key-management UI or hierarchy of separate keys for every record. Replacing a provider secret in the application does not replace this deployment encryption key.

<a id="state-exactly-what-this-encryption-boundary-protects"></a>

### State exactly what this encryption boundary protects

Encryption protects a stolen copy of the credential table only if the attacker lacks the deployment key. It does not protect secrets from a compromised API or worker that can decrypt them, or a host administrator controlling those processes.

A separate vault would have the same limitation if the compromised caller could still retrieve keys from it. Encrypted storage is not protection against every compromise of a running system.

Inframeld still owns the practical safeguards: protecting the root key, binding ciphertext to its resource, checking current permissions, limiting plaintext lifetime, returning safe errors, handling competing edits, and testing these boundaries.

The [data model](../../inframeld-application-contracts/references/components-and-services.md#supporting-records) defines PyNaCl encryption fields, nonces, and resource binding. Mounted files suit root and infrastructure secrets. Merely mounting provider-secret references would not supply the required in-app credential management.

<a id="qualify-the-adapter-and-connection-use-cases-together"></a>

### Qualify the adapter and connection use cases together

Place the focused security tests with the credential adapter and connection operations. The table records requirements, not results already collected.

| Area | Required verification |
| --- | --- |
| **Persistence and model roles** | Save a key, restart the API/worker, and use the same saved key for real bounded embedding and generation calls through one connection. Keep failures in the two role validations distinct. |
| **Integrity and resource binding** | Tamper with ciphertext, nonce, project/connection binding, credential revision, and key ID. Each case must prevent dispatch. Missing or wrong root keys must not generate replacement material. |
| **Concurrent changes and retries** | Race replacements and repeat a lost-response request. Verify one conditional mutation, correct idempotency behavior, and metadata-only responses. |
| **Removal** | Remove a credential and deny subsequent dispatch without claiming to cancel a call already sent. Do not reuse a cached old plaintext value or fall back to another provider. |
| **Destination transition** | Change origin or authentication binding with an explicitly provisioned credential, and separately test an allowed credential-free transition. Access and credential changes commit together or neither does. An omitted key cannot forward the old secret. |
| **Authorization and disclosure** | Exercise unauthorized management/use, cross-project references, request-validation failures, provider exceptions, and library debug paths. Assert that submitted/saved keys never appear in responses, persisted jobs, receipts, snapshots, logs, or the parser's environment/mounts. |

These checks are necessary before relying on provider credentials and are intended to remain manageable for one developer. They imply no performance result, completed security audit, or tested image lock.
