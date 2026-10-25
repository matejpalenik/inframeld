# Write and maintain focused skills

Alice changes a service and notices that its worked example is stale. Correcting that example should help the next engineer without requiring every future task to read another manual. This guide governs writing and maintaining skills within the developer's confirmed scope.

- For document shape, use [workflow versus contract](#choose-a-workflow-or-contract-view).
- For a possible improvement discovered during ordinary work, use [handoff offers](#offer-and-maintain-skill-updates).
- For substantial rewrites, use [coverage](#preserve-coverage-during-a-rewrite) and [fresh-context checks](#evaluate-in-fresh-contexts).
- For approving an architectural choice, use [decision finalization](architecture-decisions.md), rather than accepting it through an editorial correction.

<a id="writing-pattern"></a>

## Writing pattern

Use the [grant workflow](../../../.agents/skills/inframeld-access-models/references/grant-administration.md) as a focused writing example. A topic guide should explain how the area works before presenting its detailed operating rules:

1. Briefly explain the reader's problem, prerequisites, reading route, and design status.
2. Link practical reader questions to their answers in a contents table.
3. Introduce concepts through a small example, then give them their technical names.
4. Explain which domain owns each responsibility. Use a diagram only where it helps.
5. Follow one successful operation, then show what changes when it fails, repeats, or competes with another change.
6. Explain why important records and transaction boundaries exist. Link implemented fields to their code or migrations and logical relationships to their owning record reference.
7. Give maintainers a compact table of scenarios and expected results.
8. Link owning decisions and references, and identify deferred work and tests still needed.

Adapt this pattern to the document. Pagination needs a short contract and example, not eight padded chapters. Logical record references need clear relationships and links to exact implemented constraints. HTTP references need precise response and implementation details.

Use short, connected paragraphs and familiar words. Keep exact code names, but explain what they mean before using them heavily. Prefer “save the change and its audit event together” to “commit the mutation and transactional audit atomically.” Introduce a term such as transaction when it helps the reader understand the mechanism.

Use the shared [resource-naming vocabulary](../../../.agents/skills/inframeld-architecture/references/resource-names-and-identity.md#resource-naming): **name** is the exact command/configuration selector, **display name** is the presentation label, and **ID** is the permanent identity. Screen columns should say `NAME` and `DISPLAY NAME`. Distinguish them in prompts and rename examples too. Do not use display names as implicit references. Preserve exact third-party symbols and existing code/database/wire field names when documenting them, and explain legacy mappings rather than silently renaming them or implying a migration. This terminology does not turn every internal record into a user-named resource.

Use Alice, SupportBot, Support, Test, and Production consistently, with each example's assumptions stated. Explain what diagram arrows mean and whether boxes are parts of the backend or separate services. Tables work well for comparisons and exact rules. Avoid semicolons in prose.

Give each rule one owning document. Remove duplicated explanations and obsolete comparisons, while keeping warnings next to the operation they constrain. Keep dated historical evidence clearly separate from current instructions. Preserve limits, exceptions, calculations, open questions and untested assumptions. If detail belongs elsewhere, move it to an active reference and link it. A shorter document is not better if it loses the reason a safeguard exists.

State the rule directly rather than citing shorthand from a design workshop. For example, explain which operations an application account may perform and which permissions it needs. Link the owning reference with descriptive text. A reader should not need a retired discussion document to decode a decision number.

Introduce precise technical terms when they are useful. For example, "save and validate the operation before starting background work" explains admission. Prefer "check current permission before saving" to "revalidate mutation authority at commit" when the distinction does not require the more technical wording. Separate a rule, its reason and its failure behavior instead of packing them into one sentence.

## Choose a workflow or contract view

A workflow teaches what happens. Start with the situation and owner, explain necessary concepts, then follow the ordinary sequence. Consolidate failures, retry and changed-state outcomes. End with implementation status and precise conditional routes. Keep one sources section.

A contract answers an exact field or rule question. State its owner and status first. For an implemented shape, link its defining code, schema or migration and show a small contextual example. Do not maintain another full declaration. For an unimplemented transport shape, use clearly labelled Python-oriented design blocks with exact wire names, complete alternatives and short local comments. `TypedDict`, `Literal`, `NotRequired` and comments explain a design. They perform no runtime validation and do not approve a pending choice. Existing design-schema views remain subordinate to that schema.

Show valid examples and relevant invalid cases. Explain strict parsing, bounds, cross-field relationships, current authority and transactional checks outside the types where necessary. A field annotation cannot establish current Project membership or trusted provider completion. Never invent an unknown field, default, endpoint, enum or service signature to make an example look complete.

Keep architecture, workflows, contracts, worked implementation examples and pending analysis distinct. Link each directly from the skill under its reading condition. Existing broader references remain useful explanations, not empty redirect pages. Aim for 700–1,800 prose words per focused reference, with longer complete code and complex protocols where justified. Preserve requirements rather than meeting a word target.

A summary must preserve its relevant conditions or link to the precise owner. For example, admitting B2 does not select R2 automatically. Check summaries, scenarios and diagrams against the same authoritative rule during every substantial rewrite.

## Offer and maintain skill updates

1. **Identify durable improvements.** At a meaningful handoff, consider accepted decisions, confirmed conventions, inspected changes, stale examples and demonstrated routing failures. Offer only a real guidance improvement. Routine work and documented rules need no offer.
2. **Check evidence and ownership.** Compare owning references, decisions and inspected code. Distinguish design, implementation and verification. Surface conflicts and include necessary canonical-source changes. Link implementation only when its files exist.
3. **Offer once with concrete scope.** Batch related changes, naming the skill, reason, evidence, exact files/sections and intended edits. Raise a blocking contradiction earlier. Respect decline or deferral unless material evidence changes. Complete explicitly approved edits. Otherwise obtain file-specific confirmation under root guidance.
4. **Choose the smallest home.** Revise the existing owner. Keep discovery and essential safeguards in `SKILL.md`, conditional explanations and substantial examples in directly linked references. Add scripts, assets or another skill only for a distinct reusable need.
5. **Preserve knowledge and structure.** Merge superseded duplication while preserving requirements, exceptions and rationale. Use concrete explanations. Keep one active skill body and exclude task logs, speculative instructions and copied manuals.
6. **Validate affected changes.** Check frontmatter, links, routing and source-backed snippets. Changed activation or substantial workflows require representative positive/negative trials. Report checks actually run and unavailable evaluations. Apply the detailed checks below when their scope matches.

<a id="skill-reading-routes"></a>

## Skill reading routes

Keep one active `SKILL.md` for each of the nine capabilities below under `.agents/skills/`. Architecture is for orientation and journeys spanning owners, not a prerequisite for every domain question. Coding Standards loads for code work in every repository language. It teaches backend Python conventions and routes other languages to their existing guidance. Application Contracts covers application orchestration and transport. The former combined Pipelines/Releases skill has been replaced by the separate Pipelines and Releases names, without a compatibility body.

| Skill | Detailed owner |
| --- | --- |
| [Architecture](../../../.agents/skills/inframeld-architecture/SKILL.md) | [Focused references](../../../.agents/skills/inframeld-architecture/references/module-map.md) and that skill’s direct workflow routes. |
| [Access Models](../../../.agents/skills/inframeld-access-models/SKILL.md) | [Focused references](../../../.agents/skills/inframeld-access-models/references/architecture.md) and that skill’s direct workflow routes. |
| [Knowledge](../../../.agents/skills/inframeld-knowledge/SKILL.md) | [Focused references](../../../.agents/skills/inframeld-knowledge/references/architecture.md) and that skill’s direct workflow routes. |
| [Indexing](../../../.agents/skills/inframeld-indexing/SKILL.md) | [Focused references](../../../.agents/skills/inframeld-indexing/references/architecture.md) and that skill’s direct workflow routes. |
| [Pipelines](../../../.agents/skills/inframeld-pipelines/SKILL.md) | [Focused references](../../../.agents/skills/inframeld-pipelines/references/architecture.md) and that skill’s direct workflow routes. |
| [Evaluation](../../../.agents/skills/inframeld-evaluation/SKILL.md) | [Focused references](../../../.agents/skills/inframeld-evaluation/references/architecture.md) and that skill’s direct workflow routes. |
| [Releases](../../../.agents/skills/inframeld-releases/SKILL.md) | [Focused references](../../../.agents/skills/inframeld-releases/references/architecture.md) and that skill’s direct workflow routes. |
| [Application Contracts](../../../.agents/skills/inframeld-application-contracts/SKILL.md) | [Focused references](../../../.agents/skills/inframeld-application-contracts/references/components-and-services.md) and that skill’s direct workflow routes. |
| [Coding Standards](../../../.agents/skills/inframeld-coding-standards/SKILL.md) | [Focused references](../../../.agents/skills/inframeld-coding-standards/references/component-roles-and-imports.md) and that skill’s direct workflow routes. |

Read the selected skill and only the references relevant to the current question. Before any repository code planning, suggestions, additions, changes or reviews, including tests and code snippets, root AGENTS.md requires Coding Standards. Apply its Python references only to backend Python. Other languages retain their directory and language guidance. Backend services require its service example, and affected aggregates/repositories require their specific example. Services and execution boundaries also require the owning Application Contracts workflow. Moving detailed conventions out of root guidance does not make them optional. Domain-only explanations need no coding-standard load. Loading any skill grants no editing or external-action authority.

<a id="write-a-skill-for-both-people-and-agents"></a>

### Write a skill for both people and agents

Frontmatter describes the actual capability and activation conditions. The body explains purpose, a small working model, essential constraints, a method for explaining/reviewing, and direct conditional reading routes. Aim for roughly 400–800 words per entry point, excluding diagrams. This is an editorial target, not permission to discard information.

References should explain a problem through Alice or SupportBot, introduce concepts and owners, follow a normal flow, then cover failures/retries/changed state, implementation limits and supporting sources. A junior engineer should understand the ordinary workflow without reading ADRs first. Explain specialized terms where introduced. Avoid dense paragraphs, unexplained issue shorthand and a catch-all edge-case dump.

Keep one-level reference navigation and direct source citations. Focused references own behavior and logical records. Code and migrations own implemented shapes, and ADRs own rationale. Avoid copied manuals or competing specifications. Keep historical evidence, explicit supersession and pending qualification distinguishable. No scripts, assets, interface metadata or placeholder folders are needed without a concrete workflow benefit.

Architecture diagrams distinguish processes, logical owners and interaction arrows from code dependencies. The glossary explains terms and commonly confused meanings without duplicating exact record schemas.

<a id="maintain-architecture-views"></a>

### Maintain architecture views

Use [C4](https://c4model.com/diagrams) for progressively closer structural views and [arc42 runtime guidance](https://docs.arc42.org/section-6/) for selected interactions and failures. These guide how we explain architecture. They do not add product requirements or demand every possible diagram.

Use system context for users and external systems, runtime topology for processes/stores, the module map for ownership, and each domain's `references/architecture.md` for internal responsibilities and selected workflows. Keep every reference directly linked from its skill with an explicit loading condition. For domain-specific backend component design, generation or structural review, read the owning architecture and relevant workflow. Shared components use Application Contracts. Behaviour-only questions need no automatic architecture prerequisite.

Start each module view with a concrete problem. Explain ownership, main parts, normal flow, failures, data/execution boundaries, implementation status and pending decisions in that order. Define unfamiliar terms where they matter. Keep diagrams titled, readable and scoped. Label arrows and explain whether they show calls, information, state transitions or source dependencies. Runtime boxes, code roles and domain concepts are different views. A named concept does not imply a class, aggregate, table or service.

Focused owning references specify accepted behaviour, logical records and qualifications. Keep a brief unresolved-question notice in the owning reference and link its focused decision analysis from the existing skill. That reference explains evidence, viable options, a non-binding recommendation, trade-offs and the work that needs a decision. Keep pending analysis distinct from the accepted specification and link its one owning discussion. Link it from the module view too. Recording a proposal does not accept it or reopen a settled decision. Use [the just-in-time process](architecture-decisions.md#just-in-time-architecture-decisions) for later finalization.

When a component, interface or workflow changes, recheck its architecture view, relevant diagrams and inspected paths together with the owning reference. Preserve distinctions among accepted design, inspected implementation, recorded verification and production qualification. Render every new or changed Mermaid diagram and inspect the result. Use read-only trials for explanation, failure/review and unrelated requests, plus a case that encounters an unaccepted proposal. Report unavailable runtime or visual checks explicitly.

<a id="maintain-worked-code-examples"></a>

### Maintain worked code examples

Coding Standards keeps substantial examples in its seven focused references. Begin with a concrete component task, explain its owner/layer/role and placement, then show contextual code, normal flow, relevant failure and source limits. A junior reader should understand why that component exists without opening an ADR first.

Label complete inspected modules, selected teaching excerpts and illustrative code accurately. Identify the exact source or proposed destination and whether a proposed snippet is a complete new file, replacement or insertion. Include needed imports and context. For a selected test, identify its source fixtures and show their declarations when needed to understand the behavior. Do not use unexplained ellipses or omit safety checks from an example presented as a complete use case.

When an implementation changes, recheck the corresponding excerpt and its explanation against the owning reference. Keep one full service example rather than copying it into every reference. Link neighboring examples by the decision they help make. Preserve valid function, primitive, projection and instance-service exceptions. Source fidelity does not make incidental code choices universal rules.

<a id="preserve-coverage-during-a-rewrite"></a>

### Preserve coverage during a rewrite

Snapshot current working-tree files and hashes outside the repository before writing. Inventory individual decisions, requirements, examples, exceptions, symbols, limits, sources and qualification statements. Record each item's final location and any identical statements merged. Check meaning and applicability, not just shared words. Retained canonical content is an acceptable destination only when the relevant rule is identified and remains reachable.

Do not leave unique context solely in a temporary ledger or Git history. Do not create a permanent migration map or archive. Preserve intervening edits and resolve only explicit supersession. Report unresolved source disagreements without inventing policy. Repair active skill names and routes, without retaining delivery reports or task histories in current developer documentation. Preserve architectural rationale and explicit supersession in ADRs.

<a id="evaluate-in-fresh-contexts"></a>

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
