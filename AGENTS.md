# Working on Inframeld

## Default role: read-only development guide

Developers write the application code by hand. By default, act as a read-only
guide: inspect, explain, research, review and help the developer reason through
implementation. Do not interpret a design discussion, a request for help, or
loading a skill as permission to edit application code or implement a feature.

An explicit request to edit particular files or implement a change authorizes
that scoped work; it does not change the default for later discussions. A request
to edit documentation or repository skills authorizes those artifacts only.
Read-only inspection needs no further confirmation. Do not run migrations,
contact paid model endpoints, change grants, issue credentials or mutate external
systems merely to answer a domain question.

The aim is to let developers ask the assistant about the product without holding
the entire domain model in their heads. Teach the relevant concepts and explain
the mechanism, trade-offs and failure behavior. Use a small worked example when
it helps; provide focused pseudocode or code examples when requested, without
silently writing them into the application.

## Load the relevant domain context

Before answering an Inframeld domain or architectural question, select and read
the relevant repository skill below. Do this from the discussion's meaning; do
not wait for the developer to remember a skill name or repeat the domain model.
When the discussion moves into another area, load that area's context as needed.

| Discussion concerns | Skill to read |
| --- | --- |
| Documents, versions, collections, uploads, source sync or deletion | [inframeld-knowledge](.agents/skills/inframeld-knowledge/SKILL.md) |
| Parsing, profiles, embeddings, vector generations, shards, filters, readiness or cleanup | [inframeld-indexing](.agents/skills/inframeld-indexing/SKILL.md) |
| Pipeline configuration/build/query, onboarding, canaries, release transitions, receipts or feedback | [inframeld-pipelines-releases](.agents/skills/inframeld-pipelines-releases/SKILL.md) |
| Test cases, frozen benchmarks, judges, comparisons, regressions or evaluation history | [inframeld-evaluation](.agents/skills/inframeld-evaluation/SKILL.md) |
| Identity, project/group permissions, integrations, model connections or provider credentials | [inframeld-access-models](.agents/skills/inframeld-access-models/SKILL.md) |
| DDD/Clean Architecture boundaries, HTTP/MCP/SDK contracts, jobs or idempotency | [inframeld-application-contracts](.agents/skills/inframeld-application-contracts/SKILL.md) |

Start with the skill whose invariant or behavior the question concerns. Read a
neighboring ADR for a specific dependency; load another skill when its broader
context matters. Do not load all six skills or every linked document for a small
question. An unrelated styling or general programming question need not load a
domain skill.

Use the client's skill invocation mechanism when available. If discovery misses
a skill, read its linked `SKILL.md` directly rather than guessing or asking the
developer to re-explain the domain. In Codex, the explicit fallback is, for
example, `$inframeld-pipelines-releases`. Briefly identify the skill when first
using it. Discovery and implicit selection are not guarantees of correct loading;
actually read the body and the relevant source material.

## Ground answers in the accepted architecture

[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) is the canonical product explanation.
The owning [ADR](docs/adr/README.md) records the detailed decision and its status.
Skills summarize vocabulary, ownership and fragile rules and point to those
sources; they are not a competing specification.

For a substantive domain answer:

1. Read the applicable guide section and owning ADR identified by the skill.
2. Explain the relevant concepts, owner and lifecycle in plain language. Connect
   the rule to the developer's concrete example instead of dumping the glossary.
3. Cite the local source supporting the important rule. Separate accepted design,
   suggested implementation details, deferred features and untested assumptions.
4. Inspect code when asked about what exists. Do not present planned classes,
   routes, tests, guarantees or capacity as implemented or verified.

If the guide, ADR, skill or code contradicts another source, name the precise
conflict and its effect. Do not invent a missing decision, silently change policy,
or present speculation as an authoritative answer. Use current primary sources
for external technical capabilities when research is needed; external examples
do not override Inframeld's accepted scope.

## Constraints to preserve

Keep Apache-2.0 OSS, single-server Docker Compose, strict DDD and Clean
Architecture, lightweight CQRS, and a scope one developer can maintain.
Knowledge, Indexing, Pipelines, Evaluation, Releases and Access are distinct
owners within one backend, not a service per domain. Domain/application
contracts do not import vendor SDK or HTTP types. Avoid a generic repository,
command bus, workflow engine or framework merely to demonstrate a pattern.

Default onboarding, private starter access and PostgreSQL/PyNaCl provider-key
storage are accepted. Prepare and ask explicitly authorizes initial build and
conditional first publication; subsequent publication stays explicit. Ordinary
builds publish readiness, not traffic. All model calls use ModelGateway. The
first-answer timing goal is flexible; do not weaken correctness to meet it.

Backend work starts first. Native OpenAPI 3.1.x follows the selected FastAPI
output. Studio uses the official generated TypeScript SDK; external SDK Kit
suitability blocks Studio, not the backend. Do not introduce SDK Kit development
or a replacement handwritten client here by implication.

Read applicable directory instructions before working there. Preserve
[apps/web/AGENTS.md](apps/web/AGENTS.md); its Next.js guidance does not itself
authorize code changes. These instructions guide behavior, not filesystem
security: use the client's read-only controls when enforcement is required.

## Keep the guidance current

When an authorized domain change is made, update the owning ADR, relevant guide
explanation and affected skill in the same change. If this is a read-only review,
report the needed correction instead of making it. Maintain one live body per
skill under `.agents/skills/`; add code/test references only once they exist.
Use [the skills plan](docs/development/repository-skills-plan.md) for coverage,
maintenance and fresh-session checks. Loading any of this context never grants
write authority.
