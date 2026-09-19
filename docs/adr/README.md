# Architecture Decision Records

Start with the **[canonical developer architecture guide](../ARCHITECTURE.md)**. It explains the product from the ground up. These ADRs own detailed decisions and rationale. The [earlier closing review](../reviews/v1-architecture-review.md) is historical assessment, not a new review gate; current onboarding decisions are in ADR-0019/0020.

## Authority and qualification

Accepted design is separate from tested implementation. The product is a single-server, Apache-2.0 Docker Compose deployment with strict DDD/Clean Architecture and lightweight CQRS. Immutable vector generations, PostgreSQL membership, server-owned permission filters, SeaweedFS, Kratos/deployment OIDC, opaque fixed-integration credentials, group allowlists, custom/private model endpoints and the universal ModelGateway boundary are selected.

OpenEvals and configurable GPT-5.6 Luna are now selected for initial groundedness qualification. Pipeline-associated cases, frozen benchmarks, baseline/candidate comparison and case/version history are confirmed. The explicit in-app Build → Compare → Canary → Promote/Reject → Rollback workflow applies in Manual releases. Automatic updates uses advance authorization from source/configuration actions, never evaluation scores, to publish ready results. Work and routing run automatically after admission. GitHub/external runners, webhooks and a workflow engine are deferred.

The detailed feedback PUT/GET/editing/Studio contract and the two-tool MCP/header-capable trusted-client profile are **accepted**, with SDK/interoperability tests pending. Native FastAPI OpenAPI **3.1.x** is accepted; there is no 3.0.3 output requirement. SDK Kit is an external project whose extraction/suitability blocks Studio implementation only; the backend proceeds first.

Default configure-models → upload → ask and persistent application-entered credentials are confirmed v1 requirements. Private starter/access defaults are accepted in ADR-0019, and ADR-0020 selects application-managed authenticated ciphertext in PostgreSQL using PyNaCl with a separate persistent root key. The first-answer scenario is accepted as a flexible usability goal: two minutes is aspirational and roughly ten minutes is also acceptable, with no hard timing gate. Reversible Automatic updates / Manual releases are accepted. The default path starts automatic; newly created deployments default manual with an explicit automatic option. Authorized updates can build and publish repeatedly, while manual canaries and release decisions remain explicit. There is no one-time Prepare and ask operation. Precise default-selector shapes remain implementation recommendations, not backend approval blockers.

Backup/restore remains required with the existing provisional coordinated baseline; numerical objectives and validation are deferred to implementation. Index reconstruction, Hydra/own OAuth issuance, verified user delegation, general ACLs, LangSmith/Langfuse/exporters and deeper evaluation diagnosis remain deferred. Exact image pins, parser enforcement, gateway integration, model calibration, vector recovery and capacity still need tests; none has been certified by this documentation work.

Legacy filenames for ADR-0011/0013 remain for link stability and no longer imply a mandatory AWS-hosted architecture.

## Decision index

| ADR | Subject | Current authority |
| --- | --- | --- |
| [0001](ADR-0001-modular-application-structure.md) | Modular domain/application structure | Strict DDD/Clean Architecture/lightweight CQRS accepted; no new service per domain |
| [0002](ADR-0002-product-owned-openapi-contract.md) | Code-first API, official clients, in-app workflow | Workflow and generated TypeScript Studio integration accepted; native 3.1.x accepted; external SDK Kit blocks Studio only |
| [0003](ADR-0003-immutable-rag-lineage-and-release-identities.md) | Immutable identities and provenance | Source/revision/profile/pipeline distinctions retained; serving attribution extended for feedback |
| [0004](ADR-0004-postgresql-source-of-truth-and-shared-chroma.md) | Immutable vectors, shards, membership and recovery | Accepted for qualification; explicit costs, ordinary retries and exceptional cleanup |
| [0005](ADR-0005-api-enforced-tenancy-and-authorization.md) | Kratos and application authorization | Identity/group/fixed actor and private starter/access defaults accepted |
| [0006](ADR-0006-byok-provider-boundary.md) | ModelGateway and OSS custom endpoints | Accepted universal boundary and persistent application-entered keys; PostgreSQL/PyNaCl selected in 0020 |
| [0007](ADR-0007-durable-jobs-idempotency-and-recovery.md) | Jobs, idempotency and safe receipts | Accepted behavior; no hidden secret/full-answer replay cache |
| [0008](ADR-0008-deterministic-evaluation-and-release-decisions.md) | In-app evaluation and history | OpenEvals + configurable Luna selected; calibration/integration unperformed |
| [0009](ADR-0009-sticky-logical-canary-deployments.md) | Affinity, abort, promotion and rollback | Explicit transition semantics accepted; online feedback remains advisory |
| [0010](ADR-0010-secure-document-ingestion-boundary.md) | Parser isolation | Concrete mechanism selected; supported-host tests still required |
| [0011](ADR-0011-hosted-vercel-and-aws-deployment-profile.md) | Production Compose / SeaweedFS | Selected runtime shape; MCP accepted in existing API, no new identity/service stack |
| [0012](ADR-0012-backward-compatible-database-migrations.md) | Controlled runtime upgrades | Maintenance-window baseline retained; separate from RAG rollback |
| [0013](ADR-0013-minimal-hosted-observability-and-recovery.md) | Backup/restore baseline | Provisional approach/objectives retained; no further operations exercise needed to start |
| [0014](ADR-0014-data-retention-deletion-and-external-processing.md) | Scoped deletion and bounded evidence | Existing security boundaries retained; feedback extends bounded receipt retention |
| [0015](ADR-0015-profile-specific-index-materializations-and-pipeline-bindings.md) | Ready materializations and bindings | Existing immutable generation/profile ownership retained |
| [0016](ADR-0016-docling-processing-and-cross-encoder-reranking.md) | Docling/reranker and future seams | Built-ins retained; hook/webhook execution and custom evaluators deferred |
| [0017](ADR-0017-answer-feedback.md) | Online answer feedback | Accepted originating-principal editable contract and Studio behavior |
| [0018](ADR-0018-first-party-mcp-adapter.md) | First-party MCP consumption | Accepted two tools and header-capable client profile; default selector implementation recommendation in 0019 |
| [0019](ADR-0019-default-onboarding-and-first-publication.md) | Default onboarding and reversible publication modes | Private defaults, automatic/manual creation choices, two-way switching and flexible first-answer scenario accepted; implementation qualification pending |
| [0020](ADR-0020-persistent-outbound-credentials.md) | Persistent outbound model credentials | Accepted encrypted PostgreSQL/PyNaCl storage and security boundary; suggested API shapes, implementation tests pending |

Repository-specific skills are installed under `.agents/skills/`, with a root read-only working agreement and [six domain skills and their coverage plan](../development/repository-skills-plan.md). SDK Kit remains external and no extraction/trial is authorized here. Markdown/link checks establish documentation integrity only; behavior needs implementation tests.
