# CLI context, portability and recovery

<a id="cli-context-portability-and-recovery"></a>

Alice has a local installation and a remote Support project. A retry or imported configuration must not silently choose whichever target happens to be current now. The CLI guides selection and presents outcomes, while backend owners enforce the operation.

<a id="resolve-context-deliberately"></a>

## Resolve context deliberately

Use the selected one-server-URL discovery and target/account/project contract. Project Name and ID form one precedence choice, not independently merged inputs. Explicit selection overrides both environment forms. Display names are labels, never resource selectors. Stored bindings use permanent IDs.

Admitted work retains original installation/account/project identity. Resolve original retry context before current aliases or changed settings. A missing/inaccessible original target does not authorize substitution.

For example, Alice admits a query against Support, then rebinds her default alias to Sales. A retry finds the original logical-route idempotency record before resolving a new target. It must not create another paid query against Sales. Exact selector internals remain implementation recommendations rather than a delivered API.

Bounded lists return one page unless traversal is explicit. Dry-run permits only its documented metadata inspection and must not perform the requested mutation or hidden model work.

<a id="import-definitions-and-protected-data"></a>

## Import definitions and protected data

Complete supported configuration uses TOML. Protected question/reference/expectation transfer uses explicit versioned JSONL. Credentials and runtime backups are separate. Configuration alone does not transfer knowledge bytes, vectors, Deployments, release versions or data access.

1. Resolve destination identities, audience mappings and backend-bound credentials. Matching names do not authorize overwrite or reuse of permissions.
2. Review current state and the exact requested effects. Reject a known stale review before resource mutations, retaining each owner's later current checks.
3. Execute ordinary owner operations. Partial successful work remains saved. There is no global transaction, automatic cross-resource rollback or hidden execution.
4. Reconcile original operations and distinguish reused, unapplied and unknown effects. Unchanged eligible work may resume under current checks.
5. Changed inputs/state require fresh review rather than rewriting the old job. Preserve uncertain paid dispatch and show-once credential boundaries.

Budget policy, trace policy, case audiences and connection changes keep their specific authority. Preserve can be a valid choice. A known-ineligible explicit apply is denied, not skipped silently or executed as a saved human. Imported metadata is not permission.

<a id="present-useful-outcomes"></a>

## Present useful outcomes

Ordinary automated JSON is one final object. Successful admission or inspection is not completed job success. Missing output or a nonzero exit cannot authorize new work. Noninteractive mode needs explicit required inputs and must not invoke prompts, editors, browser login or blanket approval for later paid effects.

Show plain-language progress with actual counts, saved results and bounded protected details. Keep human and JSON meaning aligned. Distinguish a lost CLI connection, unconfirmed cancellation and an unknown paid outcome. Mock fields and closed UX workshops do not publish schemas or prove runtime behavior.

Structured change review uses red struck-through old values and green new values together with explicit labels. Use Current / Proposed for intent, Before / Now for confirmed changes and Reviewed / Now when checked state changed since review. Preserve neutral unchanged facts and plain/JSON fallbacks.

A colored proposal does not prove commit. A saved-revision delta does not alter an admitted build, and ready output is not a live-version delta. Never expose secrets or create a diff/tracking backend merely for presentation.

<a id="recovery-is-scoped-to-original-work"></a>

## Recovery is scoped to original work

Retry job status and safe resume through existing bounded outcomes. Project deletion resumes only the admitted scope and exposes content-free status under its contract. Identity cleanup preserves original obligations, trusted evidence and independent blocks. Neither adds another job state machine or an authorization bypass.

All commands remain scriptable with descriptive dry-run behavior, while exact wire/output/recovery representations remain specification work where identified. Do not present an accepted user journey as a delivered provisioning API.

- [CLI context](cli-targets-and-accounts.md#cli-context), [configuration portability](configuration-export-and-import.md), [jobs and recovery](jobs-and-recovery.md), [shared change presentation](cli-change-review.md#cli-change-presentation) and [Pipeline change review](cli-change-review.md#change-review).
- [V1 scope](../../inframeld-architecture/references/v1-scope-and-extension-boundaries.md), [resource names](../../inframeld-architecture/references/resource-names-and-identity.md#resource-naming), [Evaluation transfer](../../inframeld-evaluation/references/history-and-dataset-transfer.md#dataset-portability), [Access automation](../../inframeld-access-models/references/actions-and-initial-grants.md#cli-automation-authority) and [Access contracts](../../inframeld-access-models/references/actions-and-initial-grants.md).

<a id="pending-decisions-for-dependent-implementation"></a>

## Pending decisions for dependent implementation

Before choosing an unresolved implementation contract, load only the entry whose trigger applies:

- [PD-CONTRACTS-04: Bind import review and partial recovery to exact actions](decision-import-review-and-recovery.md). Before implementing import planning/equivalence, admission ordering, child operations or interrupted-import recovery.
- [PD-CONTRACTS-03: Matching qualified CLI/runtime releases](decision-cli-server-compatibility.md) is accepted through ADR-0095. Offline metadata does not verify remote compatibility. Runtime enforcement and release-pair qualification remain separate work.
- [PD-ACCESS-02: Keep durable work and credential lifetime explicit](../../inframeld-access-models/references/decision-admitted-work-authority.md). Before admitting, executing or resuming durable work that must interpret credential expiry, rotation, revocation or replacement.
