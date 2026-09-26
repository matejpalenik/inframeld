# Maintaining Inframeld's architecture documentation

Use this guide when adding or rewriting documentation. A new maintainer should be able to find a current rule, understand it through an example, and follow a link to exact details without first reading the decision history.

> **Status:** this is repository writing and maintenance guidance. It does not approve new product behavior or establish implementation evidence.

## Contents

| Reader's question | Start here |
| --- | --- |
| Where should a rule live? | [Ownership](#where-information-belongs) |
| How do we record or supersede a choice? | [Decisions](#introduce-or-change-a-decision) |
| How do I distinguish design from code? | [Status and evidence](#preserve-status-and-explain-evidence) |
| How should a topic guide read? | [Writing pattern](#writing-pattern) |
| Which skills need updating? | [Skill routes](#skill-reading-routes) |
| What do I check before handoff? | [Review](#check-coverage-and-references) |
| Which historical sources are unavailable? | [Missing material](#unavailable-historical-material) |

## Where information belongs

| Reader’s question | Owning document | What to put there |
| --- | --- | --- |
| What does this application do, and how do its parts work together? | [Architecture introduction](../ARCHITECTURE.md) | A connected explanation, vocabulary, a worked journey, and links to deeper material. |
| Why did we choose this approach? | [Architecture decision records](../adr/README.md) | One architectural choice, its context, considered options, outcome, consequences, and status. |
| How must this part of the product behave? | The relevant [topic guide](../ARCHITECTURE.md#reading-paths) | Current rules, procedures, examples, failures, limitations, and qualification requirements. |
| Which records exist, and how do they relate? | [data-model.md](data-model.md) | Record identities, ownership, fields, relationships, lifecycle states, constraints, and whether physical tables are proposed or implemented. |
| What has actually been implemented or tested? | Existing code, tests, and a dated evidence section or implementation reference | Concrete paths and what the check established. A design document is not test evidence. |
| What should an assistant read and preserve for this task? | One of the six [repository skills](#skill-reading-routes) | Essential boundaries and precise reading routes. Skills must not become independent specifications. |

The [HTTP error guide](error-handling.md), [error maintainer reference](error-handling-reference.md), and [pagination guide](pagination.md) continue to own their established details. Link to them rather than reproducing their implementation instructions in the API guide.

For example, storing current permissions separately from audit history is an architectural decision. The Access guide explains what happens when Alice removes a permission. The data model defines the grant's unique key. Once implemented, a test can prove that removal and its audit event commit together. Link that test only when it exists.

## Introduce or change a decision

1. Check the [decision index](../adr/README.md) and the relevant guide. Find out whether the question is already decided, still proposed, or an implementation detail within an accepted choice.
2. For a new architectural choice, copy the [ADR template](../adr/template.md), allocate the next unused ID, and give it a specific title. Explain the problem and the actual options in language a new contributor can follow.
3. Record the status and the known decision date. If the original decision date was not recorded, use the ADR's writing date in the Date field and say in Context that the original date is unknown. Do not invent a rejected alternative, a benchmark result, or a historical date.
4. Keep the decision focused. If two choices can change independently, consider separate ADRs. Length is a reason to review the scope, not a word limit. Move schemas, procedures, extensive examples, and teaching material into their owning references.
5. When an accepted choice changes, create a new ADR that explicitly supersedes the old one. Update the old record’s status and links so readers can follow the history. Do not rewrite the old rationale to make the new choice look inevitable.
6. Update the current guide, affected data-model sections, index, architecture introduction where needed, and relevant skills together. Ordinary corrections and navigation improvements can update an existing ADR without pretending a new decision was made.

Keep assigned ADR IDs stable. Use the next unused ID in the index for a new choice. Reorganizing an explanation does not create a new architectural decision.

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

## Writing pattern

Use [Access control](access-control.md) as the writing example. A topic guide should explain how the area works before presenting its detailed operating rules:

1. Briefly explain the reader's problem, prerequisites, reading route, and design status.
2. Link practical reader questions to their answers in a contents table.
3. Introduce concepts through a small example, then give them their technical names.
4. Explain which domain owns each responsibility. Use a diagram only where it helps.
5. Follow one successful operation, then show what changes when it fails, repeats, or competes with another change.
6. Explain why important records and transaction boundaries exist. Link exact fields and constraints to the data model.
7. Give maintainers a compact table of scenarios and expected results.
8. Link owning decisions and references, and identify deferred work and tests still needed.

Adapt this pattern to the document. Pagination needs a short contract and example, not eight padded chapters. The data model needs domain navigation and exact constraints. HTTP references need precise response and implementation details.

Use short, connected paragraphs and familiar words. Keep exact code names, but explain what they mean before using them heavily. Prefer “save the change and its audit event together” to “commit the mutation and transactional audit atomically.” Introduce a term such as transaction when it helps the reader understand the mechanism.

Use Alice, SupportBot, Support, Test, and Production consistently, with each example's assumptions stated. Explain what diagram arrows mean and whether boxes are parts of the backend or separate services. Tables work well for comparisons and exact rules. Avoid semicolons in prose.

Give each rule one owning document. Remove repeated explanations, rewrite history, and obsolete comparisons, while keeping warnings next to the operation they constrain. Preserve limits, exceptions, calculations, open questions, and untested assumptions. If detail belongs elsewhere, move it to an active reference and link it. A shorter document is not better if it loses the reason a safeguard exists.

## Skill reading routes

Keep one active `SKILL.md` per domain under `.agents/skills/`. Preserve its frontmatter, discovery purpose, read-only default, and task boundaries. A small question should load the relevant guide section, not every guide in the repository.

| Skill | Read for current behavior | Read for records |
| --- | --- | --- |
| [Access Models](../../.agents/skills/inframeld-access-models/SKILL.md) | [Access control](access-control.md), [model connections](model-connections.md) | [Access](data-model.md#access), [connections and credentials](data-model.md#shared-supporting-records) |
| [Application Contracts](../../.agents/skills/inframeld-application-contracts/SKILL.md) | [Application structure](application-structure.md), [API contracts](api-contracts.md), [jobs and idempotency](jobs-and-idempotency.md), [MCP](mcp.md), HTTP error and pagination references | [Supporting records](data-model.md#shared-supporting-records) |
| [Knowledge](../../.agents/skills/inframeld-knowledge/SKILL.md) | [Knowledge lifecycle](knowledge-lifecycle.md), [ingestion security](ingestion-security.md), [retention and deletion](retention-and-deletion.md), [onboarding](onboarding.md) | [Knowledge](data-model.md#knowledge) |
| [Indexing](../../.agents/skills/inframeld-indexing/SKILL.md) | [Indexing](indexing.md), [ingestion security](ingestion-security.md), [model connections](model-connections.md) | [Indexing](data-model.md#indexing) |
| [Pipelines and Releases](../../.agents/skills/inframeld-pipelines-releases/SKILL.md) | [Pipelines and releases](pipelines-and-releases.md), [answer feedback](answer-feedback.md), [onboarding](onboarding.md) | [Pipelines](data-model.md#pipelines), [Releases](data-model.md#releases) |
| [Evaluation](../../.agents/skills/inframeld-evaluation/SKILL.md) | [Evaluation](evaluation.md), relevant [model](model-connections.md) and [access](access-control.md) boundaries | [Evaluation](data-model.md#evaluation) |

After a substantive skill change, check its frontmatter and links, then follow realistic questions through its reading routes. Skills keep essential warnings and task boundaries. Guides own the full explanation. Loading a skill does not authorize edits.

## Check coverage and references

Before a broad rewrite, capture current working-tree files and hashes outside the repository. Compare the rewrite with that baseline and preserve intervening edits. Every current requirement must remain in an active document. The temporary copy supports review, but is not a reading destination. Do not recreate an archive, migration map, or documentation framework.

Check files, heading links, explicit anchors, ADR IDs, plain-text paths, diagrams, and skill instructions. If a heading moves, repair incoming links from ADRs, architecture, README, guidance, and skills. Keep published HTTP problem fragments and exact contract wording stable. A link must reach the relevant explanation, not merely an existing nearby heading.

Walk through document replacement, index reuse, stale automatic publication, evaluation history, application-key authorization, lost-response recovery, and secure restoration. Each route must explain its normal flow and failure boundary without requiring ADR-first reading.

Inspect source before describing behavior as implemented or presenting copyable examples. Say which checks were run, which facts came from source inspection, and which results were developer-reported. Run Prettier on changed Markdown and `git diff --check`. Editorial work does not require application suites or generated contracts.

Preserve [AGENTS.md](../../AGENTS.md), its TDD and read-only safeguards, and [web directory guidance](../../apps/web/AGENTS.md). Documentation maintenance does not authorize code changes, paid calls, migrations, commits, or publishing.

## Unavailable historical material

Four previously referenced documents were unavailable in the reviewed checkout and available Git history. The availability notes below identify the missing files and link to existing specifications. No missing report or test result has been reconstructed.

### Missing SDK Kit review

`docs/reviews/sdk-kit-feasibility.md` is unavailable. The [API contract guide](api-contracts.md) retains the known delivery decision: backend work proceeds first, while external SDK Kit suitability blocks Studio. Studio uses the official generated TypeScript SDK. This does not prove generation or interoperability has passed.

### Missing closing review

`docs/reviews/v1-architecture-review.md` is unavailable. The [decision index](../adr/README.md) and topic guides preserve the scope and qualification statements actually present in the available sources. This does not recover the closing review’s analysis or create a new review gate.

### Missing onboarding reference

`docs/reviews/onboarding-reference.md` is unavailable. The [onboarding guide](onboarding.md) retains the available first-use journey, private provisioning rules, retry behavior, and flexible timing goal. That goal is not evidence of a measured first-answer time.

### Missing skills plan

`docs/development/repository-skills-plan.md` is unavailable. [Skill reading routes](#skill-reading-routes) provides current maintenance guidance without claiming to recover that plan.
