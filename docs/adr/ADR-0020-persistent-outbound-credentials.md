# ADR-0020: Persistent outbound model credentials

**Status:** Accepted — persistent application-entered credentials and the PostgreSQL/PyNaCl storage boundary. Implementation qualification is pending.
**Date:** 19 September 2026.
**Required approach:** Project-scoped provider credentials, encrypted in PostgreSQL with a separately supplied persistent deployment key, and resolved only for authorized model calls.
**Source:** [Canonical architecture guide](../ARCHITECTURE.md).
**Related:** [Gateway and connections](ADR-0006-byok-provider-boundary.md), [Access](ADR-0005-api-enforced-tenancy-and-authorization.md), [idempotency](ADR-0007-durable-jobs-idempotency-and-recovery.md), [Compose deployment](ADR-0011-hosted-vercel-and-aws-deployment-profile.md).

## Context

Inframeld calls a customer's model endpoint to create embeddings and generate answers. An **embedding model** converts text into numerical vectors for search; a **generation model** produces an answer. When an endpoint requires a credential, Inframeld needs that credential each time it makes an authorized call.

An authorized user must be able to enter the credential through the application, keep it across restarts, and replace or remove it later. The eventual onboarding screen uses this backend capability. Requiring an operator to maintain provider-key files outside the application does not meet that product requirement.

From first principles, **a provider credential must be recoverable to make an outbound call, but recoverability must not become permission to reveal it to users or unrelated components**. We need encrypted persistence, explicit authorization, and a controlled path from the saved credential to its approved endpoint.

The implementation also needs to distinguish changing a secret from changing model behavior. Replacing a key should not rewrite a pipeline's history or silently move it to another endpoint. Retrying a lost save response should not create a second change or reveal the stored key.

## Decision

**Store provider credentials as authenticated ciphertext in the existing PostgreSQL database behind a small application-owned credential-store port. Use PyNaCl's `Aead` API and a separately supplied 32-byte deployment encryption key mounted read-only into the API and worker.**

**Ciphertext** is the encrypted representation of a value. **Authenticated encryption** also checks that the encrypted message and its associated binding data have not been altered. That integrity check is separate from authenticating the user who requests an operation.

Use one credential slot per project-owned provider connection. Return safe metadata through the application API, and decrypt the credential only when dispatching authorized model work.

This is a narrow credential adapter, not a general secrets platform. It introduces no new secrets service, public decryption endpoint, arbitrary secret namespace, dynamic credential issuer, or vault-administration interface.

The persistence mechanism and security behavior are accepted. Exact endpoint names and numerical input limits remain implementation details. **Qualification means testing the actual adapter and deployment; the design does not claim those tests have already passed.**

### 1. Keep outbound credentials separate from incoming authentication

Not every secret needs to be stored in a recoverable form.

| Secret                                      | Purpose                                                                                          | Storage and ownership                                                                                                                                                                                               |
| ------------------------------------------- | ------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Outbound provider credential**            | Authorizes Inframeld to call a customer's model endpoint.                                        | The gateway must recover its original value. Store authenticated ciphertext and a safe reference; decrypt only for authorized dispatch. A one-way hash is insufficient.                                             |
| **Inframeld-issued integration credential** | Authenticates an incoming customer application or supported Model Context Protocol (MCP) client. | Inframeld only verifies the high-entropy value presented by the caller. Keep its cryptographic verifier/hash, safe prefix, ownership, scope, expiry, and revocation metadata. Return plaintext once under ADR-0007. |
| **Human passwords and sessions**            | Authenticate people using Inframeld.                                                             | Kratos continues to own them. They do not move into the provider-credential store.                                                                                                                                  |

**High entropy** means a secret has enough unpredictability to resist guessing. A **verifier** lets the server check a presented secret without recovering the originally issued value.

The encrypted store is for outbound model credentials only. It does not change the existing integration-key or human-session design.

### 2. Keep authorization, connection ownership, and encryption separate

A **port** is an application-owned interface describing a capability. An **adapter** implements it using specific technology. Credential persistence is a supporting application capability behind such a port, not a seventh business domain.

| Owner                                       | Responsibility                                                                                     |
| ------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| **Model-connection commands**               | Own the stable credential reference and the behavior for replacement and removal.                  |
| **Access**                                  | Decides who can manage a connection, use it for a particular action, or inspect its safe metadata. |
| **Credential-store infrastructure adapter** | Owns the ciphertext format and interaction with the encryption library.                            |
| **Domain entities and pipeline snapshots**  | Refer to the connection/configuration without containing plaintext or encryption-library objects.  |

For v1, each **project-owned provider connection has one credential slot**. Do not create an installation-wide credential pool that is automatically shared across projects.

Permission to use a model lets an admitted build, query, or evaluation use its permitted connection through the gateway. **It does not grant permission to read the provider key.** An admitted operation is work the application has accepted for execution.

Ordinary fixed-access query integrations cannot manage credentials. Access's accepted defaults determine which initial project administrator receives credential-management authority. No broad secret-reader role is introduced.

### 3. Separate connection meaning from its replaceable credential

A **connection** identifies configured access to a provider endpoint. Its immutable **semantic revisions** record the endpoint/provider behavior selected by pipelines and profiles. Semantic configuration describes what model behavior is requested, not just which secret permits the request.

The credential slot is separate. A pipeline or profile references a semantic connection revision; the gateway resolves that connection's permitted **current credential** when it needs to make a call.

| Change                         | Required behavior                                                                                                                                                                      |
| ------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Replace the provider key**   | Keep the connection references and pipeline history. Advance the credential revision and invalidate role validation recorded for the old credential. The new value starts unvalidated. |
| **Remove the credential**      | Make it unavailable for future required-key calls and invalidate its old validation status. Existing references remain explainable through non-secret identity metadata.               |
| **Change the endpoint origin** | Create a new connection and require explicit credential provision. Never forward the saved key to another origin through a semantic revision alone.                                    |

An **origin** is the endpoint's scheme, hostname, and port. A related model name is not permission to send a credential to a different origin.

#### One connection can serve two independently validated roles

Mira creates `Company Models`, enters its key once, then selects embedding model **E** and generation model **G** on that connection. When the provider supports both roles at the same origin with the same authentication, both can use the saved credential.

The application validates the roles independently. A successful chat probe does not prove that E supports embeddings or produces the expected number of vector dimensions.

If the roles use different origins or genuinely different credentials, configure separate connections. Do not copy the secret between them implicitly.

#### Saving a replacement does not certify that it works

Initial setup checks validation for the **current credential revision** before first publication. A successful probe of the old key cannot validate its replacement.

Existing published versions may attempt to use the deliberately replaced key and report ordinary provider failures. There is no hidden rollback to an old secret or fallback to another provider/model. Credential rotation changes the live capability to call the connection, not the historical pipeline configuration.

### 4. Expose a narrow, metadata-only management API

The recommended resource path is:

```text
/v1/projects/{projectId}/model-connections/{connectionId}/credential
```

These route shapes are **recommended implementation details**, not implemented endpoints. The accepted requirement is the behavior below.

| Operation                         | Required behavior                                                                                                                                                                                                                                                                  |
| --------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **`PUT`**                         | Create or replace a bounded opaque provider value. Require credential-management authority, an `Idempotency-Key`, and the expected credential revision. Revision **0** means no credential exists. Return only credential/connection identity, revision, presence, and timestamps. |
| **`GET`**                         | Return authorized safe metadata and the current revision. There is no reveal flag, encrypted-value download, or plaintext field.                                                                                                                                                   |
| **`DELETE`**                      | Require the same management authority, idempotency key, and expected revision. Mark the credential unavailable and remove its ciphertext in one transaction. Retain the non-secret identity needed to explain existing references.                                                 |
| **Connection validation command** | Run bounded, explicitly requested role probes through `ModelGateway` using the saved credential. Record sanitized results against the semantic connection revision, credential revision, and tested role/model. Never echo provider headers or raw error bodies.                   |

An **idempotency key** identifies a retried command. An **expected revision** protects against overwriting a competing change. Their transaction behavior is described in Section 8.

#### Accept a credential value, not arbitrary outbound configuration

Bound the initial value to a small API-key/token field—for example, **16 KiB of UTF-8 text**—and treat its contents as opaque. This size is a proposed implementation limit, not a finalized value. UTF-8 defines how the submitted text is encoded as bytes.

The provider adapter supplies the known authentication header. Callers cannot use credential storage to configure arbitrary headers or proxies. Endpoint approval and server-side request forgery (SSRF) restrictions remain with ADR-0006; SSRF concerns a caller causing the server to make an unauthorized outbound request.

An explicitly configured local endpoint that needs no credential is a supported distinction. It is not the same as a required key being unexpectedly missing.

#### Show the impact of removal without preserving a hidden old key

Before authorized removal, show safe reference information identifying the affected current and retained pipeline versions. Removing the credential can intentionally prevent those versions from making future model calls.

Do not preserve an old plaintext value merely to make a rollback target appear healthy. **Deleting Inframeld's saved copy does not revoke the key at the external provider, and it cannot recall a provider call already dispatched.**

### 5. Encrypt the value and bind it to the correct resource

Use PyNaCl's maintained `Aead` API with the behavior recorded in the source:

| Encryption component         | Selected behavior                                                                                                                       |
| ---------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| **Algorithm**                | XChaCha20-Poly1305 authenticated encryption.                                                                                            |
| **Key**                      | A separately supplied **32-byte** deployment encryption key.                                                                            |
| **Nonce**                    | Let the library automatically generate a random **24-byte** nonce. Never derive it from a credential ID, timestamp, or retried command. |
| **Stored encrypted message** | Store the library's returned message, including its nonce and authentication tag. Do not invent a separate encryption/MAC construction. |

A **nonce** is a per-encryption value required by the algorithm. An **authentication tag** is integrity-checking data produced by authenticated encryption. A MAC is a message authentication code; the selected API already supplies the required authenticated-encryption construction.

The adapter stores a **format version, algorithm identifier, key identifier, and encrypted message**. The key identifier names which deployment key is needed; it is not the key itself.

#### Bind ciphertext to its organization, project, connection, and revision

**Authenticated associated data (AAD)** binds the encrypted value to its intended use and resource. The adapter constructs a canonical, unambiguous encoding of:

```text
fixed purpose and format version
    + organization ID
    + project ID
    + connection ID
    + credential ID
    + credential revision
```

Canonical encoding means the same values always have one unambiguous representation. Reconstruct them from the authorized database record, not caller-supplied encryption metadata.

Copying ciphertext into another project's row or changing its connection/reference/revision must fail authentication and prevent dispatch. **PyNaCl does not infer this resource binding; Inframeld must supply it correctly.**

There is a separate limit: an attacker with unrestricted database-write access could restore an entire older record together with all its matching binding values. AAD does not detect that complete-record rollback. Current authorization and trust in the database remain separate security boundaries.

### 6. Supply one persistent deployment key, and keep it out of the database

Provision the root encryption key once using a cryptographically secure random generator. Store it in a protected, host-managed file outside source control, container images, and the application database.

A one-time bootstrap may create the file with **exclusive creation**, restrictive permissions, and no terminal output of the key. Exclusive creation means it must not overwrite an existing file. Later starts reuse that exact persistent file.

**Never generate a replacement key on every container start or when a configured key file is missing.** Container recreation must not change the key needed to decrypt existing rows.

Docker mounts the file read-only into the API and worker only. The parser and web container receive neither this key nor direct credential-store access.

#### Keep the encryption key and request-fingerprint key distinct

| Deployment key                         | Purpose                                                                                                                                        |
| -------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| **Provider-credential encryption key** | Encrypts and decrypts saved provider credentials.                                                                                              |
| **Idempotency HMAC fingerprint key**   | Supports ADR-0007's protected request fingerprints for detecting equivalent secret-bearing commands. It must be a **different** protected key. |

HMAC is a keyed authentication hash. Keeping these keys separate preserves their different purposes.

The existing protected-deployment-state and recovery requirements apply to both. This ADR adds no backup schedule or recovery system. PostgreSQL records key identifiers, never the root encryption key.

#### Missing or wrong key material must fail visibly

Missing, malformed, or unknown key material disables credential resolution and protected credential writes with a sanitized dependency error. A replaced or wrong key cannot decrypt existing rows.

Do not erase the ciphertext, fall back to plaintext, invent another key, or switch providers to make the request appear successful.

#### Prepare for controlled root-key replacement without building key-management software

Record key IDs now so a future maintenance replacement need not change connection references. Changing the active key ID alone does not rotate already-stored ciphertext.

A future replacement procedure must retain the old key until **bounded, revision-checked re-encryption has completed and been verified**. Bounded work handles a limited set of records at a time; revision checks prevent maintenance from overwriting a concurrent credential change.

No online key-management interface or hierarchy of separate encryption keys per record is required for v1. **Replacing a provider key through the application API does not replace the deployment encryption key.**

### 7. Keep plaintext short-lived and dispatch only to the approved destination

The authorized create/replace request necessarily carries plaintext over **TLS**, the transport protection used by HTTPS, to the API. Studio clears its submitted value and receives only safe metadata. The API encrypts the value before persistence.

A reverse proxy may terminate TLS and handle the request. Request-body/header capture must therefore exclude credential routes. **The design does not claim that plaintext never passes through infrastructure processes.**

For model use, the API or worker follows this path:

```text
Admitted build, query, or evaluation
    -> Resolve the exact permitted connection revision and model role
        -> Check the current credential state
            -> Decrypt inside the credential adapter
                -> Dispatch through ModelGateway to the approved destination
                    -> Record only safe credential-revision attribution
```

Resolve the credential for each bounded call without a long-lived plaintext cache. Keep references short-lived and avoid unnecessary copies. Python's memory management does not guarantee immediate byte-for-byte zeroization, so do not claim that the key is instantly erased from memory when the call finishes.

Provider clients, framework debug tracing, and exception representations must not retain or emit the key. Jobs carry connection references, not secrets. Saved plaintext must never enter pipeline/profile snapshots, benchmark/evaluator revisions, logs, evaluation evidence, answer receipts, or API responses.

#### Check removal at the dispatch boundary

A wrong key or tampered encrypted envelope prevents provider dispatch. A credential removed before the final resolution check also prevents new dispatch.

Removal after a call has crossed that boundary cannot undo the already-admitted call. **There is no distributed revocation transaction with the provider:** the local database change and the remote execution are not one atomic action.

### 8. Commit credential changes and safe retry outcomes together

Encryption is local work. Use one PostgreSQL transaction to reserve the idempotency key, conditionally update the credential revision, store its ciphertext, and record the sanitized command result.

```text
One PostgreSQL transaction
    -> Reserve the request's idempotency key
    -> Apply the expected credential-revision check
    -> Store the ciphertext and updated credential state
    -> Record the metadata-only outcome
    -> Commit together, or roll back together
```

A transaction rollback publishes none of these changes. There is no separate vault write that can succeed while its application reference remains uncertain.

#### Fingerprint the submitted secret without saving it in retry metadata

The request fingerprint includes the secret through ADR-0007's **domain-separated keyed HMAC**. Domain separation identifies the purpose of the fingerprint. Never store the request body or an unkeyed digest of a possibly guessable credential in idempotency metadata.

| Situation                                                   | Required behavior                                                                                                           |
| ----------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| **Same key and equivalent request**                         | After current authorization checks, return the safe recorded outcome without another mutation or revealing the saved value. |
| **Same key with a different secret**                        | Conflict: this is not an equivalent retry.                                                                                  |
| **Successful save response is lost**                        | Retrying can recover the metadata-only outcome. Decryption is never part of response replay.                                |
| **Two genuine changes expect the same credential revision** | Only one conditional mutation succeeds; the other receives a stale-revision conflict.                                       |
| **An old completed command is replayed after later edits**  | Return that command's historical safe outcome without reverting current state.                                              |

#### Worked example: two operators replace revision 3

Mira and Dan both read credential revision **3** and request a replacement.

Mira's transaction creates revision **4**. Dan receives **`409 stale_revision`**, reads the current metadata, and deliberately decides whether another replacement is needed. His stale request cannot overwrite revision 4.

If Mira loses her response, retrying her original command returns its safe recorded result. If another edit has since created revision 5, that replay still describes Mira's completed change; it does not restore revision 4.

#### Keep provider validation outside the credential-save outcome

Validation is a separate recorded operation. Saving a key is not proof that the provider accepts it.

A probe whose chargeable outcome becomes uncertain follows ADR-0007's normal uncertain-call rule. A missing response is not permission to hide a second provider request inside credential validation.

### 9. State exactly what this encryption boundary protects

Encryption protects a copied credential table **when the attacker does not also have the deployment key**. It does not protect credentials from a compromised API or worker that legitimately has access to that key, or from a host administrator controlling those processes.

Using a separate vault would not make a compromised caller harmless if that caller still held credentials permitting it to read provider keys. The selected design makes this limit explicit rather than presenting encrypted storage as protection against every running-system compromise.

The smaller runtime therefore leaves real responsibilities with Inframeld: root-key custody, resource binding, current permissions, limited plaintext lifetime, sanitized errors, concurrent-update handling, and focused security tests.

### 10. Qualify the adapter and connection use cases together

The minimum tests belong with the credential adapter and connection operations. They are planned acceptance tests, not evidence already collected.

| Area                               | Required verification                                                                                                                                                                                                                                                                 |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Persistence and model roles**    | Save a key, restart the API/worker, and use the same saved key for real bounded embedding and generation calls through one connection. Keep failures in the two role validations distinct.                                                                                            |
| **Integrity and resource binding** | Tamper with ciphertext, nonce, project/connection binding, credential revision, and key ID. Each case must prevent dispatch. Missing or wrong root keys must not generate replacement material.                                                                                       |
| **Concurrent changes and retries** | Race replacements and repeat a lost-response request. Verify one conditional mutation, correct idempotency behavior, and metadata-only responses.                                                                                                                                     |
| **Removal**                        | Remove a credential and deny subsequent dispatch without claiming to cancel a call already sent. Do not reuse a cached old plaintext value or fall back to another provider.                                                                                                          |
| **Authorization and disclosure**   | Exercise unauthorized management/use, cross-project references, request-validation failures, provider exceptions, and library debug paths. Assert that submitted/saved keys never appear in responses, persisted jobs, receipts, snapshots, logs, or the parser's environment/mounts. |

These tests are focused enough for one developer and are necessary before relying on the credential path. This ADR adds no performance claim, implementation audit, or qualified image lock.

## Consequences

### Positive

- **Provider credentials become part of ordinary application setup.** Authorized users can save and replace them without editing host files, and the same connection can support separately validated embedding and generation roles across restarts.
- **Credential persistence and retry outcomes share one transaction.** PostgreSQL records ciphertext, revision, and sanitized command results together, avoiding coordination with a second secrets store.
- **The runtime remains small without inventing cryptography.** A narrow adapter uses maintained authenticated encryption and automatic nonce generation, while keeping application permissions, model configuration, and incoming identity credentials separate.

### Negative

- **Inframeld remains responsible for the security around encryption.** Correct binding, protected deployment keys, current authorization, limited plaintext exposure, redaction, concurrency checks, and failure tests still require implementation work.
- **Losing or replacing the deployment key can make saved credentials unusable.** Persistent key custody and recovery are essential; recording a new key ID alone does not re-encrypt existing data. Compromised privileged processes or the host remain outside the copied-table protection.
- **Credential changes can affect live and retained pipelines immediately.** A replacement starts unvalidated, and removal can prevent future calls. No old-key or provider fallback hides that effect, and local deletion neither revokes the external key nor recalls an already-dispatched call.

## Alternatives considered

### Encrypted PostgreSQL with PyNaCl `Aead` — selected

Reuse maintained authenticated encryption, integrity checking, and automatic random nonce generation. Keep root-key injection, resource binding, permissions, short plaintext lifetimes, sanitized errors, concurrent updates, and tests in the application.

The main fit for this initial product is transactional: the ciphertext and command/idempotency outcome commit in the same existing database. PyNaCl's high-level handling of extended random nonces reduces the nonce-management work Inframeld must implement itself.

### OpenBao KV v2

**Not selected as a mandatory v1 dependency.** OpenBao supplies HTTP secret storage, versioning, policies, and compare-and-set writes, which condition an update on the expected stored state.

Inframeld would still own project/connection policy, authorization, redaction, and coordination between connection references and vault writes. It would also need to deploy and initialize the service, manage its unseal trust, configure application authentication/policies, and manage token lifecycles. **Unsealing** makes the vault's protected storage available for use.

The objection is not simply one additional container. The initial handful of model credentials does not justify that mandatory runtime and second persistence boundary, while the product still needs its own access decisions.

OpenBao is credible when a customer already operates the necessary trust infrastructure or secrets become a larger product requirement. Its documented static-file auto-unseal option does not eliminate root-key custody; the source records that OpenBao limits the circumstances in which this arrangement is recommended.

### Encrypted PostgreSQL with `cryptography` `AESGCM`

**A viable alternative, not an additional selected library.** It provides maintained authenticated encryption and associated-data support, leaving the same application responsibilities, including correct nonce generation and non-reuse.

The selection favors PyNaCl's high-level automatic extended-nonce handling as a reduction in implementation responsibility. Do not add both libraries merely to offer an algorithm choice.

### Deployment-managed secret files

**Retained for deployment material, insufficient for provider-credential entry.** Docker supplies service-scoped file mounts, while the operator must provision/change the files, protect them on the host, and map safe references.

Use this approach for the root encryption key, the separate idempotency-fingerprint key, and infrastructure secrets. Files alone do not let an authorized user persist a provider credential through the running application API.

## References

### Related decisions

| Reference                                                                            | Responsibility                                                                                                   |
| ------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------- |
| [Canonical architecture guide](../ARCHITECTURE.md)                                   | Overall application structure and model-connection ownership.                                                    |
| [ADR-0006: Gateway and connections](ADR-0006-byok-provider-boundary.md)              | Approved endpoints, semantic connection revisions, separate model roles, and outbound-request restrictions.      |
| [ADR-0005: Access](ADR-0005-api-enforced-tenancy-and-authorization.md)               | Current management/use permissions, project scope, and the distinction between human and integration identities. |
| [ADR-0007: Idempotency](ADR-0007-durable-jobs-idempotency-and-recovery.md)           | Secret-bearing request fingerprints, safe replay outcomes, incoming-key issuance, and uncertain provider calls.  |
| [ADR-0011: Compose deployment](ADR-0011-hosted-vercel-and-aws-deployment-profile.md) | Service-specific secret mounts and protected persistent deployment configuration.                                |

### Recorded external evidence

The original ADR records the following observations from **19 September 2026**. They are retained as source evidence, not freshly verified releases or qualified Inframeld dependencies.

| Component                               | Recorded observation and boundary                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| --------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **OpenBao 2.6.2**                       | The observed released version, under MPL-2.0. `2.7.0-beta20260909` is a prerelease and is not assumed here. Its maintained KV, authentication, and unseal APIs make it a realistic alternative, not a selected dependency. [Release](https://github.com/openbao/openbao/releases/tag/v2.6.2), [source license](https://github.com/openbao/openbao/blob/v2.6.2/LICENSE).                                                                                                                         |
| **PyNaCl 1.6.2**                        | Released **1 January 2026**; the source records an updated bundled libsodium build and the inspected `Aead` interface. Its Apache-2.0 source license fits the intended dependency policy; retain packaging notices. This is an initial library candidate, not an installed or qualified image lock. [Changelog](https://pynacl.readthedocs.io/en/latest/changelog/), [published package](https://pypi.org/project/PyNaCl/1.6.2/), [license](https://github.com/pyca/pynacl/blob/1.6.2/LICENSE). |
| **`cryptography` 50.0.1 documentation** | The observed stable documentation version. `AESGCM` supplies authenticated encryption and associated data and explicitly requires nonce non-reuse. It remains an alternative, not another framework to deploy. [Versioned API](https://cryptography.io/en/50.0.1/hazmat/primitives/aead/).                                                                                                                                                                                                      |

These version and licensing observations come from the source ADR's recorded review.

[PyNaCl's encryption documentation](https://pynacl.readthedocs.io/en/latest/secret/) and [tagged 1.6.2 implementation](https://github.com/pyca/pynacl/blob/1.6.2/src/nacl/secret.py) are the recorded references for `Aead`, automatic nonce handling, and the encrypted-message format.

The OpenBao comparison uses its [KV v2 documentation](https://openbao.org/docs/secrets/kv/kv-v2/), [AppRole application-authentication documentation](https://openbao.org/docs/auth/approle/), and [static-seal documentation](https://openbao.org/docs/configuration/seal/static/). [Docker Compose secret mounts](https://docs.docker.com/compose/how-tos/use-secrets/) is the recorded reference for supplying protected files to selected services.
