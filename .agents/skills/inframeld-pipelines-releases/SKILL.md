---
name: inframeld-pipelines-releases
description: Explain or review Inframeld pipeline builds, serving, feedback, canaries, rollback and reversible automatic/manual publication. Use for the in-app RAG lifecycle and default onboarding, not a GitHub CI workflow.
---

# Inframeld Pipelines and Releases

Keep two owners clear while explaining one user workflow. Pipelines owns
immutable configuration/bindings, query orchestration, AnswerReceipts and answer
feedback. Releases owns Deployment pointers, cohort routing and legal transitions.
This skill groups related work; it does not merge these domain areas.

## Scope and reading route

Default to read-only explanation and review. Loading the skill does not authorize
code edits, release commands or external mutations. Paths are repository-relative.
Read the relevant guide section and owning ADR; flag mismatches instead of
letting this reminder become an alternative specification.

- `docs/ARCHITECTURE.md`: first-use, builds, serving, evaluations, releases and
  feedback sections as relevant; do not routinely load them all.
- `docs/adr/ADR-0002-product-owned-openapi-contract.md`: accepted in-app workflow.
- `docs/adr/ADR-0004-immutable-rag-lineage-and-release-identities.md` and
  `docs/adr/ADR-0016-profile-specific-index-materializations-and-pipeline-bindings.md`:
  immutable inputs and complete ready bindings.
- `docs/adr/ADR-0010-sticky-logical-canary-deployments.md`: routing/transitions.
- `docs/adr/ADR-0018-answer-feedback.md`: accepted feedback/receipt behavior.
- `docs/adr/ADR-0020-default-onboarding-and-first-publication.md`: required default
  experience and accepted reversible Automatic updates / Manual releases.
- Consult ADR-0005/0006/0008/0009 for pins, access, retries or offline evidence
  only when that dependency matters to the task.

## Domain language and boundaries

A Pipeline is the logical configuration/test association; a PipelineVersion
freezes one configuration and complete index bindings. A build request freezes
inputs while preparing missing dependencies; its reserved version identity is
not a serveable version. An IndexMaterialization belongs to Indexing. A Deployment
provides a stable serving identity with current/candidate/previous targets.
AnswerReceipt records what actually served; Feedback is its mutable current
rating, not an evaluation run or new deployment state.

Deployment is an explicit aggregate root for transitions. PipelineVersion is an
immutable consistency boundary. Pipeline configuration and answer-feedback
updates have their own bounded invariants; do not infer a prescribed ORM class
or load every version/receipt as a child of one large Pipeline aggregate.

## Important behavior

1. Build freezes revisions, profiles and configuration. Publish complete ready
   bindings only after Indexing verifies them. Building alone never changes
   Deployment pointers. A prompt change can reuse its ready index.
2. A query selects one version and bounded retention pin, then uses that exact
   authorized corpus for its whole execution. Recheck current permission/health
   before egress and disclosure. A release halfway through cannot reattribute
   the answer or silently reroute a partly executed query.
3. Embeddings and generation use ModelGateway. Validate citations against actual
   final evidence. Missing credentials, failed shards or selected reranker
   failures do not cause a different provider, unfiltered query or fallback answer.
4. An application affinity key determines cohorts, not identity or document
   rights. The documented hash uses stable principal/rollout identities, not
   percentage or rotating credential identity. Ten percent means a share of
   identities, not an exact request count. Enforce required affinity.
5. Aborting B preserves current A and previous Z. Promoting B makes A previous.
   Rollback restores A and consumes that one-step target. An active candidate or
   unavailable rollback target blocks rollback; never choose another target
   silently. Different commands use expected revision; retries retain their key.
6. In Manual releases, Build, Compare, canary changes and release decisions are
   explicit. Automatic updates combines authorized build and separate publication;
   Compare stays explicit in both modes and does not pause updates. Durable work
   continues automatically. Scores/feedback do not authorize release. No external
   runner, webhook, autonomous ramp or general workflow engine is required.
7. AnswerReceipt records actual pipeline/deployment revision/cohort and every
   source used in final generation, including uncited sources. It is not a
   permanent full-answer log. Lost-answer replay returns safe receipt status,
   not regeneration. Fixed integrations retain their own successful answer.
8. Accepted PUT/GET feedback uses one current rating per answer/originating
   principal, bounded comment, revision and timestamps. Corrections use a new
   key plus expected revision; duplicates add no vote. Current source access
   protects receipts, comments and counts. Late feedback remains on its original
   version/cohort; expiry follows receipt retention without pinning vectors.
9. Studio separates offline and online evidence. Coverage divides rated answers
   by eligible produced receipts in the same authorized answer-time window.
   Missing feedback is not negative; self-selection and incomplete denominators
   remain visible. Inframeld verifies the submitting application, not its users.

## Accepted publication modes and defaults

Publication mode belongs to each Deployment, not PipelineVersion or every
deployment of a Pipeline. The default configure-models → upload → ask path starts
automatic. Explicit deployment creation defaults manual with an automatic option;
it still selects one genuinely ready initial version. Before the default's real
Deployment exists, its binding owns mode/control revision and the route returns
not-ready. First publication transfers that state atomically. No fake version,
candidate, previous target or separate Prepare and ask operation is introduced.

Automatic mode uses completed authorized batches and explicit Save and apply
configuration actions. Each freezes a complete corpus and selected configuration;
unrelated drafts are ignored. Build then separate publication uses normal jobs
and domain rules. A failed/partial update never replaces healthy current.
Automatic publication retains former current as the one-step previous target.
The initiating actor needs build/deploy rights as well as mutation permissions;
an upload-only operation cannot publish or fan out to unauthorized targets.

Both switches are accepted. Automatic → manual preserves current and invalidates
pending publication; builds may finish ready. Manual → automatic freezes the
displayed inputs and admits a fresh update, leaving current until success.
An attached candidate, even at 0%, blocks enabling automatic. Candidate/canary,
promotion/rejection and rollback commands require manual; rollback leaves manual.
Re-enabling afterward deliberately authorizes applying selected changes again.

Every switch advances control revision: an old job cannot publish after off/on
merely because mode is automatic again. One automatic operation per deployment
runs at a time; newest authorized request identity guards overlapping uploads.
Superseded work can yield reusable artifacts but not publication or a fallback
after newer failure. Check captured control/request/attempt/serving state,
readiness and current permission atomically with publication. Never refresh an
old job's captured authority. A switch cannot undo an already committed release.

Default deletion/rebinding invalidates old work; restart never resurrects removed
resources. Shared default-route shape remains an implementation recommendation;
HTTP/MCP/SDK parity and concurrency behavior require qualification. Read ADR-0020
for the detailed sequence rather than inventing a generic release-policy engine.

## Review examples

Trace P12 → built P13 → comparison → canary → abort, then separately promotion
and rollback. Include a concurrent operator, an unavailable target and a late
feedback comment. For onboarding, trace two files and a failed replacement while
separating accepted behavior from untested implementation and usability
assumptions. Include an old build finishing after automatic → manual → automatic
and a new deployment's default/manual creation choice. Read one neighboring owner
when needed; do not invent release
states, broad statistics or a parallel quickstart RAG implementation.
