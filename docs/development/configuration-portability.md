# Recreating Configuration Across Installations

Alice configures a project, exports its definitions to Git and sends the repository to Bob. Bob can recreate the supported resource configuration in his installation. He still supplies credentials, loads documents, prepares indexes and explicitly evaluates or builds. **Configuration portability is not a backup or a deployment.**

This guide explains what can be transferred, how Bob reviews destination changes and what happens if import stops partway through. Model metadata remains explicitly reviewed. Changing project budgets, tracing or retention remains restricted to authorized humans, even during import.

**Status:** this is accepted behavior, not an implemented importer. Exact versioned TOML/JSONL schemas, application contracts and permission mappings remain specification work in [the delivery plan](cli-delivery-plan.md).

## Contents

| Reader's question | Start here |
| --- | --- |
| What travels in configuration? | [Export scope](#export-scope) |
| Can the export mix incompatible revisions? | [Coherent capture](#one-coherent-capture) |
| What happens to existing destination settings? | [Destination review](#destination-review) |
| How does Bob supply his own keys? | [Separate credentials](#credentials-stay-separate) |
| What if the destination changes or import stops halfway? | [Import and recovery example](#import-recovery) |
| Can test questions travel too? | [Evaluation datasets](#evaluation-datasets) |

## Export Scope

Each resource uses one TOML file with `schema_version`, `kind`, `metadata.name`, `metadata.display_name` and the supported resource-specific `spec`. A minimal collection can omit unnecessary `spec`. Names resolve references within their resource type and project; stored relationships use permanent destination IDs. Display names never resolve identity.

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

Complete exports expand effective settings, including explicit disabled reranking and selected supported defaults. Preserve prompt text exactly. Unsupported settings cannot be silently omitted. Concise authored definitions may omit only fields with specified versioned defaults; exact omission rules remain schema work.

For example, export Alice's reviewed 32,768-token context, not a catalogue's newer suggestion of 131,072. Bob's newer catalogue must not replace that explicit value on import. The [metadata rules](model-connections.md#model-metadata) also preserve supported tokenizer, model and profile meaning, including settings explicitly left unset.

Recording where a setting came from explains it. It does not transfer validation status, approve a destination or guarantee model behavior. The [model](https://github.com/matejpalenik/inframeld/issues/121) and [portability](https://github.com/matejpalenik/inframeld/issues/151) contracts must define its portable representation and how equivalent settings are compared. This adds neither a model registry nor an unrestricted bag of provider options.

Offline validation checks definitions without fetching catalogues, tokenizers or provider metadata. If the destination cannot honor a setting, report the incompatibility. Do not substitute a default or run a hidden probe.

## One Coherent Capture

1. Resolve the requested project/source and complete supported inventory.
2. Capture a coherent set of resource revisions, including current connection definitions and exact immutable profiles.
3. Check current authority over the complete requested export. Fail rather than produce a misleading partial project or reveal hidden inventory.
4. Serialize non-secret definitions and requirements. Dataset inclusion is explicit, not automatic.
5. For existing local output, review owned additions/replacements/removals and recheck local state before writing. Preserve unrelated files; do not silently overwrite newer edits or mutate Git.

Configuration directories may be reused where environments are identical. Use separate complete directories when environments intentionally differ. Directory names never select target/account/project. V1 has no overlays, inheritance, executable templates or implicit `.env` loading.

## Destination Review

V1 creation of configurable resources is human-only. An application may review/import eligible changes to existing resources and explicitly reuse compatible definitions. A missing dependency or changed immutable profile requiring creation makes its plan ineligible: reject the known-invalid plan before mutations and report the resource an authorized human must provision. A subsequent import uses a new reviewed plan against those destination IDs. Neither a Create grant record nor a saved human login makes application creation eligible. [The provisioning contract](access-contracts.md#provisioning) owns this boundary; ordinary operational output such as versions and cases remains supported.

For Bob, `legal-research` names a candidate project in his selected installation, not Alice's UUID. He selects an existing destination or separately creates one. The importer validates local files offline first; destination-aware dry-run is a distinct read-only review.

- Resolve dependencies by project/type name, then retain permanent IDs. A matching name proves neither semantic equivalence nor authority.
- For a human import, propose creation for missing resources; application imports require those resources to exist. Propose explicit reuse for matching configuration. Different configuration is a conflict until deliberately resolved through a supported guarded update or corrected input.
- Changed immutable processing/embedding meaning requires a distinct named profile. Do not mutate an existing profile to satisfy an import.
- Review each source audience requirement against permitted destination groups, even when names match. Group creation is separate; save destination IDs. Import neither copies memberships/grants nor changes existing document audiences.
- Preserve destination project budget/tracing policies unless a separately authorized reviewed update explicitly changes them. Imported settings cannot override operator restrictions.
- Shared connection updates retain live-impact review, current revision/dependency checks, credential binding and the embedding-compatibility veto. Import is not a privileged shortcut.

**Example: importing with an application key.** Git contains a USD 100 project limit; SupportBot's destination has a USD 20 limit. With current access to the necessary definitions and otherwise authorized resource operations, the default preserve choice keeps USD 20 and reports the intentional difference. It does not invoke budget mutation. If SupportBot explicitly requests applying USD 100, the plan is ineligible: only an explicitly authorized human may set, raise, lower or remove the project limit in v1.

Reject that known-invalid plan before its resource mutations; do not silently omit the requested change or switch to a saved human account. The user may separately choose a new plan that preserves the budget, or have an authorized human perform a separately reviewed change.

This rule also covers first setting a limit, lowering it and applying explicit no-limit. A file, import grant or confirmation cannot make an application eligible. Permission to inspect protected policy information remains separate. [Budget management](model-connections.md#budget-policy-authority) owns mutation and accounting. Authority can still be revoked after review: ordinary owners recheck at commit, preserve completed import steps and report partial outcomes without replaying a policy over newer state.

**The same preserve/apply distinction applies to tracing and retention.** Suppose Git requests tracing on for 30 days but the destination uses off for 7 days. These are illustrative settings, not new defaults. SupportBot may import otherwise authorized resources while preserving off/7 days; report the intentional difference only within its disclosure authority. It cannot apply on/30 days, disable capture or change retention even if it can inspect pipeline traces.

Reject that known-ineligible explicit plan before mutations. Only an active human with current project trace-policy authority may approve apply through #149, under operator constraints and reviewed state. Do not change identity or silently substitute preserve.

Reducing retention must disclose possible expiry of existing history. It uses the ordinary retention operation, not an import-owned cleanup mechanism. Import never transfers or explicitly deletes trace history. The separate human-only delete-history action requires separate deletion authority; it is not implied by policy apply or inspection. Automatic expiry and source erasure continue through ordinary backend workflows. [Observability](observability.md#trace-authority) specifies this boundary; #151/#154/#184 must expose it and #155/#187 must qualify preservation, denial and partial recovery.

## Credentials Stay Separate

TOML contains authentication requirements, never credential values, encrypted secrets or references that automatically discover arbitrary secrets. After configuration import, Bob sees which connections/sources require credentials and can reuse the same protected screens as ordinary model/source setup. Existing credentials remain unchanged unless explicitly replaced.

Human input uses hidden entry; automation uses protected files or stdin, not argv or environment secrets. Human-only provider-credential/grant administration remains human-only even when a surrounding import is scriptable. Sources use explicit backend-configured identity or source-specific credentials; never laptop ambient credentials, a human login token or another resource's key. Saving configuration or credentials performs no synthetic test or sync implicitly.

For a model connection, an exported API-key authentication requirement is not the key itself. Bob separately supplies the raw provider key; the backend adapter later constructs the known provider header. Inframeld login/application credentials cannot fill that slot. A supported metadata read uses the same destination-bound credential checks, not the exporting installation's key or a direct CLI request. Missing keys leave configuration saved but not usable for required authenticated calls; import never claims successful authentication. Origin/auth-method changes cannot preserve a key implicitly. [Provider authentication](model-connections.md#provider-authentication) owns these rules.

## Durable Import

1. Bind the reviewed definitions, mappings, current authority and expected destination revisions to the original operation.
2. Invoke existing domain-owned operations in dependency order. This is orchestration inside the existing backend, not a new domain, generic provisioning engine or global transaction across external work.
3. Persist each resource result. Already completed resources remain after interruption; omitted resources are never pruned.
4. Recover original admission/job before repetition. Continue eligible unfinished work under current checks. Changed inputs or relevant state need fresh review; reconcile uncertain writes before retrying.
5. Report configuration, credentials, data, preparation, evaluation and publication as separate outcomes. Finish is the default. Optional continuation reuses ordinary screens and separately authorized operations.

New collections are empty. Imported sources do not synchronize. No documents, model calls, embeddings, builds or release transitions occur merely because import succeeded.

<a id="import-recovery"></a>

## Follow One Import Through Success and Interruption

Bob reviews six resource actions for `legal-research`: create two collections, reuse three matching dependencies and update the saved `contracts` Pipeline. The matching dependencies retain their IDs and credentials. The Pipeline update changes working configuration only. The [reviewed import and recovery ticket](https://github.com/matejpalenik/inframeld/issues/154) makes three existing rules concrete; it does not introduce another import engine or a transaction spanning the whole project.

### First bind the reviewed input

Validate the complete selected input and resolve every known conflict before resource mutations. Bind the actual target/account/project, supported definition content, destination identities, create/reuse/update choices, policy choices, required acknowledgments and relevant expected revisions. A path on Bob's laptop is not a durable copy of those definitions. Missing credentials are separate unmet requirements, not permission to send a probe or borrow another identity's key.

Before beginning resource mutations, recheck the reviewed input, current authority and relevant destination state. A known change invalidating that review stops the import without resource mutations. This is not a promise that concurrent changes cannot happen a moment later: every owning operation still checks its relevant authority, revisions and dependencies at its ordinary boundary. No global project lock or all-or-nothing transaction is selected here. Unrelated destination activity does not by itself justify inventing a whole-project revision conflict; #151 specifies the relevant checks for each action.

### Case 1: the reviewed actions still apply

Invoke ordinary domain operations in dependency order. Create missing resources, reuse matching ones without manufacturing revisions, and apply only explicitly reviewed supported updates. A reused resource must remain suitable and accessible when remaining work needs it. A name is not proof of equivalence, and a previously successful reuse check is not permanent authority.

On confirmed completion, report **Created 2, Reused 3, Updated 1** for this fixture. Configuration is saved, but credentials, documents and indexes may still be missing. Finish remains the default. Import does not synchronize sources, test providers, evaluate, build, create a Deployment or publish. Shared-current connection updates, if separately selected, retain their normal live-impact guards; "no publication" is not "no possible effect on live connectivity."

### Case 2: the review is stale before resource changes

Bob reviewed Pipeline revision 17. Alice saves revision 18 before the import's pre-mutation checks. Report that the review changed and that **no resource changes were made by this import**, if confirmed. Show permitted reviewed/current values using the [shared delta presentation](api-contracts.md#cli-change-presentation), not a proposed update disguised as a completed one. Ask Bob to review the current destination and the intended incoming settings again. Do not accept revision 18 automatically, reinterpret a create as reuse or turn generic confirmation into overwrite authority.

Internal admission/recovery records may already exist; "no resource changes" does not mean that no request/job metadata was written. If an acknowledgment is lost, recover its outcome before making even this narrower claim. Exact admission/precondition ordering remains #151/#124 work.

### Case 3: the destination changes after some work completes

In a separate run, two creates and three reuses complete before a changed Pipeline revision blocks its update. The following is **mock, unimplemented presentation**, assuming current access permits the listed facts:

```text
Import incomplete

Created      2 resources
Reused       3 resources
Not applied  1 pipeline

The pipeline changed after your review.
Completed changes were kept.

Next: review the pipeline change before continuing.
```

"Not applied" here means the owner confirmed that the guarded Pipeline update did not commit. If the write outcome is unknown, show that uncertainty instead; neither success nor failure can be inferred from a timeout. Counts come from protected retained resource outcomes, with a bounded detail view naming the affected resources and reasons where access permits. Do not hide unattempted, failed or uncertain actions inside a success count. Reused resources are resolved outcomes, not writes performed by the import.

Keep confirmed completed effects. There is no automatic rollback, deletion of newly created resources, replay of completed updates or restoration over newer state. A changed review needs a fresh explicit reviewed import, which may deliberately reuse earlier completed resources after current comparison. The original operation retains its partial history; approval of changed definitions/state must not rewrite its meaning. Exact linkage between old and new work remains specification work, not a new plan-resource API.

### Recover the original operation before deciding what to do next

| Observed situation | Next allowed action |
| --- | --- |
| The CLI disconnected and original work may still be running | Look up the original admission/job, then inspect or watch. Do not submit a second import merely because the terminal lost contact. |
| Unfinished work is confirmed eligible under the unchanged reviewed input and current checks | Explicitly resume the same operation, skipping completed mutations. A historical success does not bypass current dependency/access checks. |
| Local TOML changed | The old job still means its retained original definitions. Using the new files requires new review/admission, not implicit file rereading on resume. |
| A required revision, identity, permission or live-impact review changed | Stop stale continuation. Preserve completed work and obtain a fresh valid review; never silently retarget or adopt newer state. |
| A child write's acknowledgment was lost | Reconcile the original child identity/result before repetition. A later edit must not be overwritten by replay of an earlier success. Unknown remains unknown until authoritative evidence resolves it. |
| Required retained input/history is unavailable | Explain the recovery limit. Do not infer that no effects occurred or reconstruct permission from local names/counts. Any new work needs explicit review. |

Current permissions govern both effects and disclosure, including resource names, counts and stored definitions. Dry-run describes the plan and unavailable checks without mutation/admission or becoming later approval. Scripts provide required choices, return structured conflicts/partial outcomes without prompts, and never switch to a saved human identity. Human progress uses stderr when stdout carries JSON. Ctrl-C requests cancellation without undoing committed resources; `c` detaches the watcher only. [Jobs](jobs-and-idempotency.md#import-recovery) owns these shared retry/cancellation boundaries.

#151 specifies exact reviewed-input/equivalence/revision contracts, #153 prepares destination review, #154 performs guarded durable application and #184 presents the same outcomes. #155/#187 must later verify stale-before-mutation, post-partial races, missing credentials, lost acknowledgments, changed files, duplicate resume, current access and zero hidden execution. #124/#156 retain shared recovery/output contracts. These are accepted requirements and future qualification scenarios, not implemented APIs or test results.

## Evaluation Datasets

Explicit dataset export includes actual questions, references and passage expectations in versioned Inframeld JSONL alongside TOML settings. Preserve complete selected membership, portable case identity, immutable content revisions and provenance. Do not export source corpus, vectors, runs or credentials. [Evaluation](evaluation.md#dataset-portability) owns these records and protection, not the configuration grouping.

New/changed imported cases start unreviewed and require an explicit destination audience immediately, including before source linking. Unchanged revisions may reuse existing review state. Conflicting local/incoming edits require a choice; older imports never silently roll back current content and omission never deletes cases. Existing protection survives reimport and editing.

Link only verified permitted source-version/artifact/coordinate evidence. Propose unique proven matches, ask about ambiguity and retain unresolved expectations honestly. Validate every passage even when reviewing one shared source mapping. Linking does not load documents, change acceptance or reduce the requested benchmark silently. Linked cases require both retained imported-audience access and current source access.

After linking and review, optional evaluation uses the exact intended case set through ordinary frozen admission. Finish remains default. Configuration import is not acceptance, readiness or permission to publish.

## Qualification Boundaries

Specification gates must settle exact schemas/defaults, semantic equivalence, coordinate proof, capability/target mapping, revision review and recovery output. Runtime gates must cover complete round trips, local overwrite races, concurrent destination edits, expired authority, uncertain writes, interrupted imports, retained local edits, hidden sources, erasure and every supported resource. Exported copies already downloaded cannot be recalled across installations.

See [CLI delivery](cli-delivery-plan.md), [resource identities](data-model.md#resource-naming), [model connections](model-connections.md#shared-current), [jobs](jobs-and-idempotency.md) and [Definition of Done](definition-of-done.md).
