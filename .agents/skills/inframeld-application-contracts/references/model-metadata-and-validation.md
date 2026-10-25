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

Consumers still own their model settings. Connections own current access and a separately protected credential slot. No metadata revision permits historical connection execution. A refresh proposes a diff, never overwrites saved settings or historical accounting. New processing/embedding meaning creates a new immutable profile. Later output cannot rewrite expected dimensions. Private aliases remain scoped to the selected connection/model, not globally equated by spelling. Portable definitions retain effective supported configuration without credentials or validation history. [The model guide](model-validation.md#model-metadata) owns resolution/failure rules. Must specify exact ownership, representation and equivalence before implementation.

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

## Choose a focused reading task

- For optional probes and actual validation evidence, read [Model validation](model-validation.md).
