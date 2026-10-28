# Working on Inframeld

## Default role: read-only development guide

Act as a read-only guide by default for questions, explanations, design discussions and reviews: inspect, explain, research and help the developer reason through implementation. Loading a skill or discussing a plan does not itself authorize implementation.

When the developer requests implementation or edits, proceed with the necessary repository changes, tests and documentation within the requested scope. Do not require a separate write-confirmation phase or file-by-file approval. Ask for clarification when material ambiguity or a destructive, irreversible or external action needs additional authorization. Keep unrelated work intact and do not silently expand the task.

Read-only inspection needs no approval. Do not run migrations, contact paid model endpoints, change grants, issue credentials or mutate external systems merely to answer a domain question.

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
| Authored Python, including backend components and tests | [Python Standards](.agents/skills/inframeld-python-standards/SKILL.md) |
| Authored Rust, including CLI and xtask code | [Rust Standards](.agents/skills/inframeld-rust-standards/SKILL.md) |
| Application boundaries, HTTP/MCP/CLI contracts, orchestration, jobs or idempotency | [Application Contracts](.agents/skills/inframeld-application-contracts/SKILL.md) |
| Rust SDK consumption, generation, qualification or generator patches/upgrades | [Rust SDK](.agents/skills/inframeld-rust-sdk/SKILL.md) |
| Shared SDK generation policy, new endpoint coverage or cross-language qualification | [SDKs](.agents/skills/inframeld-sdks/SKILL.md) |
| TypeScript SDK consumption, Fetch/Zod behavior or generator maintenance | [TypeScript SDK](.agents/skills/inframeld-typescript-sdk/SKILL.md) |
| Python SDK consumption, HTTPX/Pydantic behavior or generator maintenance | [Python SDK](.agents/skills/inframeld-python-sdk/SKILL.md) |
| Choosing test layers, dependency isolation or interpreting verification evidence | [Testing](.agents/skills/inframeld-testing/SKILL.md) |

Use the client's skill invocation mechanism when available. If discovery misses a skill, read its linked SKILL.md directly, for example through `$inframeld-pipelines`. Actually read the relevant body and reference. Briefly identify a skill on first use. Follow specific neighboring guide sections when a dependency matters, adding another skill only when its broader context matters. Do not load all skills or every linked document for a small question. Unrelated styling/general programming needs no domain skill.

SDK skills are independently discoverable siblings. The shared SDK skill owns common policy, without being a prerequisite for ordinary language-specific consumption. Testing is conditional guidance for test strategy and evidence, not an additional prerequisite for every code change. Coding Standards remains mandatory for repository code work.

## Mandatory code guidance

Before planning, suggesting, adding, changing, generating, refactoring or reviewing any repository code, read [Coding Standards](.agents/skills/inframeld-coding-standards/SKILL.md). This includes tests, code snippets and reviews without file edits. Select the language before applying its conventions. Authored Python additionally reads [Python Standards](.agents/skills/inframeld-python-standards/SKILL.md), and authored Rust reads [Rust Standards](.agents/skills/inframeld-rust-standards/SKILL.md). Backend Python follows the mandatory references below. Web and other languages keep their directory/language guidance, including [web guidance](apps/web/AGENTS.md). Do not import Python declarations or backend architecture into Rust or frontend code. Generated SDK sources remain generator-owned.

Behavior-only explanations, request tracing and documentation-only work do not require Coding Standards merely because source is inspected. If the answer starts suggesting code changes or evaluating code quality, load it before doing that work. Loading any skill grants no write authority.

## Mandatory backend conventions

Before planning, suggesting, generating, refactoring or reviewing backend Python components, read the shared [Coding Standards](.agents/skills/inframeld-coding-standards/SKILL.md), [Python Standards](.agents/skills/inframeld-python-standards/SKILL.md) and its [component roles and imports](.agents/skills/inframeld-python-standards/references/component-roles-and-imports.md) reference. Read its applicable static-utility, value/record, protocol/persistence and testing/documentation references before making the affected suggestions or review findings. These are mandatory conventions, not optional advice. Do not load every reference for a small question.

Before domain-specific backend component design, code generation or structural review, read the owning domain skill's `references/architecture.md` and relevant workflow. Shared components use [Application Contracts’ shared component view](.agents/skills/inframeld-application-contracts/references/components-and-services.md), with its transaction/job or gateway reference when applicable. Use accepted design and inspected implementation according to their stated status. Identify pending proposals before recommending code that depends on them. Behaviour-only questions can use their workflow directly without loading every architecture. Read the owning domain workflow when behavior matters. For services, orchestration or provider/session boundaries, also read [Application boundaries and services](.agents/skills/inframeld-application-contracts/references/components-and-services.md). Before suggesting or reviewing a backend service or complete write, read [Services and use cases](.agents/skills/inframeld-python-standards/references/services-and-use-cases.md). For aggregate or repository changes and reviews, also read [Aggregates and repositories](.agents/skills/inframeld-python-standards/references/aggregates-and-repositories.md). These reference requirements are mandatory for their affected components.

The mandatory references own the complete conventions: domain → layer → role, one primary public type, direct imports, static utilities/mappers/policies and their function exceptions, meaningful value objects, secret-safe runtime identifiers, explicit protocol inheritance/overrides, strict typing and typed ORM. Apply those rules before proposing affected code. The raw-statement exception stays limited to CREATE/DROP in `apps/backend/tests/support/postgres.py`. Contexts never replace current authorization or transaction/provider safeguards.

## Behavioral testing and documentation

For new behavior or a bug fix:

1. Establish only the public symbols/signatures/lifecycle needed for test execution, without implementing the tested behavior.
2. Write the behavioral test.
3. Run it and require the intended behavioral failure. Import/collection failures mean the scaffold needs only its missing seam.
4. Implement the smallest real behavior, then run the focused test and relevant suite.
5. Refactor with tests green. Do not smuggle behavior into scaffolds or add interfaces for speculative future services.

Do not add architecture/import-boundary tests, dependency fixtures, composition-root construction tests, naming checks or similar repository-setup enforcement tests. The developer guards those conventions manually. Test actual product behavior, contracts and integrations.

Apply purpose-first, compact, value-based documentation to production and test code. Preserve trust, failure, ownership and meaningful scenario details without blanket declaration coverage. Interfaces own shared contracts. Use no semicolons or em dashes in prose, comments or docstrings. [Core testing and documentation](.agents/skills/inframeld-coding-standards/references/testing-and-documentation.md) owns the shared contract. Python Standards owns backend docstring/naming details and mandatory component references, while Rust Standards owns Rust idioms.

## Sources, status and product boundaries

Resolve code paths from the repository root.

[ARCHITECTURE.md](docs/ARCHITECTURE.md) introduces the product. Focused skill references own accepted feature behavior, architecture, logical records and implementation guidance. Code owns implemented representations, generated OpenAPI owns delivered HTTP shapes and migrations own persistence. [ADRs](docs/adr/README.md) record choices, rationale and explicit supersession. [Developer guides](docs/development/README.md) explain how to work in the repository.

For substantive domain answers, read the owning workflow. Read exact code contracts when fields or representations matter, and the relevant ADR when rationale, supersession or a design conflict matters. Cite important rules and explain lifecycle and ownership through the user's example. Inspect code before claiming behavior exists. Distinguish accepted design, pending choices, inspected implementation, checks personally run, developer-reported evidence and deferred work. Surface conflicts instead of inventing policy. Use current primary documentation for external capabilities when needed.

Preserve Apache-2.0 OSS, single-server Docker Compose, strict DDD/Clean Architecture, lightweight CQRS and a scope one developer can maintain. Knowledge, Indexing, Pipelines, Evaluation, Releases and Access are owners in one backend. All remote model calls use ModelGateway. Private starter resources are ordinary resources. Readiness, current health, publication authority and shared connection changes remain distinct. First-answer timing is flexible and cannot weaken correctness.

Backend work comes first. V1 delivers a Rust CLI and small Kratos/Hydra account UI. Full Studio is deferred and follows the same CLI-led contracts. Use native selected FastAPI OpenAPI 3.1.x and generated application clients without adding a competing handwritten client. The Rust SDK uses the pinned patched generator selected by [ADR-0088](docs/adr/ADR-0088-use-a-pinned-patched-generator-for-the-rust-sdk.md) and maintained through the [Rust SDK](.agents/skills/inframeld-rust-sdk/SKILL.md) skill. The TypeScript and Python selections are recorded in [ADR-0089](docs/adr/ADR-0089-select-patched-typescript-and-python-sdk-generators.md). The [SDKs skill](.agents/skills/inframeld-sdks/SKILL.md) owns common maintenance and shared conformance, whose runner and operation coverage are implemented through the private SDK tooling. [ADR-0091](docs/adr/ADR-0091-promote-selected-sdks-and-retire-generator-comparisons.md) promotes the three unpublished SDKs and retires comparison reproduction. Automatic checks and external branch-rule activation remain distinct. Follow ADR-0055 and the [V1 scope](.agents/skills/inframeld-architecture/references/v1-scope-and-extension-boundaries.md). Use the implementation issue template and shared Definition of Done for authorized backlog work, preserving issue history and independence from Studio.

Read applicable directory instructions, including [web guidance](apps/web/AGENTS.md). Guidance does not enforce filesystem security. Use the client's read-only controls when enforcement is needed.

## PR descriptions and maintenance

Before authorized GitHub issue creation, rewriting or relationship changes, follow [Author delivery issues](docs/development/documentation-maintenance.md#author-delivery-issues). Use concrete delivery examples, focused authoritative reading and native parent/blocker relationships. Preserve closed evidence and distinguish unmerged work from completed delivery. Drafting or reviewing an issue does not authorize publishing it.

Before drafting a PR title/description or creating a PR, read [.github/PULL_REQUEST_TEMPLATE.md](.github/PULL_REQUEST_TEMPLATE.md). Use its headings/checklists and actual branch changes. Distinguish personally run, developer-reported and pending checks. Never mark unverified items complete. Drafting text does not authorize creating/updating a GitHub PR.

For authorized domain changes, update the owning workflow/record references, affected human guidance and navigation together. Architectural choice changes receive a superseding ADR using [the template](docs/adr/template.md), preserving and cross-linking earlier rationale. Ordinary corrections/navigation may update an existing ADR. Never turn proposed or untested design into an implemented guarantee.

### Resolve architecture decisions when needed

Before proposing code or implementing a contract that depends on a pending decision, read the matching reference in the owning skill. Explain why its trigger applies, the alternatives, recommendation and affected owners. Follow [the just-in-time workflow](docs/development/guides/architecture-decisions.md#just-in-time-architecture-decisions). Obtain approval of the concrete design before dependent implementation. Record the decision as part of requested implementation without a separate file-by-file approval step. Reconcile guides, records, ADRs, skill references and affected diagrams, then perform the repository-wide consistency pass before dependent implementation. Surface conflicts instead of silently changing accepted decisions. Unrelated pending decisions do not block work. Qualification gaps do not prohibit evidence-gathering tests. Approval of a proposal or its documentation does not authorize application edits.

### Offer and maintain skill updates

At a meaningful handoff, offer one evidence-backed update only when an accepted decision, confirmed convention, inspected change, stale example or demonstrated routing failure exposes a real guidance gap. Name the owning skill, evidence, exact files/sections and intended edits. Complete updates within the requested scope. Offer unrelated updates rather than applying them silently. Respect decline/deferral unless material evidence changes.

Check owning sources and distinguish design, implementation and verification. Surface conflicts. Keep discovery and essential instructions in `SKILL.md`, conditional explanations/examples in directly linked references, and one active owner per requirement. Preserve exceptions and rationale while removing superseded duplication. Do not add logs, speculative rules or copied manuals. Add resources or skills only for a distinct reusable need.

Follow the mandatory [skill-authoring procedure](docs/development/guides/skill-authoring.md) for evidence, ownership, writing and validation, including realistic positive/negative trials when activation or substantial workflows change. Report checks actually run and unavailable evaluations. Routine work needs no offer.

Follow [documentation maintenance](docs/development/documentation-maintenance.md) for detailed procedures. Preserve the recorded unavailability of historical material. In a read-only review, report needed corrections instead of making them. Loading any context never grants write authority.

For SDK tooling work, start with the [SDK runbook](packages/sdk-tools/README.md) and its [architecture map](packages/sdk-tools/docs/architecture.md). Ordinary Node feature tests own shared expectations. Native drivers call generated APIs, and filtered local runs cannot establish full qualification. [ADR-0092](docs/adr/ADR-0092-maintain-sdks-with-typed-workflows-and-native-conformance-tests.md) records the tooling choice.
