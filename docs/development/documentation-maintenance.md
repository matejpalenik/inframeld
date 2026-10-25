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
| Agent discovery and task method | Concise `SKILL.md` metadata/body with direct conditional links. |
| Development and operator procedures | Human guides and runbooks, with current implementation limits explicit. |

Give each rule one detailed owner. A human guide may explain its purpose briefly, then link to that owner. Avoid parallel specifications, large required reading stacks and copies of exact code declarations. Existing code may intentionally lag accepted design. Label that gap rather than changing the target during editing.

For authorized issue work, retain the [implementation template](../../.github/ISSUE_TEMPLATE/implementation.md) and [Definition of Done](definition-of-done.md). Issues own task tracking. Do not add delivery inventories, progress logs or reconciliation reports to developer guides or skills. Historical issue bodies are not rewritten merely because a documentation path moved.

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

Four earlier sources remain unavailable: the external client-tooling feasibility report, `docs/reviews/v1-architecture-review.md`, `docs/reviews/onboarding-reference.md` and `docs/development/repository-skills-plan.md`. No report or test evidence has been reconstructed. ADR-0055 supplies the current generator-neutral CLI direction. Current first-use and qualification references preserve only the requirements actually available. Flexible first-answer timing is not a measured result.

## Choose the maintenance task

For writing, routing, examples and evaluation, follow [Skill authoring](guides/skill-authoring.md). For pending decisions, explicit approval and repository-wide reconciliation, follow [Architecture decisions](guides/architecture-decisions.md). These are mandatory procedures for their affected work, not a requirement to load both for every correction.
