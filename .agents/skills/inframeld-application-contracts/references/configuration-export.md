# Export one coherent configuration

Alice exports Support to recreate it elsewhere. The export captures a consistent permitted definition set. It carries no provider secrets, document contents, vectors, release history or live Deployment state.

<a id="export-scope"></a>

## Export Scope

Each resource uses one TOML file with `schema_version`, `kind`, `metadata.name`, `metadata.display_name` and the supported resource-specific `spec`. A minimal collection can omit unnecessary `spec`. Names resolve references within their resource type and project. Stored relationships use permanent destination IDs. Display names never resolve identity.

| Resource | Exported meaning | Not transferred |
| --- | --- | --- |
| Project | Supported non-secret settings and policies | Identity authority, grants, memberships or operator locks |
| Model connection | One current provider/access definition and authentication requirements | Keys, historical executable access variants or model selections belonging to consumers |
| Processing profile | Explicit immutable parser/chunker/tokenizer settings and supported implementation identities | Parsed documents or runtime caches |
| Embedding profile | Connection/model, expected dimensions, normalization, distance and relevant document/query input behavior | Vectors or proof that a provider alias will never change |
| Collection | Name/display name and supported definition fields | Document membership, profiles or data |
| Source | Supported read-only S3 location, collection reference and audience requirements | Credentials, checkpoints, data or imported upstream ACLs |
| Pipeline | Complete saved working settings, inline prompt and typed-name dependencies | Deployments, templates, built versions, jobs or execution history |
| Evaluation | Supported non-secret evaluator/generation settings | Dataset content unless explicitly requested through the separate protected transfer |

Working Pipeline settings are the default export source. The user may instead explicitly extract settings from a Deployment's current version or a selected retained version. The result is still an ordinary Pipeline definition, not an exported Deployment.

The earlier proposal to transfer broader live-configuration state was superseded by this configuration-only scope. Optional evaluation dataset transfer was added separately. It does not restore Deployment export.

Complete exports expand effective settings, including explicit disabled reranking and selected supported defaults. Preserve prompt text exactly. Unsupported settings cannot be silently omitted. Concise authored definitions may omit only fields with specified versioned defaults. Exact omission rules remain schema work.

For example, export Alice's reviewed 32,768-token context, not a catalogue's newer suggestion of 131,072. Bob's newer catalogue must not replace that explicit value on import. The [metadata rules](model-validation.md#model-metadata) also preserve supported tokenizer, model and profile meaning, including settings explicitly left unset.

Recording where a setting came from explains it. It does not transfer validation status, approve a destination or guarantee model behavior. The model and portability contracts must define its portable representation and how equivalent settings are compared. This adds neither a model registry nor an unrestricted bag of provider options.

Offline validation checks definitions without fetching catalogues, tokenizers or provider metadata. If the destination cannot honor a setting, report the incompatibility. Do not substitute a default or run a hidden probe.

<a id="one-coherent-capture"></a>

## One Coherent Capture

1. Resolve the requested project/source and complete supported inventory.
2. Capture a coherent set of resource revisions, including current connection definitions and exact immutable profiles.
3. Check current authority over the complete requested export. Fail rather than produce a misleading partial project or reveal hidden inventory.
4. Serialize non-secret definitions and requirements. Dataset inclusion is explicit, not automatic.
5. For existing local output, review owned additions/replacements/removals and recheck local state before writing. Preserve unrelated files. Do not silently overwrite newer edits or mutate Git.

Configuration directories may be reused where environments are identical. Use separate complete directories when environments intentionally differ. Directory names never select target/account/project. V1 has no overlays, inheritance, executable templates or implicit `.env` loading.

<a id="complete-configuration-directories"></a>

## Complete configuration directories

A project configuration is a directory of complete resource definitions. Pipeline dependencies use plain names in resource-typed fields, while admitted operations bind resolved permanent destination IDs. Prompt text stays inside the Pipeline definition. Collection definitions describe configuration independently of their current document contents.

Offline validation precedes destination-aware review. An export explicitly selects working or Deployment-selected configuration and either captures the complete permitted configuration coherently or fails. Replacing an existing local export requires an explicit review of that local change. Use complete directories for deliberate environment differences, rather than treating missing definitions as deletion or hidden patch instructions. A reviewed file update replaces complete Pipeline working settings through the ordinary revision and authorization checks. It does not publish.
