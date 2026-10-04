# Understanding Inframeld

Inframeld helps a team connect models, upload its knowledge, and ask questions grounded in that knowledge. It also helps the team understand which documents and configuration produced an answer, compare a proposed change, and control when that change reaches users.

The central technique is **retrieval-augmented generation**, or RAG: find relevant passages first, then give those passages to a model as evidence for its answer. Finding a passage does not prove that an answer is correct. Inframeld preserves the identities and evidence needed to investigate results and improve the pipeline.

This introduction explains the **accepted design**. Acceptance means we have chosen the behavior; it does not mean every feature is implemented or tested. The guides distinguish selected rules, proposed implementation details, deferred features, and qualification still required. The [backend README](../apps/backend/README.md), [HTTP error reference](development/error-handling-reference.md), and [pagination reference](development/pagination.md) describe concrete foundations already present. Inspect the relevant code when answering what works today.

## A small journey from document to answer

Suppose Alice wants a support assistant to answer questions about her company’s handbook.

1. **Alice signs in and receives private starter resources.** Kratos verifies her human identity; Hydra supplies the accepted browser-assisted human CLI login and token lifecycle. Inframeld’s Access rules decide what her local account may do. A project groups her resources; document groups control who may read the evidence. These are ordinary application resources, not a security shortcut.
2. **She configures the required model capabilities.** A connection describes how to reach a model service; each role separately selects its model. Connections have one shared current access configuration and a separately replaceable provider credential. Remote requests pass through ModelGateway, the application-owned boundary for approved destinations and provider interaction.
3. **She uploads the handbook.** Knowledge records its stable Document identity and a DocumentVersion for these bytes. Untrusted files are processed in a restricted execution boundary. Successful upload, successful parsing, and readiness to answer are different milestones.
4. **The application prepares searchable evidence.** Indexing creates text chunks, obtains embeddings, and verifies the prepared data. An embedding is a numerical representation used to find similar text. PostgreSQL records collection membership; Chroma stores derived vectors.
5. **A build prepares a pipeline version.** A Pipeline describes retrieval and generation settings. A PipelineVersion freezes selected settings and prepared inputs. Finishing a build makes that version ready; it does not itself move customer traffic.
6. **A separate release step chooses the version to serve.** A Deployment is the stable destination callers query. The default onboarding deployment uses Automatic updates, so an authorized update can request a normal build and separate conditional publication. A newly created deployment defaults to Manual releases unless its creator explicitly chooses automatic mode.
7. **A question uses current permissions.** The application checks the right to query the deployment and applies document access when selecting evidence. ModelGateway sends the permitted final evidence to generation. An answer receipt records which version and evidence served the answer without creating a hidden full-answer replay cache.

The [onboarding guide](development/onboarding.md) explains the whole journey, including incomplete configuration and provisioning retries. Its first-answer timing goal is flexible and aspirational, not a measured guarantee.

## One backend with clear responsibilities

Inframeld is an Apache-2.0 application designed for one server using Docker Compose. A **domain** is an area of the product with its own rules. These domains are separate responsibilities inside one backend, not a network service each.

| Domain | What it owns | Example question |
| --- | --- | --- |
| Knowledge | Sources, document versions, collection membership, uploads, and synchronization | Which handbook version belongs to this collection revision? |
| Indexing | Processing and embedding profiles, chunks, vectors, layouts, verification, and materializations | Is the exact search data this version needs usable? |
| Pipelines | Working configuration/history, execution-input snapshots, builds, direct/live execution, receipts, and feedback | Which configuration and evidence produced this answer? |
| Evaluation | Test cases, frozen benchmarks, evaluator revisions, comparisons, and history | How did two fixed configurations or versions perform under the same test conditions? |
| Releases | Deployment serving pointers, canaries, promotion, rejection, rollback, and publication modes | Which ready version should answer the next request? |
| Access | Local identities, memberships, grants, document groups, and authorization | Who is calling, and what may that caller do now? |

Application use cases coordinate these owners. Adapters connect them to HTTP, MCP, databases, and external products. Domain and application contracts use application-owned types rather than vendor SDK, HTTP, or database ORM types. A command changes state; a query reads it. This separation does not require a command bus, generic repository, or workflow engine.

Read [Application structure](development/application-structure.md) for dependency rules and examples. The [data model](development/data-model.md) defines records and relationships. A logical concept does not automatically imply one table, class, service, or endpoint.

For named resources, distinguish **name**, **display name** and **ID**. Alice selects `legal-research` by its name, sees `Legal Research` as its display name, and the backend retains its permanent ID in relationships and admitted work. Display names never resolve resources. This is accepted vocabulary, not a completed schema migration. The [resource-naming contract](development/data-model.md#resource-naming) owns scope, rename safeguards and the distinction from existing physical fields.

## Versions explain change without rewriting history

An **immutable** record cannot be edited after creation. A change creates another version. Imagine a collection containing A1 and B1. Replacing document B creates B2 and a new collection revision containing A1 and B2. The earlier revision still identifies A1 and B1, so an answer can be traced to the evidence that actually served it.

Different changes have different identities. Replacing bytes changes the DocumentVersion. Changing parsing or embedding settings changes the relevant profile selection. Changing retrieval or generation settings changes pipeline configuration. A release selects a ready pipeline version; changing a serving pointer does not itself recompute vectors.

Unchanged work can be reused when its full identity matches. Reusing A’s vectors avoids embedding A again, but validating a complete collection revision can still require substantial work. A **materialization** records prepared search data for an exact collection revision and profile combination. The [Indexing guide](development/indexing.md) explains matching, layouts, retries, and verification. The [Indexing data model](development/data-model.md#indexing) owns record definitions.

History does not override current access or deletion. A historical pipeline version can become unavailable when required evidence is deleted. Removing a document from a new collection revision is different from deleting all its historical data. See [Knowledge lifecycle](development/knowledge-lifecycle.md) and [Retention and deletion](development/retention-and-deletion.md).

## Permission to act and permission to read are separate

Authentication verifies identity. Authorization evaluates permission. Kratos owns human identities and browser sessions; Hydra supplies OAuth/OIDC for first-party human CLI login under [ADR-0053](adr/ADR-0053-use-kratos-and-hydra-for-human-cli-authentication.md). Access owns application authorization using PostgreSQL state. A **principal** is the stable local identity of a human or application account.

Browser cookies and verified Hydra CLI tokens resolve to the same existing human principal. CLI token verification includes private introspection and current Kratos identity eligibility before local admission and permission checks. The small browser account UI does not require the full Studio. Hydra is accepted, not deferred, but the inspected repository still has the Kratos cookie adapter rather than a completed Hydra deployment/bearer path. [Access](development/access-control.md#human-cli-authentication) separates these design and implementation facts.

Project membership alone does not grant every action. A caller may need Query on Deployment A, while document-group membership determines the evidence it may read. Every group manager must also be an ordinary member of that group. Appointment explicitly records both assignments, so managers have the document access they may share. Ordinary members cannot share access merely because they can read. The [Access guide](development/access-control.md#group-managers) explains appointment and removal.

For example, SupportBot may query Deployment A and read the Support group. It cannot query Deployment B merely because both deployments belong to one project. A valid application key identifies SupportBot; the account’s **current** permissions are checked when the key is used. Granting or removing account permissions changes what an already issued valid key can do.

Administration is bounded too. The ability to grant a permission is separate from using it, and delegation remains limited to the permitted action and target. Human-only checks still apply where required. Ordinary departure must preserve required management coverage. Emergency suspension can block a compromised sole manager immediately, with a scoped operator recovery path. Host operators control the installation but do not automatically become unrestricted readers through ordinary product APIs.

The [Access guide](development/access-control.md) owns the complete permission matrix and recovery rules. [Access records](development/data-model.md#access) distinguish the accepted model from proposed physical details in the 14-table foundation. Incoming application keys are different from outgoing provider credentials, which belong to [Model connections](development/model-connections.md).

## Preparing a version and releasing it are different actions

Alice can first edit the Pipeline's saved working configuration, query that Pipeline directly and evaluate it without creating a release-ready version. Query on a Pipeline and Query on a Deployment are separate exact-resource grants; neither implies the separate query-trace inspection grant on that resource. Each admitted query captures exact settings, corpus and prepared-data bindings; later edits cannot change an admitted run. Temporary overrides affect only that query. Restoring old settings creates a new working revision, not a production rollback. Direct querying uses the same execution and gateway behavior, not an Experiment resource, another service or a second live Deployment. [ADR-0052](adr/ADR-0052-separate-experimental-execution-from-release-ready-pipeline-builds.md) records this development loop; [Access](development/access-control.md#pipeline-query-authority) specifies the exact-resource permission rules.

**Shared connectivity is a separate operational dependency.** Under [ADR-0054](adr/ADR-0054-use-shared-current-model-connections.md), Pipeline versions select stable connection identities, not historical access settings. A connection manager may update shared access after a guarded review, affecting consumers even in Manual release mode. Prepared/in-progress embedding incompatibility or unknown compatibility rejects the update before it changes anything. Relevant access changes stop remaining model dispatches in admitted work rather than mixing configurations. Executions record what was actually used; Pipeline rollback does not restore connection settings. Use another connection and the query/build/release path for an isolated migration. [Model connections](development/model-connections.md#shared-current) owns this boundary.

When satisfied, Alice invokes `inframeld build` on the current saved configuration, not an evaluation run. The workflow captures its inputs and chooses the sole live Deployment or requires a choice when there are several. With none, an ordinary build creates an unpublished version; first-publication onboarding retains its existing separately authorized path. In **Manual releases**, the version awaits explicit release, with optional further comparison and canary review. A canary sends a defined share of callers to a candidate. Rollback selects an eligible earlier ready version, separately from configuration restoration.

The underlying build establishes readiness, not release authority. For **Automatic updates**, the user-facing Build workflow can authorize that preparation and a separate conditional publication together. Current permissions and publication guards still apply. There is no separate CLI apply command. Editing, querying the Pipeline directly and evaluating never publish. Authorized live-input document updates retain their automatic path using the Deployment's explicitly selected configuration, not the changing working copy. Evaluation scores do not authorize releases.

Suppose Alice starts an automatic update, then switches the deployment to manual mode. The delayed build may finish, but its old publication authority cannot move traffic. Switching back to automatic admits fresh work under current controls; it does not revive that old job. Canaries and rollback require manual mode. See [Pipelines and Releases](development/pipelines-and-releases.md) for all transitions and concurrency examples, and [deployment records](development/data-model.md#releases) for saved state.

## Evaluation and feedback answer different questions

Offline evaluation can first generate starter cases from a frozen permitted sample of processed sources using embedded **Ragas**. Users review the proposed question, answer, and exact source passage; accepted revisions form the default regression benchmark. Generation, review, and evaluation are separate optional actions, not first-answer prerequisites.

A **frozen benchmark** fixes the cases used by a run. Comparisons execute both selected inputs afresh against the same benchmark and evaluator revisions. Either side can be a ready pipeline version or a fixed execution-input snapshot with verified dependencies. Ragas claim-based faithfulness measures support in the final context actually sent to generation; deterministic passage coverage and citation checks remain separate. All nested model calls use ModelGateway with explicitly selected connections. Source-inspected compatibility, calibration, and runtime integration still need qualification under [ADR-0051](adr/ADR-0051-use-ragas-for-generated-tests-and-faithfulness-evaluation.md).

Online feedback records what the originating principal thought of a particular live answer. Direct Pipeline queries and evaluation results stay outside production feedback statistics. There is one current rating per answer and originating principal; editing it replaces the rating rather than adding a vote. A shared application account is one principal, not proof of how many humans it represents. Late feedback remains attached to the version that produced the answer. Feedback does not automatically change releases.

Use [Evaluation](development/evaluation.md) for comparisons, denominators, and history, and [Answer feedback](development/answer-feedback.md) for ratings and reporting. Their records are defined in the [data model](development/data-model.md).

## Interfaces share application behavior

FastAPI generates the authoritative native OpenAPI 3.1.x contract. [ADR-0055](adr/ADR-0055-deliver-cli-first-v1-through-openapi-generated-clients.md) selects a Rust CLI and small Ory account UI for v1; full Studio follows later using the same accepted behavior. Application clients are generated from OpenAPI, with no generator package selected here. Backend work continues independently. [The delivery plan](development/cli-delivery-plan.md) maps accepted requirements to their backend, client and qualification issues; accepted requirements are not implemented guarantees.

MCP supplies a thin interface inside the existing API process for `query_deployment` and `get_answer_receipt`. Supported clients provide configured application credentials through headers and preserve business retry keys. Tool arguments cannot establish another identity. HTTP and MCP share application use cases, permissions, release routing, ModelGateway, and receipt behavior.

The optional [CLI application-connection journey](https://github.com/matejpalenik/inframeld/issues/161) reviews an application's access before explicitly issuing a credential and offering a separately approved live test. It never exports the human's Hydra login or grants Pipeline Query/release authority to an integration with only Deployment Query. An application may receive explicit Pipeline Query authority for the supported HTTP/CLI path; MCP's two-tool scope remains unchanged. Human CLI OAuth does not imply MCP OAuth discovery, support for every desktop client, verified end-user delegation or replacement of Inframeld application keys.

See [API contracts](development/api-contracts.md), the implemented [HTTP error foundation](development/error-handling.md), [pagination](development/pagination.md), and [MCP](development/mcp.md) for exact contracts and pending interoperability qualification.

## Failures and operations are part of the design

Long-running work is saved as durable jobs so a browser closing or worker restarting does not erase admitted work. Jobs have controlled attempts; only the current authorized attempt may publish a result. Database transactions stay short, with external work outside them.

**Idempotency** means recognizing a repeated request as the same operation. After a lost response, the same caller, key, and request meaning can find the original outcome. The same key with different content conflicts. An expected revision separately detects whether another command changed the state first. A timeout after a paid model request was dispatched does not prove the provider did no work. Uncertain outcomes cannot simply be retried as new work. A repeated answer request can return receipt-only status without replaying a saved full answer. Read [Jobs and idempotency](development/jobs-and-idempotency.md).

PostgreSQL owns application state, Chroma holds derived vectors, and SeaweedFS provides object storage through the application’s S3 boundary. Required state and encryption keys must be recovered coherently. Restoring older data can restore old permissions too, so access stays restricted until required security reconciliation is complete. Numerical recovery targets remain provisional; this documentation has not certified capacity or recovery performance.

## Reading paths

Choose the next document by your question:

- **Understand a workflow:** [Onboarding](development/onboarding.md) → [Knowledge](development/knowledge-lifecycle.md) → [Indexing](development/indexing.md) → [Pipelines and Releases](development/pipelines-and-releases.md).
- **Iterate before release:** [Working configuration and direct queries](development/pipelines-and-releases.md#working-configuration), [working-configuration evaluation](development/evaluation.md#comparison) and [CLI development loop](https://github.com/matejpalenik/inframeld/issues/172).
- **Understand evidence:** [Answer feedback](development/answer-feedback.md) and [Evaluation](development/evaluation.md).
- **Implement a boundary:** [Application structure](development/application-structure.md), [API contracts](development/api-contracts.md), [MCP](development/mcp.md), and [Jobs and idempotency](development/jobs-and-idempotency.md).
- **Understand security:** [Access control](development/access-control.md), [Model connections](development/model-connections.md), [Ingestion security](development/ingestion-security.md), and [Retention and deletion](development/retention-and-deletion.md).
- **Run or recover the installation:** [Deployment](development/deployment.md) and [Upgrades and recovery](development/upgrades-and-recovery.md).
- **Find exact records or rationale:** [data-model.md](development/data-model.md) and the [decision records](adr/README.md).
- **Name and recreate resources:** [Names, display names and IDs](development/data-model.md#resource-naming), [configuration portability](development/configuration-portability.md) and [protected dataset transfer](development/evaluation.md#dataset-portability). Accepted scope is separate from pending exact schemas and runtime qualification.
- **Observe and control spending:** [Operational/workload tracing](development/observability.md) and [gateway estimates and budgets](development/model-connections.md#spending).
- **Implement the CLI-first release:** [Delivery plan](development/cli-delivery-plan.md), [Definition of Done](development/definition-of-done.md) and [issue template](../.github/ISSUE_TEMPLATE/implementation.md).
- **Maintain documentation:** [Documentation maintenance](development/documentation-maintenance.md) and [skill reading routes](development/documentation-maintenance.md#skill-reading-routes).

The ADRs explain choices. The guides explain current behavior. The data model explains records. Current guidance is complete without a separate documentation archive.
