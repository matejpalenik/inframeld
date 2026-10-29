# Maintaining Inframeld's architecture documentation

<a id="maintaining-inframelds-architecture-documentation"></a>

Use this guide when adding or rewriting documentation. A new maintainer should be able to find a current rule, understand it through an example, and follow a link to exact details without first reading the decision history.

> **Status:** this is repository writing and maintenance guidance. It does not approve new product behavior or establish implementation evidence.

<a id="where-information-belongs"></a>

## Where information belongs

| Information | Authoritative home |
| --- | --- |
| Product introduction and contributor learning routes | `docs/ARCHITECTURE.md` and [developer guides](README.md). |
| Accepted feature behavior, architectural constraints and failures | The focused workflow or architecture reference in the owning skill. |
| Logical records and relationships | The owning skill’s focused record reference, with implemented definitions linked directly. |
| Implemented values, HTTP fields and database constraints | Python/Pydantic definitions, native generated OpenAPI and migrations. Do not copy them into another schema manual. |
| Architectural choice and supersession | [ADRs](../adr/README.md). |
| Unresolved alternatives and decision trigger | The existing owning `decision-*.md` reference. |
| Requested code review process, ratings and readiness report | [Review](../../.agents/skills/inframeld-review/SKILL.md), applying existing language/domain standards rather than redefining them. |
| Agent discovery and task method | Concise `SKILL.md` metadata/body with direct conditional links. |
| Shared SDK maintenance and cross-language qualification | [SDKs](../../.agents/skills/inframeld-sdks/SKILL.md), with independently discoverable language skills for specific behavior. Application Contracts retains HTTP semantics and compatibility. |
| Test layers, dependency isolation and verification evidence | [Testing](../../.agents/skills/inframeld-testing/SKILL.md). The shared Coding Standards retains TDD/documentation, language standards retain test-code conventions, domains retain business expectations, and runbooks retain commands. |
| Development and operator procedures | Human guides and runbooks, with current implementation limits explicit. |

Give each rule one detailed owner. A human guide may explain its purpose briefly, then link to that owner. Avoid parallel specifications, large required reading stacks and copies of exact code declarations. Existing code may intentionally lag accepted design. Label that gap rather than changing the target during editing.

For authorized issue work, follow [Author delivery issues](#author-delivery-issues), the [implementation template](../../.github/ISSUE_TEMPLATE/implementation.md) and [Definition of Done](definition-of-done.md). Issues own task tracking. Do not add delivery inventories, progress logs or reconciliation reports to developer guides or skills. Historical issue bodies are not rewritten merely because a documentation path moved.

<a id="author-delivery-issues"></a>

## Author delivery issues

An issue describes a stable delivery outcome, not an inventory of today's code. For example, “Reject Alice's expired browser cookie without trying her CLI token” tells a new engineer what to deliver. “Wire authentication and qualify the boundary” does not.

Choose the smallest coherent delivery scope and one of these formats:

| Format | Required contents |
| --- | --- |
| Implementation | Outcome through an example, concrete work, observable acceptance examples, boundaries/owning issues, focused reading and behavioral verification. |
| Parent | Outcome, actual native child map, exclusions and completion boundary. Keep implementation instructions and acceptance evidence in the children. Use the existing `epic` label. |
| Specification | Concrete unanswered questions, accepted constraints, outputs needing approval, affected consumers and review examples. Link the owning pending-decision analysis rather than copying it. |
| Qualification | Behavior to demonstrate, tested artifacts/environment/inputs, injected failures, required evidence and limitations. A planned test is not a passing result. |
| Deferred Studio | Intended UI behavior, delivered backend dependencies and explicit exclusion from v1. Do not invent future backend contracts. |

Use `type:implementation`, `type:specification` or `type:qualification` on open leaves. Apply `needs-decision` only when an unresolved answer prevents that ticket's implementation. Missing qualification evidence alone does not forbid evidence-gathering tests.

Before writing, compare the delivery scope with the owning skill workflow, exact contracts and accepted ADRs. The repository owns behavior. Issues own delivery and evidence. Follow explicit supersession, preserve unresolved choices and surface genuine contradictions before publishing affected requirements. Do not infer new permissions, endpoints or provider guarantees. Keep useful unique requirements visible as explicit questions if their authority is unclear.

Give a junior engineer a short path to the relevant explanation. Link exact sections instead of copying field catalogues, global conventions or the same workflow into several issue sections. Include an exact value only when the acceptance example needs it. For accepted unpublished guidance, state the exact repository path and its pending publication. Link a real PR or published revision when available. Never link `main` to missing or materially older content as if it contained the accepted update.

Reuse existing issues before creating a child. Use native parents for decomposition and native blockers for actual prerequisite capabilities, using GitHub's database issue IDs when an API requires them. Avoid blanket epic blockers where a particular child supplies the capability. Keep the graph acyclic and ensure v1 has no dependency on deferred Studio. Do not duplicate those relationships with manually maintained Ready/Blocked fields.

Update an issue when delivery scope, acceptance, an authoritative reading route, a prerequisite capability or a genuine decision changes. Code reorganization alone does not require a new starting-point inventory. Record implementation progress through completed delivery tasks, linked PRs and scoped evidence. Preserve comments and closed historical scope/results. Add only necessary navigation or a clearly separated current clarification to closed records.

Keep newly described work open while implementation is unmerged or required acceptance evidence is missing. A local adapter, an open PR or a successful ordinary path does not establish complete production integration. Distinguish source inspection, checks personally run, reported results and pending release gates. Qualification evidence should identify the tested artifacts, failures and limits.

For authorized bulk changes, snapshot bodies, comments, metadata and relationships outside the repository. Prepare coverage and the complete graph before publishing. Recheck current bodies/update times before each edit, preserve intervening work, journal actual created IDs and read back mutations. After an uncertain create, locate the issue before retrying. Verify states, milestones, labels, parents, dependencies and scope after application. Do not create repetitive migration comments or a permanent parallel backlog.

<a id="preserve-status-and-explain-evidence"></a>

## Preserve status and explain evidence

Use these distinctions explicitly:

- **Accepted design:** the intended behavior has been chosen. It may still need code and tests.
- **Proposed implementation detail:** an example table, column, selector, endpoint, or mechanism still needs implementation review. A proposed SQL map does not become a migration merely because it is detailed.
- **Implemented:** inspected code provides the named behavior. Link the files and explain the limit of that statement.
- **Verified:** a named check was actually run, with its relevant result and scope. Distinguish checks run by the author from reports supplied by someone else.
- **Deferred:** deliberately outside the current delivery scope.
- **Historical evidence or alternative:** useful context, not the current rule. Preserve its date, assumptions, and limitations.

Keep estimates and external observations in context. An illustrative workload, price, vendor capability, or timing goal is not a current guarantee. Before implementing a dependency on an external capability, check current primary documentation. Distinguish that new check from the original observation.

If sources disagree, identify the passages and explain why the difference matters. Follow an explicit superseding decision if one exists. Otherwise record the unresolved question instead of choosing a new policy during editing.

<a id="check-coverage-and-references"></a>

## Check coverage and references

Before a broad rewrite, capture current working-tree files and hashes outside the repository. Compare the rewrite with that baseline and preserve intervening edits. Every current requirement must remain in an active document. The temporary copy supports review, but is not a reading destination. Do not recreate an archive, migration map, or documentation framework.

Check files, heading links, explicit anchors, ADR IDs, plain-text paths, diagrams, and skill instructions. If a heading moves, repair incoming links from ADRs, architecture, README, guidance, and skills. Keep published HTTP problem fragments and exact contract wording stable. A link must reach the relevant explanation, not merely an existing nearby heading.

Walk through document replacement, index reuse, stale automatic publication, evaluation history, application-key authorization, lost-response recovery, and secure restoration. Each route must explain its normal flow and failure boundary without requiring ADR-first reading.

Inspect source before describing behavior as implemented or presenting copyable examples. Say which checks were run, which facts came from source inspection, and which results were developer-reported. Run Prettier on changed Markdown and `git diff --check`. Editorial work does not require application suites or generated contracts.

Preserve [AGENTS.md](../../AGENTS.md), its TDD and read-only safeguards, and [web directory guidance](../../apps/web/AGENTS.md). Documentation maintenance does not authorize code changes, paid calls, migrations, commits, or publishing.

<a id="unavailable-historical-material"></a>

## Unavailable historical material

Four earlier sources remain unavailable: the external client-tooling feasibility report, `docs/reviews/v1-architecture-review.md`, `docs/reviews/onboarding-reference.md` and `docs/development/repository-skills-plan.md`. No report or test evidence has been reconstructed. [ADR-0055](../adr/ADR-0055-deliver-cli-first-v1-through-openapi-generated-clients.md) supplies the CLI-first generated-client direction. [ADR-0088](../adr/ADR-0088-use-a-pinned-patched-generator-for-the-rust-sdk.md) subsequently selects its Rust generator implementation. Current first-use and qualification references preserve only the requirements actually available. Flexible first-answer timing is not a measured result.

## Choose the maintenance task

For writing, routing, examples and evaluation, follow [Skill authoring](guides/skill-authoring.md). For pending decisions, explicit approval and repository-wide reconciliation, follow [Architecture decisions](guides/architecture-decisions.md). These are mandatory procedures for their affected work, not a requirement to load both for every correction.
