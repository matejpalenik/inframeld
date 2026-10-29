# Separate model suggestions, saved settings and evidence

<a id="separate-model-suggestions-saved-settings-and-evidence"></a>

A catalogue suggests a large context window, but Alice’s gateway supports a smaller one. The application saves her reviewed setting. A suggestion, a saved key and a successful real call establish different facts.

> **Status:** accepted behavior is stated separately from proposed representations and qualification work. Existing Python types, generated OpenAPI and migrations own implemented shapes. Pending decisions are not accepted by this reference.

<a id="model-metadata-provenance"></a>

<a id="record-suggestions-separately-from-configuration-and-evidence"></a>

### Record suggestions separately from configuration and evidence

A catalogue may suggest a 131,072-token context while Alice deliberately saves 32,768 for her gateway. Preserve her supported value and where the suggestion came from. The catalogue must not override saved settings at runtime. The following are logical distinctions, not new tables or published fields:

| Information | Meaning |
| --- | --- |
| Suggested value and provenance | Exact provider/model/role context, source identity and snapshot/version or observation time. Unknown and conflicting values remain identifiable. |
| Reviewed effective configuration | Explicit saved values and supported unset/provider-controlled distinctions, with the ordinary owning resource revision. An explicit override is a declaration, not test evidence. |
| Runtime observation | Actual model/access/credential attribution, usage, returned dimensions and validated outcome. Callers cannot edit it to claim success. |

Consumers still own their model settings. Connections own current access and a separately protected credential slot. No metadata revision permits historical connection execution. A refresh proposes a diff, never overwrites saved settings or historical accounting. New processing/embedding meaning creates a new immutable profile. Later output cannot rewrite expected dimensions. Private aliases remain scoped to the selected connection/model, not globally equated by spelling. Portable definitions retain effective supported configuration without credentials or validation history. [The model guide](model-validation.md#model-metadata) owns resolution/failure rules. The accepted metadata/reference contract above selects ownership and equivalence. Native DTO and storage names remain implementation work.

An endpoint's **origin** is its scheme, hostname, and port. Its base path identifies the API path beneath that origin.

| Change | Required behavior |
| --- | --- |
| **Rotate a credential without changing model semantics** | Preserve connection and pipeline lineage. The replacement credential does not inherit the old role-validation status. |
| **Change embedding semantics** | Create a new embedding profile and materialization rather than change the meaning of existing vectors. A materialization is the prepared searchable index for the selected inputs and profiles. |
| **Change the chat model, prompt, or retrieval configuration** | Saving creates a working-configuration revision. Temporary per-request overrides create only execution provenance. An explicit successful Build creates a release-ready PipelineVersion. Existing versions remain unchanged. |
| **Change shared access settings** | Review all affected consumers and apply current authority, revision, destination and embedding-compatibility checks. Live impact requires explicit acknowledgment. Pipeline versions keep their connection IDs and use its current settings. |
| **Change the endpoint origin** | A guarded in-place update requires explicit credential provision for the new destination, or an allowed credential-free transition that clears the old slot. Commit together. Never forward the old key implicitly. Another connection remains the isolated-migration alternative. |
| **Shared update conflicts with prepared/in-progress embedding data, or compatibility is unknown** | Reject before changing configuration or credentials. Use another appropriate connection/profile and ordinary preparation. No force acknowledgment or automatic re-embedding. |

Embedding profiles record expected model identity or alias, connection ID, dimensions, normalization, and distance metric. Numerical execution provenance records actual access revisions. See their [record definition](../../inframeld-indexing/references/records.md#profiles-describe-behavior-not-just-names).

## Accepted metadata and reference contract

The developer explicitly approved the presented batch-4 contracts and delegated selection of all remaining decisions to the assistant on 2026-10-29, requesting repository/GitHub recording and plain-language justification. This resolution is accepted under that authority. It selects logical policy, not implemented code or passing qualification.

Use application-owned typed Known, Unknown and Conflict observations per supported model property. Keep three records distinct: advisory suggestions with exact provider/connection/model/role and source/version/time; reviewed effective settings owned by the Pipeline/profile/evaluator revision; and non-editable actual call observations. An explicit supported reviewed value wins over suggestions. Qualified selected-server observations may prefill ahead of pinned catalogue suggestions, but refresh only proposes a diff. No refresh rewrites saved settings, historical accounting or an existing profile.

The supported property set covers model/role identity, effective context/output constraints and qualified token-count strategy, role-specific input behavior, embedding dimensions/normalization/distance, supported generation parameters such as explicit versus unset temperature, structured-response capability where required, and pricing categories/provenance. Keep display-only descriptive metadata optional. Required dispatch input/output bounds and required embedding/profile meaning must be established by supported explicit configuration or qualified evidence; Unknown there blocks the dependent action. Optional discovery can remain Unknown. Unknown pricing blocks capped work under the accepted spending rule, but does not forbid otherwise supported explicitly uncapped work. A user-entered zero rate is not evidence of free execution. A generic tokenizer guess is not a proven safety bound.

Metadata reads are bounded selected-connection/model gateway operations using current destination and credential rules. No universal discovery endpoint, direct CLI provider call, implicit inference probe or arbitrary provider dictionary is introduced. Keep private aliases scoped to their connection. Successful real-use validation is bound to role, selected model, effective settings fingerprint, actual access/credential revisions and qualified adapter version. Credential replacement does not inherit old validation. Runtime output/usage validates observations; it cannot edit expected dimensions or settings to fit a mismatch. Native request/result names remain implementation-owned, not another schema manual.

Connection review/update/reference admission/deletion share a short SQL connection-liveness/dependency coordination gate with current authority and expected access/credential state. Every new executable or retained configuration reference, profile, PipelineVersion, evaluator and admitted work reference participates. Backend impact/embedding checks inspect all such dependencies regardless of the manager's visibility. Return paginated permitted details, without hidden resource names/counts or a falsely complete filtered impact list. Bind live-impact acknowledgment to exact proposal, identity/revision and relevant dependency state. A changed meaningful dependency invalidates review. Keep provider waits outside the transaction.

Retain the existing compatibility veto: shared access changes with incompatible or unproven prepared/in-progress embedding meaning fail atomically before settings or credentials change. Same alias/dimensions/probe success is insufficient. Origin/authentication-context changes require explicit protected credential provision for the destination or an allowed credential-free atomic clearing. A no-op changes no access revision. Credential-only replacement and metadata rename retain their separate meanings. Canonical import equivalence uses complete effective supported settings and typed destination references, preserving exact prompt and explicit unset distinctions.

Delete only a currently authorized same-Project live connection with no executable/current/retained dependency or active-use reference, checked in the same gate as retirement. Require an empty credential slot; deliberate protected removal is its existing separately authorized operation. Deletion does not revoke a provider key and cannot cascade into consumers. Atomically save a permanent non-content retired identity, safe original outcome and audit. Never reuse the ID or let a delayed reference admission revive it. Minimal historical call/audit/accounting attribution may retain a non-executable identity without becoming a permanent live configuration reference. Replays recover the original deletion under current disclosure; unknown or hidden dependencies produce a safe refusal rather than guessed unused status.

[ADR-0123](../../../../docs/adr/ADR-0123-keep-model-metadata-explicit-and-delete-only-unreferenced-connections.md) records rationale. Known/Unknown/Conflict handling, private aliases, explicit overrides, metadata refresh, required unknown bounds, credential-rotation validation, compatible/incompatible connection changes, concurrent new references/deletion, retained versions, hidden impact and lost-response replay. These are requirements, not passing tests.

## Choose a focused reading task

- For optional probes and actual validation evidence, read [Model validation](model-validation.md).
