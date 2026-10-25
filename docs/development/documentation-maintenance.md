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

For authorized backlog maintenance, use [the implementation template](../../.github/ISSUE_TEMPLATE/implementation.md), [Definition of Done](definition-of-done.md) and [CLI delivery traceability](cli-delivery-plan.md). One ticket owns one coherent capability or transition. Epics map children; qualification issues specify evidence rather than claim to implement runtime behavior. Record a real architecture SHA and disclose any uncommitted overlay. Keep native parents/dependencies and issue-body tables aligned, preserve completion history and isolate unresolved contract design before labelling implementation ready.

| Reader’s question | Owning document | What to put there |
| --- | --- | --- |
| What does this application do, and how do its parts work together? | [Architecture introduction](../ARCHITECTURE.md) | A connected explanation, vocabulary, a worked journey, and links to deeper material. |
| Why did we choose this approach? | [Architecture decision records](../adr/README.md) | One architectural choice, its context, considered options, outcome, consequences, and status. |
| How must this part of the product behave? | The relevant [topic guide](../ARCHITECTURE.md#reading-paths) | Current rules, procedures, examples, failures, limitations, and qualification requirements. |
| Which records exist, and how do they relate? | [data-model.md](data-model.md) | Record identities, ownership, fields, relationships, lifecycle states, constraints, and whether physical tables are proposed or implemented. |
| What has actually been implemented or tested? | Existing code, tests, and a dated evidence section or implementation reference | Concrete paths and what the check established. A design document is not test evidence. |
| What should an assistant read and preserve for this task? | One of the nine [repository skills](#skill-reading-routes) | Essential boundaries and precise reading routes. Skills must not become independent specifications. |

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

Use the shared [resource-naming vocabulary](data-model.md#resource-naming): **name** is the exact command/configuration selector, **display name** is the presentation label, and **ID** is the permanent identity. Screen columns should say `NAME` and `DISPLAY NAME`; distinguish them in prompts and rename examples too. Do not use display names as implicit references. Preserve exact third-party symbols and existing code/database/wire field names when documenting them, and explain legacy mappings rather than silently renaming them or implying a migration. This terminology does not turn every internal record into a user-named resource.

Use Alice, SupportBot, Support, Test, and Production consistently, with each example's assumptions stated. Explain what diagram arrows mean and whether boxes are parts of the backend or separate services. Tables work well for comparisons and exact rules. Avoid semicolons in prose.

Give each rule one owning document. Remove duplicated explanations and obsolete comparisons, while keeping warnings next to the operation they constrain. Keep dated historical evidence clearly separate from current instructions. Preserve limits, exceptions, calculations, open questions and untested assumptions. If detail belongs elsewhere, move it to an active reference and link it. A shorter document is not better if it loses the reason a safeguard exists.

State the rule directly rather than citing shorthand from a design workshop. For example, explain which operations an application account may perform and which permissions it needs. Link the owning guide with descriptive text. A reader should not need a retired discussion document to decode a decision number.

Introduce precise technical terms when they are useful. For example, "save and validate the operation before starting background work" explains admission. Prefer "check current permission before saving" to "revalidate mutation authority at commit" when the distinction does not require the more technical wording. Separate a rule, its reason and its failure behavior instead of packing them into one sentence.

## Skill reading routes

Keep one active `SKILL.md` for each of the nine capabilities below under `.agents/skills/`. Architecture is for orientation and journeys spanning owners, not a prerequisite for every domain question. Coding Standards loads for code work in every repository language. It teaches backend Python conventions and routes other languages to their existing guidance. Application Contracts covers application orchestration and transport. The former combined Pipelines/Releases skill has been replaced by the separate Pipelines and Releases names, without a compatibility body.

| Skill | Read for current behavior | Read for records |
| --- | --- | --- |
| [Architecture](../../.agents/skills/inframeld-architecture/SKILL.md) | [Product introduction](../ARCHITECTURE.md), [application structure](application-structure.md), [deployment](deployment.md), [onboarding](onboarding.md) | [Data model](data-model.md) |
| [Access](../../.agents/skills/inframeld-access-models/SKILL.md) | [Access control](access-control.md), [Access contracts](access-contracts.md), [model connections](model-connections.md) | [Access](data-model.md#access), [connections and credentials](data-model.md#shared-supporting-records) |
| [Knowledge](../../.agents/skills/inframeld-knowledge/SKILL.md) | [Knowledge lifecycle](knowledge-lifecycle.md), [ingestion security](ingestion-security.md), [retention/deletion](retention-and-deletion.md), [onboarding](onboarding.md) | [Knowledge](data-model.md#knowledge) |
| [Indexing](../../.agents/skills/inframeld-indexing/SKILL.md) | [Indexing](indexing.md), [ingestion security](ingestion-security.md), [model connections](model-connections.md) | [Indexing](data-model.md#indexing) |
| [Pipelines](../../.agents/skills/inframeld-pipelines/SKILL.md) | [Pipelines and Releases](pipelines-and-releases.md), [feedback](answer-feedback.md), [observability](observability.md) | [Pipelines](data-model.md#pipelines) |
| [Evaluation](../../.agents/skills/inframeld-evaluation/SKILL.md) | [Evaluation](evaluation.md), relevant [model](model-connections.md) and [access](access-control.md) boundaries | [Evaluation](data-model.md#evaluation) |
| [Releases](../../.agents/skills/inframeld-releases/SKILL.md) | [Pipelines and Releases](pipelines-and-releases.md), [onboarding](onboarding.md), [Access](access-control.md) | [Releases](data-model.md#releases) |
| [Coding Standards](../../.agents/skills/inframeld-coding-standards/SKILL.md) | [Component conventions](application-structure.md#component-conventions), [static utilities](application-structure.md#static-utilities-and-mappers), [service-writing guide](application-structure.md#service-writing-guide) | [Existing typed values and contracts](application-structure.md#component-conventions) |
| [Application Contracts](../../.agents/skills/inframeld-application-contracts/SKILL.md) | [Application structure](application-structure.md), [API contracts](api-contracts.md), [jobs/idempotency](jobs-and-idempotency.md), [MCP](mcp.md), error and pagination references | [Supporting records](data-model.md#shared-supporting-records) |

Read the selected skill and only the references relevant to the current question. Before any repository code planning, suggestions, additions, changes or reviews, including tests and code snippets, root AGENTS.md requires Coding Standards. Apply its Python references only to backend Python. Other languages retain their directory and language guidance. Backend services require its service example, and affected aggregates/repositories require their specific example. Services and execution boundaries also require the owning Application Contracts workflow. Moving detailed conventions out of root guidance does not make them optional. Domain-only explanations need no coding-standard load. Loading any skill grants no editing or external-action authority.

### Write a skill for both people and agents

Frontmatter describes the actual capability and activation conditions. The body explains purpose, a small working model, essential constraints, a method for explaining/reviewing, and direct conditional reading routes. Aim for roughly 400–800 words per entry point, excluding diagrams. This is an editorial target, not permission to discard information.

References should explain a problem through Alice or SupportBot, introduce concepts and owners, follow a normal flow, then cover failures/retries/changed state, implementation limits and supporting sources. A junior engineer should understand the ordinary workflow without reading ADRs first. Explain specialized terms where introduced. Avoid dense paragraphs, unexplained issue shorthand and a catch-all edge-case dump.

Keep one-level reference navigation and direct source citations. Canonical guides own behavior, the data model owns records and ADRs own rationale. Skill references teach those sources without becoming independent specifications or copying whole manuals. Keep historical evidence, explicit supersession and pending qualification distinguishable. No scripts, assets, interface metadata or placeholder folders are needed without a concrete workflow benefit.

Architecture diagrams distinguish processes, logical owners and interaction arrows from code dependencies. The glossary explains terms and commonly confused meanings without duplicating exact record schemas.

### Maintain architecture views

Use [C4](https://c4model.com/diagrams) for progressively closer structural views and [arc42 runtime guidance](https://docs.arc42.org/section-6/) for selected interactions and failures. These guide how we explain architecture. They do not add product requirements or demand every possible diagram.

Use system context for users and external systems, runtime topology for processes/stores, the module map for ownership, and each domain's `references/architecture.md` for internal responsibilities and selected workflows. Keep every reference directly linked from its skill with an explicit loading condition. For domain-specific backend component design, generation or structural review, read the owning architecture and relevant workflow. Shared components use Application Contracts. Behaviour-only questions need no automatic architecture prerequisite.

Start each module view with a concrete problem. Explain ownership, main parts, normal flow, failures, data/execution boundaries, implementation status and pending decisions in that order. Define unfamiliar terms where they matter. Keep diagrams titled, readable and scoped. Label arrows and explain whether they show calls, information, state transitions or source dependencies. Runtime boxes, code roles and domain concepts are different views. A named concept does not imply a class, aggregate, table or service.

Canonical guides own accepted behaviour, records and qualifications. Add unresolved architecture proposals in clearly marked sections of the owning guide, with evidence of the gap, viable options, a recommendation, trade-offs and the implementation dependent on acceptance. Link them briefly from the module view. Recording a proposal does not accept it. Do not silently fill a gap or reopen a settled decision. Later acceptance follows the existing ADR process.

When a component, interface or workflow changes, recheck its architecture view, relevant diagrams and inspected paths together with the owning guide. Preserve distinctions among accepted design, inspected implementation, recorded verification and production qualification. Render every new or changed Mermaid diagram and inspect the result. Use read-only trials for explanation, failure/review and unrelated requests, plus a case that encounters an unaccepted proposal. Report unavailable runtime or visual checks explicitly.

### Maintain worked code examples

Coding Standards keeps substantial examples in its seven focused references. Begin with a concrete component task, explain its owner/layer/role and placement, then show contextual code, normal flow, relevant failure and source limits. A junior reader should understand why that component exists without opening an ADR first.

Label complete inspected modules, selected teaching excerpts and illustrative code accurately. Identify the exact source or proposed destination and whether a proposed snippet is a complete new file, replacement or insertion. Include needed imports and context. For a selected test, identify its source fixtures and show their declarations when needed to understand the behavior. Do not use unexplained ellipses or omit safety checks from an example presented as a complete use case.

When an implementation changes, recheck the corresponding excerpt and its explanation against the owning guide. Keep one full service example rather than copying it into every reference. Link neighboring examples by the decision they help make. Preserve valid function, primitive, projection and instance-service exceptions. Source fidelity does not make incidental code choices universal rules.

### Preserve coverage during a rewrite

Snapshot current working-tree files and hashes outside the repository before writing. Inventory individual decisions, requirements, examples, exceptions, symbols, limits, sources and qualification statements. Record each item's final location and any identical statements merged. Check meaning and applicability, not just shared words. Retained canonical content is an acceptable destination only when the relevant rule is identified and remains reachable.

Do not leave unique context solely in a temporary ledger or Git history. Do not create a permanent migration map or archive. Preserve intervening edits and resolve only explicit supersession. Report unresolved source disagreements without inventing policy. Repair active skill names and routes, while retaining historical file identities and dates in old reports with current navigation alongside them.

### Evaluate in fresh contexts

After substantive changes, validate frontmatter and links, then use fresh conversations for explanation, review/failure and unrelated requests for each skill. Inspect which files are loaded as well as answer quality. Narrow questions should not require every reference or Architecture by default.

For coding-standard changes, include isolated generation and review trials. Cover reusable utilities, typed values and boundary conversion, static mappers, explicit protocol implementations, and legitimate function/instance-service exceptions. Trial agents return proposed code without repository edits. Materialize artifacts only in temporary workspaces and check meaningful behavior, strict typing and applicable lint using existing tools. Seeded review cases must include both violations and valid exceptions. For worked service/repository examples, also trial complete service construction, domain ownership, scoped loading, replay/failure behavior and repository lifetime. Check all-language routing with frontend additions/reviews and Rust review, plus behavior-only and documentation-only controls. Inspect actual loading traces and verify that non-Python answers do not inherit Python conventions.

Keep trial prompts independent of the expected answers. Record actual loading traces and outcomes. Source walkthroughs do not establish automatic activation. Report unavailable runtime trials honestly, without replacing them with inferred success. These evaluations add no repository enforcement tests and contact no product model endpoints.

| Walkthrough | Expected understanding |
| --- | --- |
| Handbook upload to Production | Separate admission, verified preparation, ready build and publication. |
| Browser, human CLI and bot key | Same human across browser/CLI, separate application identity, current authority and no fallback. |
| Consent/refresh across recovery | Version invalidation, independent blocks, provider uncertainty and unfinished production qualification. |
| Grant retry after lost response or revoked authority | Current authorization, checked scope, original operation, atomic audit and correct rollback owner. |
| Replace B1 and later erase it | Immutable revisions, unchanged A1 reuse, blocked late publication and historical unavailability. |
| A vector shard times out | Frozen-byte storage retry, no inferred paid retry, incomplete materialization remains unready. |
| Automatic → Manual → Automatic during Build | Old publication authority never revives. |
| Edited cases or missing passage coordinates | Frozen inputs, fresh comparison, explicit unscorable counts and protected evidence. |
| Connection/import/tracing/feedback changes | Exact authority, no identity fallback, partial effects, current access and original attribution. |
| Suggested backend component | Owner/layer/role, typed values/ORM, explicit protocol implementation and behavioral testing. |
| Unrelated styling, CI or generic authentication | No Inframeld domain policy imposed on the unrelated task. |

Record walkthrough outcomes and corrections in the temporary review material or handoff. Do not mislabel these editorial checks as application-suite execution, model-quality calibration or runtime qualification.

## Check coverage and references

Before a broad rewrite, capture current working-tree files and hashes outside the repository. Compare the rewrite with that baseline and preserve intervening edits. Every current requirement must remain in an active document. The temporary copy supports review, but is not a reading destination. Do not recreate an archive, migration map, or documentation framework.

Check files, heading links, explicit anchors, ADR IDs, plain-text paths, diagrams, and skill instructions. If a heading moves, repair incoming links from ADRs, architecture, README, guidance, and skills. Keep published HTTP problem fragments and exact contract wording stable. A link must reach the relevant explanation, not merely an existing nearby heading.

Walk through document replacement, index reuse, stale automatic publication, evaluation history, application-key authorization, lost-response recovery, and secure restoration. Each route must explain its normal flow and failure boundary without requiring ADR-first reading.

Inspect source before describing behavior as implemented or presenting copyable examples. Say which checks were run, which facts came from source inspection, and which results were developer-reported. Run Prettier on changed Markdown and `git diff --check`. Editorial work does not require application suites or generated contracts.

Preserve [AGENTS.md](../../AGENTS.md), its TDD and read-only safeguards, and [web directory guidance](../../apps/web/AGENTS.md). Documentation maintenance does not authorize code changes, paid calls, migrations, commits, or publishing.

## Unavailable historical material

Four previously referenced documents were unavailable in the reviewed checkout and available Git history. The availability notes below identify the missing files and link to existing specifications. No missing report or test result has been reconstructed.

### Missing historical client review

The previously referenced external client-tooling feasibility report is unavailable and establishes no qualification evidence. [ADR-0055](../adr/ADR-0055-deliver-cli-first-v1-through-openapi-generated-clients.md) replaces the earlier tooling dependency with generator-neutral OpenAPI clients and CLI-first v1. See [API contracts](api-contracts.md) for current delivery requirements.

### Missing closing review

`docs/reviews/v1-architecture-review.md` is unavailable. The [decision index](../adr/README.md) and topic guides preserve the scope and qualification statements actually present in the available sources. This does not recover the closing review’s analysis or create a new review gate.

### Missing onboarding reference

`docs/reviews/onboarding-reference.md` is unavailable. The [onboarding guide](onboarding.md) retains the available first-use journey, private provisioning rules, retry behavior, and flexible timing goal. That goal is not evidence of a measured first-answer time.

### Missing skills plan

`docs/development/repository-skills-plan.md` is unavailable. [Skill reading routes](#skill-reading-routes) provides current maintenance guidance without claiming to recover that plan.
