# CLI-First Backlog Reconciliation Report

This report preserves the documentation and GitHub planning checks performed on the dates shown below. It does not certify implementation or runtime behavior. At the initial correction checkpoint, the delivery map covered 107 capabilities. Use the [delivery plan](cli-delivery-plan.md) for the maintained issue inventory and capability map.

Each pass records its own baseline and results. Earlier checks are historical evidence, not checks rerun during later editorial changes.

## Baseline and Authority

The real repository baseline is `b3bbfc438a6dbc390e4bd56210474bacaf177a49`. Existing uncommitted documentation was captured before editing and preserved as the starting point. The maintainer explicitly approved describing the accepted 2026-10-01 uncommitted architecture overlay in tickets instead of making a commit or pretending unpublished files exist at that SHA.

The GitHub baseline contained 100 issues, including 89 open and 11 closed, 14 epics and 156 native dependency edges. Pull requests were excluded. The existing v1 milestone is number 1; no duplicate milestone or release date was created.

## Delivery Changes

- [CLI epic #114](https://github.com/matejpalenik/inframeld/issues/114) owns the Rust client, common automation contract, context/authentication, local lifecycle, onboarding, domain workflows and three end-to-end qualification gates. Reused [#80](https://github.com/matejpalenik/inframeld/issues/80) owns generator-neutral client integration.
- [Configuration-portability epic #115](https://github.com/matejpalenik/inframeld/issues/115) groups shared schema/resolution/export/import work. Domain mutations stay with their existing owners; evaluation datasets stay with Evaluation.
- [#82](https://github.com/matejpalenik/inframeld/issues/82) is the required standalone Ory account UI under Access. It no longer depends on Studio integration.
- [#101](https://github.com/matejpalenik/inframeld/issues/101) qualifies the assembled CLI/account-UI release while preserving backend, MCP, upgrade, recovery and measured-capacity requirements.
- Exactly #12, #13, #81 and #83-#94 remain deferred Studio work outside v1. Their scope follows the same accepted CLI-led behavior.

[ADR-0055](../adr/ADR-0055-deliver-cli-first-v1-through-openapi-generated-clients.md) records the delivery direction and partially supersedes the external-tooling prerequisite in ADR-0006. The separate local-only reranking conflict was raised with the maintainer and explicitly resolved through [ADR-0056](../adr/ADR-0056-support-explicit-local-hosted-or-disabled-reranking.md): explicit local Ettin 32M, hosted gateway reranking or disabled reranking, retaining bounded execution and qualification obligations.

## Capability Splits

| Existing coordinator or owner | Focused work |
| --- | --- |
| [#61](https://github.com/matejpalenik/inframeld/issues/61), automatic updates | [#131](https://github.com/matejpalenik/inframeld/issues/131) admission; [#132](https://github.com/matejpalenik/inframeld/issues/132) conditional publication; [#133](https://github.com/matejpalenik/inframeld/issues/133) atomic first binding; [#134](https://github.com/matejpalenik/inframeld/issues/134) failure/race qualification |
| [#63](https://github.com/matejpalenik/inframeld/issues/63), Manual releases | [#135](https://github.com/matejpalenik/inframeld/issues/135) attach; [#136](https://github.com/matejpalenik/inframeld/issues/136) allocate traffic; [#137](https://github.com/matejpalenik/inframeld/issues/137) reject; [#138](https://github.com/matejpalenik/inframeld/issues/138) promote; [#139](https://github.com/matejpalenik/inframeld/issues/139) rollback |
| [#66](https://github.com/matejpalenik/inframeld/issues/66), case revisions/review | [#141](https://github.com/matejpalenik/inframeld/issues/141) benchmark freezing; [#142](https://github.com/matejpalenik/inframeld/issues/142) generation; [#143](https://github.com/matejpalenik/inframeld/issues/143) execution; [#144](https://github.com/matejpalenik/inframeld/issues/144)-[#146](https://github.com/matejpalenik/inframeld/issues/146) protected dataset export/import/source linking |
| [#44](https://github.com/matejpalenik/inframeld/issues/44), bounded source synchronization | [#126](https://github.com/matejpalenik/inframeld/issues/126) source configuration and [#127](https://github.com/matejpalenik/inframeld/issues/127) source authentication |

Other coherent capabilities remain with their existing issue IDs. Completed foundations were not reopened. In particular, #53 still includes only the planned `PipelineHook`/`WebhookDispatcher` interfaces, not executable hooks or a delivery service.

## Ticket System

The [implementation template](../../.github/ISSUE_TEMPLATE/implementation.md) and shared [Definition of Done](definition-of-done.md) distinguish implementation, specification, qualification and epic coordination. Tickets name logical inputs, state changes, failure/recovery outcomes, ownership, exclusions, behavioral evidence and architecture freshness. Qualification tickets do not claim runtime implementation; unresolved concrete contracts are explicit prerequisites.

Original valid requirements were reviewed and carried forward, including upload limits, bounded retries, idempotency retention, parser isolation, feedback attribution and provisional backup/capacity targets. Obsolete requirements were reconciled rather than copied: fixed evaluation judges, OpenEvals, mandatory pre-evaluation builds, pinned connection access, compulsory model probes and Studio-first release assumptions.

## Verification

<!-- BEGIN VERIFIED RESULTS -->

Independent GitHub read-back completed at **2026-10-01T12:52:17.439Z**.

| Check | Result |
| --- | --- |
| Existing issues reconciled | 100: 89 open rewritten; 11 closed foundations retained closed |
| New issues/epics | 74, #114-#187; complete links in the delivery-plan inventory |
| Total issues, excluding pull requests | 174 |
| Existing v1 milestone #1 | 159: 148 open, 11 closed |
| Deferred Studio | Exactly 15; no milestone |
| Native blocked-by edges | 316; 189 added, 29 removed from baseline |
| Native parent links | 158 across 18 parent containers |
| Relationship/body consistency | Exact match with the final manifest |
| Cycles and v1-to-Studio paths | None found |
| Existing state, closure timestamps, labels and assignees | Preserved |
| Decision coverage | 106 recorded capabilities mapped; the earlier live-configuration export proposal explicitly superseded |
| Documentation checks | 37 changed Markdown files; links/anchors, skill frontmatter, 56 ADRs and 106 unique decisions checked |

The working-tree comparison used the pre-edit content hashes, not a clean-checkout assumption. All 345 files outside the documented change set stayed byte-identical to that captured baseline, and no captured file was deleted. Targeted Prettier checks and `git diff --check` passed after formatting only the changed Markdown. HEAD remains the recorded baseline SHA. Product tests were deliberately not run.

Representative handoffs: [#80 generated clients](https://github.com/matejpalenik/inframeld/issues/80), [#132 guarded publication](https://github.com/matejpalenik/inframeld/issues/132), [#187 whole-CLI qualification](https://github.com/matejpalenik/inframeld/issues/187) and [#114 epic coordination](https://github.com/matejpalenik/inframeld/issues/114).

The CLI scripting review used [clig.dev](https://clig.dev/), especially structured output, separate diagnostics, noninteractive inputs and safe interruption. Universal descriptive dry-run is an accepted Inframeld extension, not a claim that the external guide mandates it for every command.

**GitHub counter discrepancy:** GitHub REST milestone aggregate reports 74 open/0 closed; individual issues, milestone-filtered listing and GraphQL independently confirm 148 open/11 closed. No membership toggle was performed to alter the counter. The maintainer was explicitly asked whether to retain the correct assignments and document this discrepancy or investigate further; no assignment was changed to manipulate an aggregate.

<!-- END VERIFIED RESULTS -->

The editorial walkthrough covers canceled/uncertain work, current permission changes, source erasure, changed chunking and unmappable expectations, partial generation/import, failed preparation, stale publication after mode changes, and configuration transfer without documents or secrets. These are specification reviews, not executed product scenarios.

## Remaining Gates

Eight explicitly blocked contract specifications remain: [#116](https://github.com/matejpalenik/inframeld/issues/116) identity/authority, [#121](https://github.com/matejpalenik/inframeld/issues/121) model metadata/impact, [#124](https://github.com/matejpalenik/inframeld/issues/124) durable operations, [#128](https://github.com/matejpalenik/inframeld/issues/128) experimental execution/Build, [#140](https://github.com/matejpalenik/inframeld/issues/140) evaluation, [#147](https://github.com/matejpalenik/inframeld/issues/147) tracing, [#151](https://github.com/matejpalenik/inframeld/issues/151) TOML portability and [#156](https://github.com/matejpalenik/inframeld/issues/156) automation/local recovery. These settle concrete application contracts, wire mappings and permission mapping without reopening accepted product decisions.

Runtime qualification remains required for browser OAuth/session security, gateway-only Ragas routing and telemetry suppression, structured output and claim calibration, model/provider compatibility, embedding vetoes, budget races and uncertain costs, prepared-data readiness, cancellation/fencing, protected evidence/erasure, release guards, installation/upgrade/restore and complete CLI automation. The client-generator package is deliberately unselected. There are no product-test results from this reconciliation.

## Maintained File Scope

The historical baseline preserves the complete original edit inventory. This reading list points only to maintained engineering documents and skills; accepted requirements are indexed in the [delivery plan](cli-delivery-plan.md#decision-coverage).

The maintained destinations below were among the files changed relative to that historical dirty-tree baseline, not to HEAD. The original complete inventory remains in the baseline; this reading list is not the scope of the latest pass.

<!-- BEGIN CHANGED FILES -->

- [.agents/skills/inframeld-access-models/SKILL.md](../../.agents/skills/inframeld-access-models/SKILL.md)
- [.agents/skills/inframeld-application-contracts/SKILL.md](../../.agents/skills/inframeld-application-contracts/SKILL.md)
- [.agents/skills/inframeld-evaluation/SKILL.md](../../.agents/skills/inframeld-evaluation/SKILL.md)
- [.agents/skills/inframeld-indexing/SKILL.md](../../.agents/skills/inframeld-indexing/SKILL.md)
- [.agents/skills/inframeld-knowledge/SKILL.md](../../.agents/skills/inframeld-knowledge/SKILL.md)
- [.agents/skills/inframeld-pipelines-releases/SKILL.md](../../.agents/skills/inframeld-pipelines-releases/SKILL.md)
- [.github/ISSUE_TEMPLATE/implementation.md](../../.github/ISSUE_TEMPLATE/implementation.md)
- [AGENTS.md](../../AGENTS.md)
- [README.md](../../README.md)
- [docs/ARCHITECTURE.md](../ARCHITECTURE.md)
- [docs/adr/ADR-0003-generate-the-authoritative-openapi-contract-from-backend-code.md](../adr/ADR-0003-generate-the-authoritative-openapi-contract-from-backend-code.md)
- [docs/adr/ADR-0006-use-official-generated-clients-for-application-api-access.md](../adr/ADR-0006-use-official-generated-clients-for-application-api-access.md)
- [docs/adr/ADR-0042-rerank-selected-evidence-through-a-local-cross-encoder-boundary.md](../adr/ADR-0042-rerank-selected-evidence-through-a-local-cross-encoder-boundary.md)
- [docs/adr/ADR-0055-deliver-cli-first-v1-through-openapi-generated-clients.md](../adr/ADR-0055-deliver-cli-first-v1-through-openapi-generated-clients.md)
- [docs/adr/ADR-0056-support-explicit-local-hosted-or-disabled-reranking.md](../adr/ADR-0056-support-explicit-local-hosted-or-disabled-reranking.md)
- [docs/adr/README.md](../adr/README.md)
- [docs/development/access-control.md](access-control.md)
- [docs/development/api-contracts.md](api-contracts.md)
- [docs/development/application-structure.md](application-structure.md)
- [docs/development/cli-delivery-plan.md](cli-delivery-plan.md)
- [docs/development/cli-reconciliation-report.md](cli-reconciliation-report.md)
- [docs/development/configuration-portability.md](configuration-portability.md)
- [docs/development/data-model.md](data-model.md)
- [docs/development/definition-of-done.md](definition-of-done.md)
- [docs/development/deployment.md](deployment.md)
- [docs/development/documentation-maintenance.md](documentation-maintenance.md)
- [docs/development/error-handling-reference.md](error-handling-reference.md)
- [docs/development/evaluation.md](evaluation.md)
- [docs/development/indexing.md](indexing.md)
- [docs/development/jobs-and-idempotency.md](jobs-and-idempotency.md)
- [docs/development/knowledge-lifecycle.md](knowledge-lifecycle.md)
- [docs/development/model-connections.md](model-connections.md)
- [docs/development/observability.md](observability.md)
- [docs/development/onboarding.md](onboarding.md)
- [docs/development/pipelines-and-releases.md](pipelines-and-releases.md)
- [docs/development/retention-and-deletion.md](retention-and-deletion.md)

<!-- END CHANGED FILES -->

Application code, tests, infrastructure/configuration, generated contracts and `apps/web/AGENTS.md` are outside the change set. No dependencies were installed, migrations/model calls run, credentials/grants changed, or commit created. GitHub discussion history was not rewritten.

## Correction Pass

This separately approved pass on **2026-10-01** corrects the eight review findings. Its baseline was the result above: **174 issues, 159 assigned to v1, 15 deferred Studio, 316 dependency edges and 11 closed issues**. A fresh snapshot captured all 382 nonignored repository files, issue bodies, metadata, parentage and native blockers before editing. The real SHA and explicitly uncommitted overlay remain unchanged; this pass created no commit.

### What changed

- The shared builder accepts the authorized caller's captured inputs. Explicit CLI Build selects current saved working settings; document-triggered updates select the Deployment's saved binding. Neither underlying build publishes traffic.
- Ordinary administration retains handover safeguards. Separate suspension/restoration and privileged scoped operator recovery provide emergency containment without an ordinary application superuser.
- Project budget management now has an implementation owner. Setup, management and import reuse that operation without resetting usage, reservations or operation limits. No account-level ceiling was introduced.
- The reusable scorer precedes complete evaluation runs; comparison composes two freshly scored runs without a second judge loop. Import explicitly depends on ordinary budget and tracing-policy mutation capabilities.
- Re-enabling Automatic initially selects the currently serving configuration. Canary routing retains stable buckets across percentage changes and credential rotation; allocating 100% does not promote.
- CLI feedback records CLI v1 feedback reporting and own-answer corrections using the existing backend. Both backend feedback and CLI evidence remain required release prerequisites; Studio stays deferred.

### Exact GitHub scope

Four new v1 implementation issues were created and attached to their existing parents:

| Issue | Capability | Parent |
| --- | --- | --- |
| [#188](https://github.com/matejpalenik/inframeld/issues/188) | Suspend and deliberately restore installation accounts | Access #2 |
| [#189](https://github.com/matejpalenik/inframeld/issues/189) | Recover stranded administrative responsibilities through scoped operator maintenance | Access #2 |
| [#190](https://github.com/matejpalenik/inframeld/issues/190) | Manage project spending policies without resetting accounting | Models #3 |
| [#191](https://github.com/matejpalenik/inframeld/issues/191) | Inspect live feedback and manage own-answer ratings through the CLI | CLI #114 |

The following **49 existing issues** had focused body and/or dependency corrections. Parent maps were refreshed only where affected; these are not reopened or replacement issues.

| Area | Updated issues |
| --- | --- |
| Parent/coordinator maps | [#2](https://github.com/matejpalenik/inframeld/issues/2), [#3](https://github.com/matejpalenik/inframeld/issues/3), [#7](https://github.com/matejpalenik/inframeld/issues/7), [#8](https://github.com/matejpalenik/inframeld/issues/8), [#9](https://github.com/matejpalenik/inframeld/issues/9), [#10](https://github.com/matejpalenik/inframeld/issues/10), [#14](https://github.com/matejpalenik/inframeld/issues/14), [#61](https://github.com/matejpalenik/inframeld/issues/61), [#63](https://github.com/matejpalenik/inframeld/issues/63), [#114](https://github.com/matejpalenik/inframeld/issues/114), [#115](https://github.com/matejpalenik/inframeld/issues/115) |
| Access and naming | [#27](https://github.com/matejpalenik/inframeld/issues/27), [#28](https://github.com/matejpalenik/inframeld/issues/28), [#116](https://github.com/matejpalenik/inframeld/issues/116), [#117](https://github.com/matejpalenik/inframeld/issues/117), [#178](https://github.com/matejpalenik/inframeld/issues/178) |
| Spending and setup | [#37](https://github.com/matejpalenik/inframeld/issues/37), [#121](https://github.com/matejpalenik/inframeld/issues/121), [#123](https://github.com/matejpalenik/inframeld/issues/123), [#166](https://github.com/matejpalenik/inframeld/issues/166), [#168](https://github.com/matejpalenik/inframeld/issues/168) |
| Build, release and canary | [#54](https://github.com/matejpalenik/inframeld/issues/54), [#58](https://github.com/matejpalenik/inframeld/issues/58), [#62](https://github.com/matejpalenik/inframeld/issues/62), [#65](https://github.com/matejpalenik/inframeld/issues/65), [#128](https://github.com/matejpalenik/inframeld/issues/128), [#130](https://github.com/matejpalenik/inframeld/issues/130), [#131](https://github.com/matejpalenik/inframeld/issues/131), [#134](https://github.com/matejpalenik/inframeld/issues/134), [#136](https://github.com/matejpalenik/inframeld/issues/136) |
| Evaluation | [#68](https://github.com/matejpalenik/inframeld/issues/68), [#69](https://github.com/matejpalenik/inframeld/issues/69), [#70](https://github.com/matejpalenik/inframeld/issues/70), [#71](https://github.com/matejpalenik/inframeld/issues/71), [#140](https://github.com/matejpalenik/inframeld/issues/140), [#143](https://github.com/matejpalenik/inframeld/issues/143), [#180](https://github.com/matejpalenik/inframeld/issues/180) |
| Tracing and import | [#147](https://github.com/matejpalenik/inframeld/issues/147), [#149](https://github.com/matejpalenik/inframeld/issues/149), [#151](https://github.com/matejpalenik/inframeld/issues/151), [#154](https://github.com/matejpalenik/inframeld/issues/154), [#155](https://github.com/matejpalenik/inframeld/issues/155) |
| Feedback, automation and assembled qualification | [#75](https://github.com/matejpalenik/inframeld/issues/75), [#93](https://github.com/matejpalenik/inframeld/issues/93), [#96](https://github.com/matejpalenik/inframeld/issues/96), [#101](https://github.com/matejpalenik/inframeld/issues/101), [#156](https://github.com/matejpalenik/inframeld/issues/156), [#186](https://github.com/matejpalenik/inframeld/issues/186), [#187](https://github.com/matejpalenik/inframeld/issues/187) |

The completed foundations, #53's interface-only hook scope, #72-74's backend feedback contracts, the issue template and Definition of Done were preserved. Existing titles, issue states, closure timestamps, labels and assignments were not changed by this pass. New issue IDs were journaled; bodies were re-read before guarded updates, and native relationships were reconciled with their body descriptions.

### Walkthrough evidence

These are editorial walkthroughs of the accepted rules and ticket handoffs, **not executed product tests**.

| Scenario reviewed | Required outcome and handoff |
| --- | --- |
| Deployment cfg_17 versus experimental working cfg_18 | #128 distinguishes admission sources; #54 never replaces the caller's fixed selection; #58 exercises the real builder for both paths. |
| Sole manager compromised; Hydra cleanup incomplete | #188 blocks locally while retaining assignments and reports provider cleanup separately. #189 can repair only a verified missing responsibility, without unblocking the compromised account. #96 qualifies the sequence. |
| Budget lowered below settled usage with unresolved holds | #190 changes policy only; #123 retains all obligations and coordinates future admission. #37 qualifies races; #168/setup/import reuse those operations. |
| Imported budget/tracing values differ from destination | #151/#154 preserve destination settings by default. Explicit apply invokes ordinary authorized mutations; #155 covers stale review, retained accounting and partial recovery. |
| Fresh scored baseline/candidate comparison | #69 scores each eligible case with explicit denominators, #143 executes a complete run, and #68 composes two fresh runs. #70 reads history without another judge pass; #71 qualifies failures and calibration. |
| Late feedback after promotion | #72-74 retain original receipt attribution; #75 requires real canary/automatic paths. #191 reports coverage and permits only originating-principal corrections; #186/#187 qualify the CLI. |
| Automatic to Manual to Automatic | #62 defaults to the now-serving version's configuration, not an obsolete binding or working edits. A fresh control revision/admission prevents an old job regaining publication authority; #65/#134 exercise this. |
| Stable canary cohorts | #136 separates allocation administration from authenticated #55 routing. Percentage is a threshold, credential bytes do not define affinity, and 100% traffic remains distinct from promotion. |

The whole-backlog audit checked active requirements for obsolete client tooling, OpenEvals/fixed-judge assumptions, executable pinned connectivity, compulsory pre-evaluation builds, Studio-first dependencies, unselected account ceilings and stale automatic bindings. Remaining historical/exclusion mentions are identified as such. The junior-engineer pass checked affected tickets for worked examples, ordered workflow, ownership, effect boundaries, failures, recovery, specific acceptance scenarios and curated references. No further unresolved product-policy conflict was identified; missing concrete contracts remain explicit gates below.

### Verification for this pass

<!-- BEGIN CORRECTION RESULTS -->

Final independent GitHub read-back completed at **2026-10-01T13:47:07.672Z**, after the last acceptance-scenario wording correction.

| Check | Result |
| --- | --- |
| Existing issues updated / new issues | 49 / 4; exact links above |
| Total issues, excluding pull requests | 178 |
| Existing v1 milestone #1 | 163: 152 open, 11 closed |
| Deferred Studio | Exactly #12, #13, #81 and #83-94: 15, outside v1 |
| Native blocked-by edges | 354: 39 added, 1 removed in this pass |
| Native parent links | 162 across the same 18 parent containers |
| Saved bodies, parent maps and dependencies | Matched the final manifest, including all four new IDs |
| Cycles, v1-to-Studio paths and release reachability | No cycles or Studio paths; every non-container v1 issue is reachable through release #102's prerequisites |
| Preserved GitHub metadata | All existing states, closure timestamps, labels and assignees unchanged; all 11 completed issues still closed |
| Decision traceability | All 107 recorded capabilities covered; the earlier live-configuration export proposal remains explicitly superseded; per-owner qualification paths retain CLI and backend gates |
| File-scope comparison | Exactly 12 approved Markdown files changed; the other 370 captured files remain byte-identical; no captured file deleted |
| Reference checks | 96 Markdown files, 2,132 local links/anchors and 902 issue-local document references checked; 56 ADRs unchanged in count |
| Editorial tooling | Targeted Prettier checks and `git diff --check` passed; all three modified skills passed the skill validator |

The earlier milestone-counter discrepancy is no longer present in this read-back: REST reports 152 open/11 closed, matching individual assignments and the milestone-filtered issue listing. No existing memberships were toggled to manipulate the counter. No error or warning remained in the final graph/metadata verification. These results verify planning artifacts, not software behavior, provider compatibility or security qualification.

<!-- END CORRECTION RESULTS -->

### Maintained repository scope

The original correction-pass inventory remains in the preserved baseline. Current requirement ownership is in the [delivery plan](cli-delivery-plan.md#decision-coverage); the links below identify maintained destinations.

These maintained destinations were among the files changed in that historical pass. Its complete original inventory remains in the baseline:

- [docs/development/cli-delivery-plan.md](cli-delivery-plan.md)
- [docs/development/cli-reconciliation-report.md](cli-reconciliation-report.md)
- [docs/development/access-control.md](access-control.md)
- [docs/development/answer-feedback.md](answer-feedback.md)
- [docs/development/api-contracts.md](api-contracts.md)
- [docs/development/data-model.md](data-model.md)
- [docs/development/model-connections.md](model-connections.md)
- [docs/development/pipelines-and-releases.md](pipelines-and-releases.md)
- [.agents/skills/inframeld-access-models/SKILL.md](../../.agents/skills/inframeld-access-models/SKILL.md)
- [.agents/skills/inframeld-application-contracts/SKILL.md](../../.agents/skills/inframeld-application-contracts/SKILL.md)
- [.agents/skills/inframeld-pipelines-releases/SKILL.md](../../.agents/skills/inframeld-pipelines-releases/SKILL.md)

### Developer handoff

Use the [delivery plan](cli-delivery-plan.md#specification-gates) and native blockers to choose work. The eight existing specifications (#116, #121, #124, #128, #140, #147, #151 and #156) still must settle concrete permission/eligibility mappings, wire and revision contracts, operation recovery and adapter responsibilities before dependent implementation. Do not infer a missing permission or published schema from an example screen.

The corrected backlog is an implementation plan, not evidence that the intended product exists. Runtime tests remain required for identity cleanup/restoration, privileged recovery, budget-policy/admission races, Ragas integration/scoring, policy imports, exact Build inputs, stable routing and late feedback, alongside all retained security, lifecycle, capacity and CLI qualification. No application code, test, dependency, generated contract, migration, paid model call or commit was added by this correction pass.

<a id="requirements-transfer-checkpoint"></a>

## Historical Transfer Checkpoint: 2026-10-02

**Historical checkpoint, not current publication status.** At this stage, requirements transfer into self-contained implementation tickets and maintained guides was incomplete. Later publication and the [2026-10-03 handoff recheck](#handoff-recheck) supersede that pending status. Preserve the evidence below as a record of what had actually happened at this earlier checkpoint, not as a claim that GitHub is still awaiting those updates.

### Preserved baseline

The checkpoint baseline uses real HEAD `b3bbfc438a6dbc390e4bd56210474bacaf177a49` and captures 382 existing tracked/untracked files plus 178 GitHub issues and their native relationship graph. A byte-identical source snapshot and the supporting migration artifacts were preserved outside the repository:

```text
/Users/matej/Documents/inframeld-decision-archive/2026-10-02T19-26-23-533Z/
```

Source-snapshot SHA-256: `ba40666c6bfda1b7fb3c7fc97fa26d990dce354c3d27df3fab2ef3cf211c5d81`. This archive is historical evidence, not a required implementation reading path.

The archive also contains repository/GitHub baselines, source-section extraction, a candidate requirement ledger and the then-unpublished issue drafts. The extraction contains 523 heading sections and 3,246 source blocks; these are **inventory counts, not verified atomic-requirement coverage**. At this checkpoint, compound blocks still needed classification and destination/acceptance checking. The historical ledger did not mark them complete merely because a corresponding issue existed.

### Transferred into guide drafts

- [Access](access-control.md#cli-client-registration): exact first-party registration, validated login commit, rotating refresh, scoped logout, cleanup uncertainty, application-key input and authentication qualification.
- [API contracts](api-contracts.md#cli-context): precise context/environment precedence, one-server-URL discovery, descriptive dry-run and bounded list traversal.
- [Deployment](deployment.md#managed-local-http): complete managed-local HTTP boundaries, proxy/origin checks, private services, failure behavior and residual risks.
- [Onboarding](onboarding.md#host-bootstrap): host-bound bootstrap, explicit/resumable setup and generated starter naming.
- [Data model](data-model.md#resource-naming): name grammar, scope, collision/rename/retirement semantics and stable identity.
- [Pipelines/Releases](pipelines-and-releases.md#generation-context-contract): corpus-wide candidate limits, ranked-prefix assembly, explicit output allowance and optional/provider-default temperature.
- [ADR-0053](../adr/ADR-0053-use-kratos-and-hydra-for-human-cli-authentication.md) and the Access, Application Contracts and Pipelines/Releases skills now route these transferred details to their owning guides.

Together with this report, those are the eleven repository files changed at this checkpoint. No application code, tests, configuration, root guidance, dependency or generated contract is part of the changes. No commit was created.

### Publication status at the checkpoint

Unpublished body drafts then existed for #27, #53, #55, #95, #96, #116, #117, #118, #120, #121, #151, #156, #158, #159, #160, #161, #162, #166 and #185. They retained existing top-level template headings but were not a complete manifest: references, issue-relative links, acceptance coverage and owner-specific duplication still needed review. No issue body, metadata, state or native relationship had been changed by that checkpoint operation.

A complete review of all 118 capabilities and supplementary sources was still required at that checkpoint. Remaining work included transferring workflows, reconciling tickets and guides, replacing references, preparing the manifest, checking concurrent edits and reading back GitHub changes. The checkpoint alone established neither published coverage nor developer readiness. The eight engineering specification gates remained separate implementation obligations.

### Editorial evidence at the checkpoint

Targeted Prettier formatting of the transferred guide/ADR/skill files and this report completed without formatting changes. The three changed skills passed their frontmatter validators and `git diff --check` passed. The checkpoint compared all 382 baseline files: exactly the eleven files listed above changed and 371 remained byte-identical, with no new repository file. The original/archive hashes match.

All 37 newly introduced local links/anchors resolve, and the 19 unpublished drafts retain their original top-level headings and Definition of Done. These were local editorial checks, not authentication, model, CLI or product tests. Full requirement coverage, existing-reference reconciliation, published manifest equality, fresh graph/milestone checks and retirement proof were separate outstanding checks at that checkpoint.

<a id="handoff-recheck"></a>

## Handoff Recheck: 2026-10-03

This is the current result of the separately approved reference-cleanup and five-ticket correction pass. GitHub requirements had already been published after the historical checkpoint above. This pass re-read all **178 issues** and their native relationships, then changed only the five bodies below. The real baseline remains `b3bbfc438a6dbc390e4bd56210474bacaf177a49`; maintained documentation includes an explicitly uncommitted overlay through **2026-10-03**. No commit or push was made.

### Published corrections

| Issue | Concrete correction |
| --- | --- |
| [#29](https://github.com/matejpalenik/inframeld/issues/29) | Distinguishes denied Query from an authorized query with no readable evidence. The latter performs no Chroma search and follows normal no-evidence behavior. Protected bundles still require every source at disclosure. |
| [#98](https://github.com/matejpalenik/inframeld/issues/98) | Makes complete Kratos/Hydra state, external recovery keys/configuration, public CLI registration and stopped identity writers explicit backup requirements. Missing material is an incomplete backup. |
| [#99](https://github.com/matejpalenik/inframeld/issues/99) | Requires coherent identity restoration, independently verified credential invalidation, newer-restriction reconciliation and fresh current-permission login before reopening. Partial cleanup stays restricted. |
| [#100](https://github.com/matejpalenik/inframeld/issues/100) | Includes both identity services and the account UI in upgrade qualification. Distinguishes a normal compatible upgrade from restoring a backup, and rejects incompatible image-only rollback. |
| [#165](https://github.com/matejpalenik/inframeld/issues/165) | Uses those owning backup/restore/upgrade requirements, with explicit incomplete-backup and partial-migration outcomes. Removes the now-corrected inventory-gap warning. |

Each body was compared with the fresh baseline immediately before update and read back afterward. Top-level template headings, Definition of Done, states, closure timestamps, titles, labels, assignees, milestones and native relationships are unchanged. The other **173 issue bodies** are byte-identical to this pass's baseline. No new issue, permission identifier, endpoint, migration or recovery protocol was introduced.

### Verification and limits

The independent GitHub readback completed at **2026-10-03T00:24:14.599Z**. It confirmed **163 v1 issues, 15 deferred Studio issues, 11 closed issues, 354 blocker edges and 162 parent links**. All 167 body dependency declarations and 17 coordinator child maps match native relationships. There are no dependency cycles or v1 paths through Studio. Release #102 reaches all 136 other open, non-container v1 issues through prerequisites.

At this checkpoint, repository references led to owning guides, ADRs or self-contained tickets. No other repository file or GitHub issue body referred to the retired source filename. All **118 capability mappings** remained in the delivery index, including the explicit supersession of the earlier live-configuration export proposal. The original source document was left present and byte-identical. That pass did not delete it.

The local editorial check passed across **101 Markdown files, 1,978 local links/anchors, 4,232 issue links and 1,260 issue-local document references**. The 56-ADR index and all 118 ownership rows are consistent, and all four changed skills retain valid, byte-identical frontmatter. Targeted Prettier checks and `git diff --check` passed. The junior-engineer walkthrough follows denied Query, authorized empty scope, revoked bundle sources, incomplete Hydra backup, independent cleanup failure, fresh login after restore and committed identity migration followed by failed readiness. These are editorial checks and requirement walkthroughs, not executed product tests.

**One publication step remains outside this scope:** commit and push the maintained guides, ADRs, template and Definition of Done already in the working tree. Eleven distinct Markdown paths referenced by issues are not present at the recorded baseline commit, including the Definition of Done, delivery plan, observability/portability guides and ADRs 0050-0056. Existing tracked guides also contain uncommitted corrections. Tickets correctly identify this overlay instead of pretending those files exist at the SHA. Publish the complete reviewed documentation together so a developer on another machine can follow those references.

The eight specification tickets remain development prerequisites for exact contracts, not unresolved choices about the accepted product. Follow native blockers rather than issue-number order. Implementation, vendor compatibility, security, recovery, capacity and end-to-end CLI qualification must still be performed by the owning tickets. This pass adds no claim that the product is implemented or tested.

### Exact files changed in this pass

Compared with the fresh 382-file baseline, **30 Markdown files** changed and the other **352 files** remain byte-identical. No file was created or deleted in the repository. The exact list follows.

- [.agents/skills/inframeld-access-models/SKILL.md](../../.agents/skills/inframeld-access-models/SKILL.md)
- [.agents/skills/inframeld-application-contracts/SKILL.md](../../.agents/skills/inframeld-application-contracts/SKILL.md)
- [.agents/skills/inframeld-evaluation/SKILL.md](../../.agents/skills/inframeld-evaluation/SKILL.md)
- [.agents/skills/inframeld-pipelines-releases/SKILL.md](../../.agents/skills/inframeld-pipelines-releases/SKILL.md)
- [docs/ARCHITECTURE.md](../ARCHITECTURE.md)
- [docs/adr/ADR-0038-recover-from-a-coordinated-backup-of-the-installation.md](../adr/ADR-0038-recover-from-a-coordinated-backup-of-the-installation.md)
- [docs/adr/ADR-0051-use-ragas-for-generated-tests-and-faithfulness-evaluation.md](../adr/ADR-0051-use-ragas-for-generated-tests-and-faithfulness-evaluation.md)
- [docs/adr/ADR-0052-separate-experimental-execution-from-release-ready-pipeline-builds.md](../adr/ADR-0052-separate-experimental-execution-from-release-ready-pipeline-builds.md)
- [docs/adr/ADR-0054-use-shared-current-model-connections.md](../adr/ADR-0054-use-shared-current-model-connections.md)
- [docs/adr/ADR-0055-deliver-cli-first-v1-through-openapi-generated-clients.md](../adr/ADR-0055-deliver-cli-first-v1-through-openapi-generated-clients.md)
- [docs/adr/ADR-0056-support-explicit-local-hosted-or-disabled-reranking.md](../adr/ADR-0056-support-explicit-local-hosted-or-disabled-reranking.md)
- [docs/adr/README.md](../adr/README.md)
- [docs/development/access-control.md](access-control.md)
- [docs/development/answer-feedback.md](answer-feedback.md)
- [docs/development/api-contracts.md](api-contracts.md)
- [docs/development/cli-delivery-plan.md](cli-delivery-plan.md)
- [docs/development/cli-reconciliation-report.md](cli-reconciliation-report.md)
- [docs/development/configuration-portability.md](configuration-portability.md)
- [docs/development/data-model.md](data-model.md)
- [docs/development/deployment.md](deployment.md)
- [docs/development/evaluation.md](evaluation.md)
- [docs/development/indexing.md](indexing.md)
- [docs/development/jobs-and-idempotency.md](jobs-and-idempotency.md)
- [docs/development/mcp.md](mcp.md)
- [docs/development/model-connections.md](model-connections.md)
- [docs/development/observability.md](observability.md)
- [docs/development/onboarding.md](onboarding.md)
- [docs/development/pipelines-and-releases.md](pipelines-and-releases.md)
- [docs/development/retention-and-deletion.md](retention-and-deletion.md)
- [docs/development/upgrades-and-recovery.md](upgrades-and-recovery.md)

No application code, tests, runtime configuration, dependencies, generated contracts, migrations, paid model calls, credentials or grants were changed. Earlier working-tree edits and historical report evidence were preserved.

<a id="authentication-handoff-2026-10-04"></a>

## Authentication Handoff Corrections: 2026-10-04

This separately approved pass makes the accepted authentication requirements explicit in their backend, account-UI and client tickets. It does not introduce another authentication protocol or change the permission model. The real baseline remains `b3bbfc438a6dbc390e4bd56210474bacaf177a49`, with an explicitly uncommitted documentation overlay through **2026-10-04**. Repository paths identify that overlay, not files claimed to exist at the baseline SHA.

### Published ticket changes

| Issue | Correction and motivation |
| --- | --- |
| [Access contracts #116](https://github.com/matejpalenik/inframeld/issues/116) | Specifies the compatible human-session extension and one verifier per credential family. Keeps cookie CSRF, current identity checks, the principal-only context and exact permission/wire mappings with their owners. Removes the old decision-code shorthand from the workflow. |
| [Hydra integration #117](https://github.com/matejpalenik/inframeld/issues/117) | Owns bearer verification on the existing session operation and protected routes. Each request checks Hydra, current Kratos eligibility and the local human; a previous success is not cached authority. Adds repeated-request, revocation, outage, credential-confusion and recovery-cleanup scenarios. |
| [Application lifecycle #30](https://github.com/matejpalenik/inframeld/issues/30) | Owns account creation, full-authority key issuance, safe metadata, independent revocation and terminal retirement. Alice cannot issue a key to gain access she cannot delegate; an authorized revoker can revoke the last key without that access. Concurrent issuance cannot exceed two usable keys. Retirement preserves project-owned work. |
| [Ordinary administration #28](https://github.com/matejpalenik/inframeld/issues/28), [Access epic #2](https://github.com/matejpalenik/inframeld/issues/2) | Separates ordinary membership/group/grant changes and handover from #30's lifecycle operations. Keeps suspension/restoration and scoped operator recovery in #188-189. Updates the epic's description of #30. |
| [Account UI #82](https://github.com/matejpalenik/inframeld/issues/82) | Names password settings, recovery completion and configured MFA challenges alongside registration, login and consent. Failed, expired or canceled required steps cannot become successful activation or CLI login. Ory and backend operations remain responsible for verification and admission. |
| [Invitations #119](https://github.com/matejpalenik/inframeld/issues/119) | Requires #28's ordinary membership/grant operations and current authority during activation. An invitation cannot become a second permission-writing path after the inviter loses authority. |
| [Security qualification #96](https://github.com/matejpalenik/inframeld/issues/96) | Requires the actual CLI login artifact and evidence for current bearer checks, backend key administration, required account steps and independent cleanup outcomes. Preserves all infrastructure and recovery qualification. |
| [Human CLI login #160](https://github.com/matejpalenik/inframeld/issues/160), [application connection #161](https://github.com/matejpalenik/inframeld/issues/161), [first-use qualification #185](https://github.com/matejpalenik/inframeld/issues/185) | Aligns presentation with the backend owners. A browser callback is not admission or secure credential storage; a CLI review cannot replace server-side issuance checks. Preserves login, refresh, logout, connection and mixed-provider onboarding requirements. |
| [Completed Kratos foundation #25](https://github.com/matejpalenik/inframeld/issues/25) | Adds a historical clarification only. Its original "No Hydra" boundary does not exclude the later #117 integration or #82 account UI. The issue remains closed and its original scope and completion history remain intact. |

Two native blockers and their issue-body declarations were added: **#119 is blocked by #28**, and **#96 is blocked by #160**. No other dependency or parent changed. No issue was created or reopened, and no title, milestone, label or assignment changed.

### Publication verification

A fresh baseline captured all 178 issues, native relationships and 381 repository files before editing. The complete issue-body/dependency manifest was prepared before publication. Each affected issue was re-read immediately before updating and compared with its baseline, then read back afterward. The independent whole-backlog readback completed at **2026-10-04T06:32:41.890Z**.

- All **12 changed issue bodies** match the reviewed manifest. The other **166 bodies** are byte-identical to the baseline. Existing top-level headings and Definitions of Done are unchanged.
- All **11 completed issues** remain closed. States, closure timestamps, titles, labels, assignees and milestones are preserved.
- The backlog still has **178 issues: 163 v1 and 15 deferred Studio**, now with **356 blocker edges** and **162 parent links**.
- All **167 current body dependency declarations** and **17 coordinator child maps** match native relationships. There are no dependency cycles or v1 paths through deferred Studio.
- Release #102 still reaches all **136 other open, non-container v1 issues** through prerequisites.

### Repository scope and reading walkthrough

Only these three files were edited in this pass:

- [Access control](access-control.md): distinguishes the required standalone account UI and pending bearer integration from deferred Studio and existing Kratos test coverage.
- [CLI delivery plan](cli-delivery-plan.md): explains authentication ownership, retains all 118 capability mappings and updates the 11 prerequisite rows affected by the two new blockers.
- [This report](cli-reconciliation-report.md#authentication-handoff-2026-10-04): appends this dated result without rewriting earlier evidence.

The editorial walkthrough follows a successful request and then provider disablement, local suspension or revoked grants; cookie-write CSRF and competing credentials; incomplete password/MFA flows; lost login replacement; insufficient key-issuance authority; independent last-key revocation; concurrent issuance and retirement; changed invitation authority; and incomplete Kratos/Hydra cleanup. Each outcome points to a backend owner and a concrete acceptance scenario. These are requirement checks, not executed authentication tests.

Local validation passed for **414 local links/anchors**, including **83 document references in the changed issue bodies**. Existing anchors, code examples, all 118 capability owners and their qualification mappings are preserved. Targeted Prettier checks, `git diff --check` and the staged whitespace check passed. Against the fresh 381-file baseline, exactly the three approved files changed; the other **378 files**, all staged changes and HEAD are unchanged. No repository file was added or removed. Earlier report text remains byte-identical.

### Remaining engineering work

[Access contracts #116](https://github.com/matejpalenik/inframeld/issues/116) still needs reviewed wire fields, exact credential dispatch, permission mappings and verified recovery-completion integration. These are engineering deliverables for accepted behavior, not newly unresolved product choices. The owning implementation tickets must then build the behavior, and #96/#185 must qualify real Ory versions, account screens, CLI credentials and failure paths. Configured MFA support neither makes MFA mandatory nor chooses a new factor.

Publish the maintained documentation overlay before handing another developer a clean checkout. This pass made no commit, application/configuration change, credential/grant mutation, dependency installation or product-test run. It does not claim that the authentication features are implemented or security-qualified.

<a id="lifecycle-handoff-2026-10-04"></a>

## Project and Deployment Handoff Corrections: 2026-10-04

This separately approved pass closes three delivery gaps without changing product policy: ordinary project lifecycle ownership, the complete CLI Deployment journey and portability's prerequisite tracing contract. It preserves the earlier reports above as historical evidence.

The fresh baseline captured **381 repository files and 178 GitHub issues**. It inspected the developer's newer documentation commit, `f968e81f4f660a750d5d8e5da58452e4ece4d86c`. Earlier tickets retain their real `b3bbfc438a6dbc390e4bd56210474bacaf177a49` baseline and dated overlay history. This correction adds an explicit **2026-10-04 uncommitted overlay**; it does not claim those additions existed at either commit. No commit was created by this pass.

### Published ticket changes

| Issues | What changed and why |
| --- | --- |
| [Access contracts #116](https://github.com/matejpalenik/inframeld/issues/116), [ordinary administration #28](https://github.com/matejpalenik/inframeld/issues/28), [starter provisioning #27](https://github.com/matejpalenik/inframeld/issues/27) | Ordinary creation checks Create projects and saves the project, creator membership and seven initial assignments together. The starter remains a separate path. Adds naming, denial, lost-response and changed-authority scenarios. |
| [New project-deletion admission #204](https://github.com/matejpalenik/inframeld/issues/204) | Under Access Epic #2 and milestone v1. Owns current Delete project checks, the authoritative block, application/key shutdown and durable cleanup handoff. Alice can erase private project contents without gaining reading access or needing each item's Delete permission. |
| [Application lifecycle #30](https://github.com/matejpalenik/inframeld/issues/30), [protected jobs #38](https://github.com/matejpalenik/inframeld/issues/38), [physical cleanup #45](https://github.com/matejpalenik/inframeld/issues/45) | Separates whole-project admission from individual-document deletion and physical cleanup. Reuses application/key enforcement and narrow status after membership removal; interruption cannot reopen access or expand scope. |
| [CLI access #178](https://github.com/matejpalenik/inframeld/issues/178), [setup #166](https://github.com/matejpalenik/inframeld/issues/166), [import review #153](https://github.com/matejpalenik/inframeld/issues/153) | Exposes ordinary creation/deletion, preserves completed setup steps and requires a confirmed destination before import. No implicit project creation, starter recreation or private inventory disclosure. |
| [CLI Deployment management #174](https://github.com/matejpalenik/inframeld/issues/174), [command contracts #156](https://github.com/matejpalenik/inframeld/issues/156) | Adds import-to-unpublished-Build-to-explicit-Deployment creation, both mode changes and default-route inspection/repair. Uses existing backend owners; explicit creation defaults to Manual, and a changed review is never accepted silently. |
| [Portability contracts #151](https://github.com/matejpalenik/inframeld/issues/151) | Requires the owning tracing/retention specification #147 instead of allowing TOML to invent another policy model. |
| [Security #96](https://github.com/matejpalenik/inframeld/issues/96), [first use #185](https://github.com/matejpalenik/inframeld/issues/185), [development/releases #186](https://github.com/matejpalenik/inframeld/issues/186), [whole CLI #187](https://github.com/matejpalenik/inframeld/issues/187) | Adds real lifecycle, race, denial and recovery evidence to the existing qualification requirements. Human, JSON, noninteractive and dry-run paths must work without Studio or handwritten API calls. |
| [Access Epic #2](https://github.com/matejpalenik/inframeld/issues/2), [Knowledge Epic #5](https://github.com/matejpalenik/inframeld/issues/5), [Releases Epic #8](https://github.com/matejpalenik/inframeld/issues/8), [CLI Epic #114](https://github.com/matejpalenik/inframeld/issues/114), [portability Epic #115](https://github.com/matejpalenik/inframeld/issues/115) | Updates the relevant child map and cross-owner delivery descriptions. Keeps completed foundations and deferred Studio scope intact. |

Eight native blockers and their issue-body declarations were added:

- **#204 is blocked by #28, #30, #38 and #125.**
- **#45 is blocked by #204.**
- **#178 and #96 are blocked by #45.**
- **#151 is blocked by #147.**

The new issue uses the existing implementation template and unchanged shared Definition of Done. Existing issue headings, Definitions of Done and coordinator completion evidence are unchanged. No existing issue title, state, closure timestamp, label, assignee, milestone or parent was changed.

### Publication verification

All proposed issue bodies and relationships were prepared before publication. The current issues and graph were checked against the baseline, each changed issue was re-read immediately before its update, and each result was read back. The new issue number was journaled before dependent bodies were published, so an interrupted run could recover without creating a duplicate.

Independent whole-backlog readback completed at **2026-10-04T07:46:06.642Z**:

- **21 existing bodies updated**, **157 existing bodies unchanged**, and **one new issue, #204**.
- **179 issues: 164 v1 and 15 deferred Studio.** The same **11 completed issues** remain closed.
- **364 blocker edges and 163 parent links.** All **168 body dependency declarations** and **17 coordinator child maps** match native relationships.
- **No dependency cycles and no v1 dependency path through Studio.** Release #102 reaches all **137 other open, non-container v1 issues**, including the new deletion capability.

### Repository scope and reading walkthrough

Only these five files were changed:

- [Access control](access-control.md): ordinary project creation, deletion admission and their permission/recovery boundaries.
- [Retention and deletion](retention-and-deletion.md): project shutdown before data cleanup, trusted scope handoff and honest protected progress.
- [Onboarding](onboarding.md): reusable creation, preserved partial setup and the explicit CLI path from imported configuration to a live Deployment and repaired default route.
- [CLI delivery plan](cli-delivery-plan.md): ownership/dependency guidance, all 118 earlier mappings plus two explicit lifecycle mappings, and a readable 179-issue inventory.
- [This report](cli-reconciliation-report.md#lifecycle-handoff-2026-10-04): appends the correction and its evidence without rewriting earlier results.

The junior-engineer walkthrough covers authorized and denied creation, naming conflicts, lost responses, private-project deletion, racing uploads/keys/publication, interrupted cleanup and safe status after membership removal. It also covers import, separately supplied credentials/documents, unpublished Build, explicit Manual/Automatic creation, mode changes, candidate-at-zero restrictions, stale reviews and default-route repair that preserves the selected Deployment's own mode. Tracing portability follows the owning contract. These are editorial scenario checks, not executed product tests.

Local validation checked **1,715 local links/anchors**, including **1,306 document references across all 179 issue bodies**, with no missing files or anchors. Existing guide anchors and code examples remain intact. All **118 earlier capability owners and qualification mappings** are preserved; the two added lifecycle mappings bring the total to **120**. All prerequisite unions match the verified graph, including **55 updated earlier rows**. The previously collapsed inventory is now a valid 179-row Markdown table with the same existing issue identities plus #204.

Targeted Prettier checks, `git diff --check` and the staged whitespace check passed. Against the fresh 381-file baseline, exactly the five approved files changed; the other **376 files**, staged state and HEAD remain unchanged. No repository file was added or removed. Earlier report text remains byte-identical. These checks establish editorial and dependency consistency, not runtime correctness.

### Remaining engineering work

[Access contracts #116](https://github.com/matejpalenik/inframeld/issues/116), [job contracts #124](https://github.com/matejpalenik/inframeld/issues/124) and [CLI contracts #156](https://github.com/matejpalenik/inframeld/issues/156) must define exact reviewed inputs, wire outcomes, permission mappings and concurrency/recovery contracts. The tracing contract #147 precedes portability #151. These are existing prerequisite engineering deliverables, not reopened product decisions or newly invented public schemas.

Implement owners in dependency order and retain runtime qualification in #96/#185-187. No application code, tests, runtime settings, migrations, generated contracts, dependencies, credentials or grants were changed. No product tests or paid model calls ran. Publish the five documentation changes before handing another developer a clean checkout; this pass does not claim that the described features already work.
