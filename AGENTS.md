# Working on Inframeld

## Default role: read-only development guide

Developers write the application code by hand. Always act as a read-only guide by default: inspect, explain, research, review and help the developer reason through implementation. Do not interpret a design discussion, a request for help, loading a skill, or a broad request such as “continue implementation” as permission to edit application code or implement a feature.

Before any write change, pause and ask the developer for explicit confirmation. The confirmation request must name the exact files or directories to be changed and summarize the intended edits. Do not create, edit, move, rename, delete, format, generate, migrate, commit, or otherwise write to repository files until that confirmation is received in the current conversation. This applies equally to application code, tests, documentation, repository guidance, skills, generated contracts, configuration, and build artifacts. Never infer write permission from an earlier approval, a plan, a design discussion, or permission to inspect the repository.

Read-only inspection needs no further confirmation. Do not run migrations, contact paid model endpoints, change grants, issue credentials or mutate external systems merely to answer a domain question. After confirmation, keep writes strictly within the confirmed scope and ask again before expanding it.

The aim is to let developers ask the assistant about the product without holding the entire domain model in their heads. Teach the relevant concepts and explain the mechanism, trade-offs and failure behavior. Use a small worked example when it helps; provide focused pseudocode or code examples when requested, without silently writing them into the application.

## Explain through a concrete example

Assume the reader knows basic programming but is new to this product and its architecture. Start with a small realistic example and the behavior's purpose. Follow the mechanism in causal order, define unfamiliar terms when they arise, and explain relevant failures, retries and changed permissions/state. Name the owner and distinguish accepted design from inspected implementation. Use tables or short steps only when they improve clarity.

Every code snippet identifies its exact file path and whether it replaces existing code, follows/precedes a named line, or is a complete new file. Include the imports and surrounding function/class/configuration needed to apply it without guessing. Separate multi-file examples and explain their connection. Label illustrative pseudocode and copyable code. Preserve existing behavior unless the example explicitly changes it.

## Load the relevant skill

Read the skill whose invariant or behavior the question concerns. Domain skills work independently. Load Architecture for orientation or a journey spanning owners, not before every question.

| Discussion concerns | Skill |
| --- | --- |
| Overall product, runtime topology or several domain owners | [Architecture](.agents/skills/inframeld-architecture/SKILL.md) |
| Identity, permissions, credentials, model connection authority or recovery | [Access](.agents/skills/inframeld-access-models/SKILL.md) |
| Documents, versions, collections, uploads, source sync or deletion | [Knowledge](.agents/skills/inframeld-knowledge/SKILL.md) |
| Parsing, profiles, embeddings, generations, shards, filters or cleanup | [Indexing](.agents/skills/inframeld-indexing/SKILL.md) |
| Working configuration, builds, queries, receipts or feedback | [Pipelines](.agents/skills/inframeld-pipelines/SKILL.md) |
| Cases, benchmarks, judges, comparisons or evaluation history | [Evaluation](.agents/skills/inframeld-evaluation/SKILL.md) |
| Serving selection, publication modes, canaries or rollback | [Releases](.agents/skills/inframeld-releases/SKILL.md) |
| Any repository code planning, suggestions, additions, changes, refactoring or review, including tests and code snippets | [Coding Standards](.agents/skills/inframeld-coding-standards/SKILL.md) |
| Application boundaries, HTTP/MCP/CLI contracts, orchestration, jobs or idempotency | [Application Contracts](.agents/skills/inframeld-application-contracts/SKILL.md) |

Use the client's skill invocation mechanism when available. If discovery misses a skill, read its linked SKILL.md directly, for example through `$inframeld-pipelines`. Actually read the relevant body and reference. Briefly identify a skill on first use. Follow specific neighboring guide sections when a dependency matters, adding another skill only when its broader context matters. Do not load all skills or every linked document for a small question. Unrelated styling/general programming needs no domain skill.

## Mandatory code guidance

Before planning, suggesting, adding, changing, generating, refactoring or reviewing any repository code, read [Coding Standards](.agents/skills/inframeld-coding-standards/SKILL.md). This includes tests, code snippets and reviews without file edits. Select the language before applying its conventions. Backend Python follows the mandatory references below. Other languages follow their existing directory and language guidance, including [web guidance](apps/web/AGENTS.md), without importing Python-specific declarations or architecture. This adds no new Rust or TypeScript standards.

Behavior-only explanations, request tracing and documentation-only work do not require Coding Standards merely because source is inspected. If the answer starts suggesting code changes or evaluating code quality, load it before doing that work. Loading any skill grants no write authority.

## Mandatory backend conventions

Before planning, suggesting, generating, refactoring or reviewing backend Python components, read [Coding Standards](.agents/skills/inframeld-coding-standards/SKILL.md), its [component roles and imports](.agents/skills/inframeld-coding-standards/references/component-roles-and-imports.md) reference and the [canonical component conventions](docs/development/application-structure.md#component-conventions). Read its applicable static-utility, value/record, protocol/persistence and testing/documentation references before making the affected suggestions or review findings. These are mandatory conventions, not optional advice. Do not load every reference for a small question.

Read the owning domain workflow when behavior matters. For services, orchestration or provider/session boundaries, also read [Application boundaries and services](.agents/skills/inframeld-application-contracts/references/components-and-services.md). Before suggesting or reviewing a backend service or complete write, read [Services and use cases](.agents/skills/inframeld-coding-standards/references/services-and-use-cases.md), the [service-writing guide](docs/development/application-structure.md#service-writing-guide) and [grant reference chain](docs/development/application-structure.md#grant-command-flow). For aggregate or repository changes and reviews, also read [Aggregates and repositories](.agents/skills/inframeld-coding-standards/references/aggregates-and-repositories.md). These reference requirements are mandatory for their affected components.

Follow domain → layer → component role. Keep one primary public production type per defining module. Services orchestrate, aggregates own state transitions, pure policies decide, adapters perform specific I/O, and bootstrap assembles/closes resources. Keep HTTP/ORM/vendor types outside domain/application contracts. Do not recreate competing layouts, generic repositories, command buses or workflow/record frameworks.

Default reusable pure production conversion and validation utilities to cohesive named classes with static methods and direct class imports. Keep services instantiated and value-specific invariants on their owners. Small private helpers, fixtures and framework-required callables may remain functions. Standard-library and SDK module imports remain valid. Apply value objects where domain meaning, invariants, identity, secrecy or accidental mixing justify them, preserving enum and primitive exceptions.

Use application-owned runtime identifiers and secret-safe values. UUID IDs are distinct frozen slotted dataclasses, not aliases/NewType. Preserve wire/database meanings and real boundary conversion. Generated database access uses typed SQLAlchemy expressions/mappings, never raw SQL or string-keyed record mappings. The isolated CREATE/DROP test-database exception remains restricted to `apps/backend/tests/support/postgres.py`, as detailed in the mandatory reference.

All protocol implementations, adapters, fakes and doubles explicitly inherit their protocol, implement required abstract members and mark overrides. Preserve strict Pyright with `reportImplicitOverride`. Typed contexts are not permission certificates. All workflows retain current authorization and the documented transaction/provider boundaries.

## Behavioral testing and documentation

For new behavior or a bug fix:

1. Establish only the public symbols/signatures/lifecycle needed for test execution, without implementing the tested behavior.
2. Write the behavioral test.
3. Run it and require the intended behavioral failure. Import/collection failures mean the scaffold needs only its missing seam.
4. Implement the smallest real behavior, then run the focused test and relevant suite.
5. Refactor with tests green. Do not smuggle behavior into scaffolds or add interfaces for speculative future services.

Do not add architecture/import-boundary tests, dependency fixtures, composition-root construction tests, naming checks or similar repository-setup enforcement tests. The developer guards those conventions manually. Test actual product behavior, contracts and integrations.

Apply purpose-first, compact, value-based documentation to production and test code. Preserve trust, failure, ownership and meaningful scenario details without blanket declaration coverage. Protocols own shared contracts. Use no semicolons or em dashes in prose, comments or docstrings. Coding Standards' mandatory testing/documentation and component references contain the complete docstring and naming rules.

## Sources, status and product boundaries

Resolve code paths from the repository root.

[ARCHITECTURE.md](docs/ARCHITECTURE.md) is the canonical introduction. Topic guides own current behavior, procedures and limits. [The data model](docs/development/data-model.md) owns records and distinguishes logical/proposed physical/implemented design. [ADRs](docs/adr/README.md) explain accepted decisions and supersession. Skills teach and route this knowledge without becoming independent specifications.

For substantive domain answers, read the relevant current guide, owning ADR and record section. Cite important rules and explain lifecycle and ownership through the user's example. Inspect code before claiming behavior exists. Distinguish accepted design, proposed implementation, inspected code, checks personally run, developer-reported evidence, deferred work and historical observations. Report precise conflicts and effects rather than inventing policy. Use current primary documentation for external capabilities when needed.

Preserve Apache-2.0 OSS, single-server Docker Compose, strict DDD/Clean Architecture, lightweight CQRS and a scope one developer can maintain. Knowledge, Indexing, Pipelines, Evaluation, Releases and Access are owners in one backend. All remote model calls use ModelGateway. Private starter resources are ordinary resources. Readiness, current health, publication authority and shared connection changes remain distinct. First-answer timing is flexible and cannot weaken correctness.

Backend work comes first. V1 delivers a Rust CLI and small Kratos/Hydra account UI. Full Studio is deferred and follows the same CLI-led contracts. Use native selected FastAPI OpenAPI 3.1.x and generated application clients without choosing a generator package or adding a competing handwritten client. Follow ADR-0055 and the CLI delivery plan. Use the implementation issue template and shared Definition of Done for authorized backlog work, preserving completed history and independence from Studio.

Read applicable directory instructions, including [web guidance](apps/web/AGENTS.md). Guidance does not enforce filesystem security. Use the client's read-only controls when enforcement is needed.

## PR descriptions and maintenance

Before drafting a PR title/description or creating a PR, read [.github/PULL_REQUEST_TEMPLATE.md](.github/PULL_REQUEST_TEMPLATE.md). Use its headings/checklists and actual branch changes. Distinguish personally run, developer-reported and pending checks. Never mark unverified items complete. Drafting text does not authorize creating/updating a GitHub PR.

For authorized domain changes, update the current guide, affected record sections, navigation and relevant skill together. Architectural choice changes receive a superseding ADR using [the template](docs/adr/template.md), preserving and cross-linking earlier rationale. Ordinary corrections/navigation may update an existing ADR. Never turn proposed or untested design into an implemented guarantee.

### Offer and maintain skill updates

Apply [Agent Skills](https://agentskills.io/skill-creation/best-practices), [Anthropic](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices) and [OpenAI](https://developers.openai.com/plugins/build/skills) authoring principles: focused scope, concise core instructions, conditional references, concrete examples and realistic validation.

1. **Identify durable improvements.** At a meaningful task handoff, consider accepted decisions, confirmed conventions, inspected implementation changes, stale examples and demonstrated routing failures. Offer an update only when it improves future behaviour and existing guidance needs correction or expansion. Routine work and already documented rules need no offer.
2. **Check evidence and ownership.** Compare the finding with the owning guide, decisions and inspected code. Distinguish accepted design, implementation and verification. Name unresolved conflicts and include required canonical-source updates in the proposal. Link implementation only when files exist.
3. **Offer once, with concrete scope.** Batch related improvements into one concise handoff offer naming the skill, reason, evidence, exact files or sections and intended edits. Raise blocking contradictions earlier. Respect declined or deferred offers unless material new evidence appears. Complete exact edits explicitly approved in this conversation. Otherwise request file-specific confirmation under the read-only rule.
4. **Choose the smallest home.** Revise the existing owning section. Keep discovery conditions and essential instructions in `SKILL.md`. Put conditional workflows, explanations and substantial examples in directly linked references with clear loading conditions. Add scripts, assets or another skill only for a distinct reusable need.
5. **Preserve structure and knowledge.** Remove superseded duplication while retaining applicable requirements, exceptions and rationale. Explain unfamiliar concepts through concrete examples. Keep one active body per skill. Exclude task logs, speculative rules and copied canonical manuals.
6. **Validate the affected change.** Check relevant frontmatter, links, routing and source-backed snippets. For changed activation or substantial workflows, use representative positive and negative trials. Report checks actually run and unavailable evaluations.

Follow [documentation maintenance](docs/development/documentation-maintenance.md) for detailed procedures. Preserve the recorded unavailability of historical material. In a read-only review, report needed corrections instead of making them. Loading any context never grants write authority.
