---
name: inframeld-access-models
description: Explain or review Inframeld Kratos identity, organization/project grants, document-group access, fixed integrations, provider connections, model roles and persistent outbound credentials. Use for identity, permission or gateway-security boundaries, not generic authentication tutorials.
---

# Inframeld Access and Model Connections

Keep identity, application permission and outbound provider capability separate. They often meet in one setup or serving task, which justifies one skill, but Access does not become the owner of indexing or provider SDK behavior.

## Scope and sources

Default to read-only assistance. This skill grants no permission to edit code, issue credentials, contact a provider or change grants. Paths are repository-root relative. Read the applicable guide section and owning ADR before a detailed claim.

- `docs/ARCHITECTURE.md`: first-use, users/integrations and ModelGateway sections.
- `docs/adr/ADR-0005-api-enforced-tenancy-and-authorization.md`: Access policy.
- `docs/adr/ADR-0006-byok-provider-boundary.md`: connections, roles and egress.
- `docs/adr/ADR-0020-persistent-outbound-credentials.md`: accepted persistence requirement and accepted PostgreSQL/PyNaCl encrypted storage.
- `docs/adr/ADR-0019-default-onboarding-and-first-publication.md`: accepted private access defaults and accepted reversible publication modes.
- Read ADR-0007 for secret-bearing idempotency, ADR-0017 for feedback rights, ADR-0018 for MCP credentials and ADR-0014 for deletion/revocation as needed.

## Language and ownership

A Principal is the stable authenticated human/application actor. Organization and Project bound ownership. Action grants authorize operations; document-group allowlists narrow readable content. The access context has a verified actor and an optional verified delegated subject. In v1 fixed integrations have no subject.

An incoming integration credential authenticates a caller and is verified from a stored hash. An outbound provider credential is a secret the application must retrieve to call a model; hashing alone cannot support that use. A Connection records an approved endpoint and immutable semantic revisions. Embedding and generation are separate model roles, potentially sharing one connection and credential. Indexing owns EmbeddingProfile; Pipelines owns frozen generation configuration; Evaluation owns judge settings. None embeds the plaintext key.

Access owns principal/project/group/grant consistency. Connection and credential management are shared application capabilities with scoped authorization and separate secret-resolution infrastructure, not new proposed microservices. Do not infer a class/aggregate per grant, token or profile from these concepts.

## Security and lifecycle rules

1. Kratos owns human identity/sessions, including optional deployment-level external OIDC sign-in in OSS. Inframeld owns application authorization. Identity-provider email/groups do not automatically grant rights. Kratos is not Inframeld's OAuth issuer; Hydra and delegated-user flows remain deferred.
2. Incoming application credentials are opaque, expiring and revocable; store only a verifier and safe metadata. Rotation preserves the stable principal. Distinct query/build/evaluate/deploy/feedback grants do not imply admin rights. Lost show-once secrets cannot be recovered by idempotency replay.
3. Fixed integration access is its own configured ceiling. A user ID, affinity key, MCP argument or claimed group never verifies a human or expands scope. Everyone using SupportBot's authority can reach its allowed knowledge. Future verified delegation intersects actor ceiling with subject rights, not unions.
4. Project/action checks precede document access. PostgreSQL owns groups and allowlists. Current policy protects historical content, citations, final context, evaluation evidence, receipts and feedback. Receipt checks include uncited sources. Apply checks before retrieval and at the documented final dispatch/disclosure points; acknowledge already-admitted network races.
5. Every Inframeld model call uses ModelGateway. Custom/private OpenAI-compatible endpoints remain OSS. Operator-approved origins, DNS/destination checks, TLS/custom CA and bounded capabilities protect egress. A per-query URL is not a connection, and “compatible” is not proof of embedding support.
6. Probe embedding and generation roles separately. Share a provider connection when appropriate so the user does not re-enter its credential. Freeze semantic connection/model references in profiles/versions. Credential-only rotation preserves semantics; changed endpoint/model meaning does not. Under ADR-0020's accepted storage design, key replacement/removal invalidates its previous role-probe status. Changing endpoint origin requires a new connection and explicit credential provision; never forward the saved key automatically.
7. Persistent application-entered provider keys are required. Saved plaintext never returns to Studio or enters domain snapshots, jobs, logs, evaluator evidence, receipts or parser sandboxes. Only scoped credential operations create/replace/remove it; outward responses contain safe metadata.
8. The ADR-0020 PostgreSQL adapter using PyNaCl `Aead` and a separately supplied root key is accepted. Preserve its fail-closed behavior, authenticated resource binding and narrow plaintext-resolution boundary. Mounted files can supply bootstrap/root keys but do not replace the required runtime credential API. Do not add OpenBao or invent cryptography by default.
9. Missing credentials, root keys or required capabilities make affected calls unavailable; no silent default provider/key/model is selected. Central retry policy forbids hiding an ambiguous chargeable call in a vendor SDK retry.

## Accepted defaults and publication authority

The first useful answer without manual organizations/projects/groups is required. The accepted solution uses one provisioned organization, a securely claimed initial administrator and creator-private starter project/group, with ordinary ID-bound resources. Administrator status alone does not grant source reading. Other users and integrations receive access explicitly. Nonempty default allowlists apply on admission; changing a default does not retroactively make all documents public. Read ADR-0019 for the precise access boundary. The default starts automatic; new deployments default manual with an explicit automatic creation choice. Automatic update admission needs source/configuration plus build/deploy rights for each specified target; queued work rechecks current authority. Mode alone never elevates upload-only or query-only access. Switching to manual invalidates pending publication; enabling automatic authorizes fresh selected inputs. Ordinary builds still have no release authority. The shared default-route shape does not alter these rules.

## Task examples and checks

Trace an engineer saving one provider connection for separate model roles, then an application querying with its different incoming credential. Identify where each secret is verified/decrypted and which component can see plaintext. Review credential replacement, missing-key behavior and safe replay without printing secret values. For access, compare a human, fixed integration and forged subject; include revocation between retrieval and disclosure. Recommend focused checks, not a new federation, secrets-administration or governance platform.
