# PD-CONTRACTS-04: Bind import review and partial recovery to exact actions

**Status:** ACCEPTED on 2026-10-29 in [ADR-0116](../../../../docs/adr/ADR-0116-apply-bounded-reviewed-import-plans-through-stable-child-operations.md). Implementation and qualification remain separate delivery work.

**Owner:** `inframeld-application-contracts`

The developer explicitly approved the presented batch-4 contracts and delegated selection of all remaining decisions to the assistant on 2026-10-29, requesting repository/GitHub recording and plain-language justification. This resolution is accepted under that authority. It selects logical policy, not implemented code or passing qualification.

## Contents

- [Approved resolution](#approved-resolution)
- [Why and example](#why-and-example)
- [Implementation and required evidence](#implementation-and-required-evidence)
- [Architectural impact and dependencies](#architectural-impact-and-dependencies)
- [Historical context and alternatives](#historical-context-and-alternatives)
- [Sources and finalization](#sources-and-finalization)

<a id="non-binding-recommendation"></a>

## Approved resolution

Use a durable bounded reviewed action plan. Its identity binds the installation/target/account/Project, supported canonical definitions and content digest, typed-name-to-destination-ID mappings, exact create/reuse/update choices, preserve/apply policy choices, effective defaults/schema version, live-impact acknowledgments, relevant expected owner revisions and stable parent/child request identities. Persist original supported non-secret input before resource effects. Initial bounds are 1000 resource files,1 MiB per file,10 MiB total decoded input and a 2000-action plan. Reject cycles, duplicate typed names, unknown fields/kinds/versions and unsupported semantics before admission. No executable templates, overlays, environment interpolation or provider/asset download occurs during offline validation.

Use the existing TOML schema_version/kind/metadata/spec structure with schema_version 1 for the initial format. Complete export materializes effective supported values and explicit disabled/provider-controlled states. Omission is allowed only for schema-versioned defaults: display name defaults to name, omitted collection spec is empty, and omitted import policy action means preserve. Missing required Pipeline/model/profile settings is an error, not a catalogue lookup. Typed local references are names within their known resource kind and Project. Explicit portable supported metadata/provenance is advisory or effective according to its typed role; runtime validation, actual usage, IDs, secrets/grants, documents/vectors and Deployment/job state are never transferred.

Semantic equivalence compares canonical complete supported effective definitions after typed destination-reference resolution. Ignore display labels and provenance timestamps as proof of execution meaning, but preserve them as metadata. Preserve exact prompt text, explicit unset/provider-controlled versus explicit values, model/profile identities, connection origin/base path/authentication requirements, dimensions, normalization, metric and document/query input behavior. Same name or matching dimensions alone is not equivalence. A changed immutable profile requires an explicit distinct profile, never mutation. Missing required dependency has an explicit authorized create or makes the plan ineligible.

Before any resource mutation, validate all known choices, authority and relevant destination revisions. Ineligible application creation, human-only policy apply, hidden dependency/conflict or unacknowledged live connection impact rejects the known-invalid plan before resource effects. Preserve destination spending/tracing/retention by default; explicit apply invokes each ordinary human-authorized policy operation. Import permission cannot supply those rights. New collections are empty, source definitions do not sync and no build/model/publication/provisioning outside the supported resources runs implicitly.

Execute dependency-ordered stable child operations through normal owners. Each rechecks current authority, expected state and compatibility at commit. Reuse reads also recheck their relevant semantic/reference state before dependent children. There is no global Project transaction, blanket Project revision or generic provisioning engine. A concurrent change after initial review may leave earlier children committed and later actions stopped. Report actual applied/reused/failed/uncertain/not-started outcomes; never claim whole-import rollback or prune omitted resources.

Recover original child outcomes before retry. A changed file, destination mapping or expected revision does not replace an admitted plan. A new reviewed plan may reference already completed resources and re-review unfinished changed actions, without re-executing completed effects. An inaccessible completed child is not treated as missing or recreated; expose only permitted safe status and stop dependent work that cannot be authorized. Partial results and comparisons obey current owner/source disclosure. Local export replacement uses its separate reviewed owned-file set and never mutates Git or unrelated files.

## Why and example

Import should apply exactly the configuration Bob reviewed and tell him which changes actually happened if a later step fails.

An import creates two resources, then its Pipeline update conflicts with Alice's newer revision. Keep the two resources and stop the stale update. A new review can use those resources without creating duplicates.

The plan needs explicit identities and per-owner outcomes. It avoids an elaborate provisioning engine and the false promise that a multi-step import is globally atomic.

<a id="decision-trigger-and-stopping-boundary"></a>

## Apply the accepted contract

Use this contract when the original trigger matches. Do not ask for the same policy decision again. Concrete native methods, DTO names and physical schemas are implementation choices consistent with this contract and the repository conventions. Missing measurements, fixtures or assembled evidence block the affected qualification/support claim, not authorized implementation or isolated tests. A failed test is not permission to weaken an accepted safety boundary.

<a id="open-questions-and-required-evidence"></a>

## Implementation and required evidence

Offline rejection, canonical round trips/equivalence, changed files, human/application eligibility, default preserve/explicit policy apply, dependency ordering, partial and uncertain children, hidden completed resources and concurrent owner edits.

These are required checks, not tests run or successful production evidence. No application edits, paid calls or production changes follow merely from recording this decision.

## Architectural impact and dependencies

Shared CLI/import orchestration, all imported resource owners, budget/trace policy and configuration schemas. Update review-to-partial-recovery sequences without copying owner persistence into import.

Load neighboring decisions only under these conditions:

- [PD-CONTRACTS-02 (accepted): Coordinate budget policy, reservations and uncertain settlement](decision-spending-coordination.md). Only for explicit budget apply.
- [PD-PIPELINES-02 (accepted): Make a confirmed trace opt-out stop later capture and delivery](../../inframeld-pipelines/references/decision-trace-policy-fencing.md). Only for trace-policy apply.
- [PD-ACCESS-02 (accepted): Keep durable work and credential lifetime explicit](../../inframeld-access-models/references/decision-admitted-work-authority.md). When queued import continuation needs credential-lifetime semantics.

## Historical context and alternatives

The following preserves the earlier problem, context and options. Statements that a choice was open describe that earlier analysis. The approved resolution above now settles it.

<a id="problem-and-example"></a>

### Original problem and example

Historical analysis before this resolution.

Bob reviews an import that creates two resources and updates Pipeline revision 17. Alice saves revision 18 before the update executes. The creates may already have completed. Recovery must preserve them and require fresh review of the changed update, rather than overwriting 18 or reporting the entire import had no effects.

The preserve/apply rules and partial-outcome behavior are accepted. Exact equivalence checks, relevant destination revisions, parent/child identities, precondition ordering and recovery schemas remain open. Names or a generic confirmation cannot establish resource equivalence or authority.

### Original accepted context and evidence

Historical context before this resolution. Unchanged invariants still apply.

Import invokes owning operations in dependency order, preserves completed effects and never prunes omitted resources. New collections are empty, sources do not sync and no model/build/publication starts implicitly. Credentials remain separate, and protected policies retain human-only authority.

Bind the actual definitions and reviewed mappings, not merely a laptop path. Recheck relevant current state before effects and at each owner’s boundary. There is no global project transaction or blanket project revision. Shared connection changes can affect live connectivity even without publication.

### Considered alternatives and trade-offs

Historical options, resolved by the approved contract above.

1. **Persist a reviewed action plan with stable child operations.** Store bounded supported definitions/mappings and original child identities so interruptions recover exact actions. This makes partial progress clear, but needs explicit plan limits and per-owner outcomes.
2. **Reconstruct pending actions from the original durable input and recorded outcomes.** Recompute only through stable equivalence/precondition rules, retaining completed identities. This can reduce stored derived plan data, but is harder to prove safe when destination state changes.

## Sources and finalization

- [Durable import and recovery](configuration-import-recovery.md#import-recovery).
- [Original import identity](configuration-import-recovery.md#import-recovery).
- [Context and target contracts](http-mcp-and-generated-clients.md).

Follow [decision finalization](../../../../docs/development/guides/architecture-decisions.md#just-in-time-architecture-decisions) for a later change to this accepted policy. Qualification evidence must identify its artifacts, environment, failures and limits. This record does not fabricate implementation or a passing test.
