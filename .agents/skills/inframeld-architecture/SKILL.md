---
name: inframeld-architecture
description: Explains Inframeld's overall product, runtime architecture and domain ownership. Use for orientation or journeys spanning several domains, rather than a single-domain detail.
---

# Inframeld architecture

Help a developer understand what Inframeld is building and which part owns a behavior. Start with a concrete user goal, then introduce the architecture needed to explain it. This skill is for orientation and questions spanning domains. A focused authentication or indexing question can use its own domain skill directly.

## Working model

Alice wants a support assistant to answer questions from her team's handbook. Inframeld admits the document, prepares searchable passages, runs a configured retrieval-and-generation pipeline, and records which evidence produced an answer. Retrieval-augmented generation, or RAG, means finding relevant passages and supplying them to a model as evidence. Retrieved evidence does not prove an answer is correct.

The product has six owners within one modular backend:

| Owner | Responsibility |
| --- | --- |
| Knowledge | Source admission, immutable document versions and exact collection membership. |
| Indexing | Parsing/chunking profiles, embeddings, derived vectors and verified search readiness. |
| Pipelines | Working configuration, builds, query execution, answer receipts and feedback. |
| Evaluation | Reviewed cases, frozen benchmarks, fresh comparisons and protected offline evidence. |
| Releases | Deployment serving pointers, publication modes, canaries and rollback. |
| Access | Local identities, memberships, grants and current authorization. |

For example, changing R1={A1,B1} to R2={A1,B2} does not rewrite B1. Indexing can reuse unchanged A1's compatible data across those revisions. A successful build produces a ready PipelineVersion. Releases separately decides whether that version receives traffic. These distinctions let Alice change knowledge without silently rewriting history or authorizing publication.

## Essential rules

- Preserve Apache-2.0 OSS, one-server Docker Compose and a scope one developer can maintain. Domains are responsibilities, not separate network services.
- API and worker processes share application behavior. Domain rules remain independent of HTTP, ORM and vendor SDK types. Supporting jobs and audit do not create another business domain.
- PostgreSQL owns application authority. Chroma stores derived vectors, and SeaweedFS stores source and derived artifacts. Every remote model call uses ModelGateway.
- Authentication establishes identity. Product admission, action grants and document access are separate current checks. Historical records never bypass changed permissions or erasure.
- Readiness, release authority and current dependency health are separate. Evaluation scores and feedback do not authorize publication.
- V1 is backend-first, with a Rust CLI and small Kratos/Hydra account UI. Full Studio is deferred. Do not turn a target diagram into an implementation claim.

## Explain or review

1. Identify the user's goal and follow one ordinary example through its owners.
2. Explain each new term when it first matters. Name the record that stays fixed and the state that may change.
3. Describe the relevant failure, retry, permission change or deletion. Identify which owner decides the outcome.
4. For existing behavior, inspect the relevant implementation. Separate accepted design, inspected code, recorded verification and remaining qualification.
5. Cite the exact current rule. Report unresolved disagreements rather than inventing a missing decision. Loading this skill grants no write or external-action authority.

## Read as needed

- For processes, infrastructure and trust boundaries, read [System overview](references/system-overview.md).
- For an unfamiliar shared term, read the relevant entry in [Glossary](references/glossary.md). Do not load the whole glossary for every question.
- For onboarding and the complete knowledge-to-answer journey, read [Document to answer](references/document-to-answer.md).

The [architecture introduction](../../../docs/ARCHITECTURE.md) owns the product overview. Topic guides own current behavior, the [data model](../../../docs/development/data-model.md) owns records, and ADRs explain decisions. These references teach that accepted design without becoming another specification.
