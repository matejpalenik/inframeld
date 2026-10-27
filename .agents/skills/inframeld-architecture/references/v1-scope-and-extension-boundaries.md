# V1 scope and extension boundaries

<a id="v1-scope-and-extension-boundaries"></a>

Alice wants a useful private support assistant. V1 delivers the backend, a Rust CLI and the small Ory account UI needed for human login. A future Studio uses the same contracts. The boundaries below keep that product practical for one maintainer.

> **Status:** accepted behavior is stated separately from proposed representations and qualification work. Existing Python types, generated OpenAPI and migrations own implemented shapes. Pending decisions are not accepted by this reference.

<a id="what-remains-outside-this-design"></a>

### What remains outside this design

**Deferred features:** application-driven resource provisioning, product-facing non-query diagnostic browsing, verified user delegation, third-party OAuth/MCP onboarding, different permissions per key, nested groups, custom roles, general policy languages, and permissions for individual document chunks. Backend human bearer verification is implemented. The complete first-party Hydra login and credential lifecycle still need runtime implementation and qualification. Keycloak and ZITADEL are not alternative deployment profiles under the Kratos-plus-Hydra decision.

Future enterprise options could include federation, separate identity providers per organization, SAML/SCIM integration, managed operation, and governance features. These are possibilities, not shipped capabilities or reasons to restrict basic secure OSS operation. Enterprise deployments could use the same identity technology, but migration would still need its own validation. User delegation is deferred by sequencing, not declared permanently enterprise-only.

**Still to specify or test:**

- Exact public schemas, treatment of links to private resources and bounded views/history within the fixed capability catalogue.
- Remaining source, collection, contributor, project, group, and application administration details.
- Application-key implementation under the [accepted credential dispatch](../../inframeld-access-models/references/credential-dispatch.md#credential-dispatch) and [key contract](../../inframeld-access-models/references/application-key-contracts.md#application-key-contract), plus runtime qualification of the [human CLI protocol](../../inframeld-access-models/references/human-cli-login.md#cli-client-registration) and [duration defaults](../../inframeld-access-models/references/human-cli-credential-lifecycle.md#cli-credential-lifecycle), including the full setting inventory. Human cookie/bearer dispatch is already implemented.
- User admission, identity verification, handover, and recovery workflows.
- Behavioral tests for administration, handover, recovery, simultaneous changes, permitted document retrieval, and deployment integration, plus coverage for database constraints not exercised by the current relational tests.

An undecided detail never implies unrestricted administrator access or a permission covering every resource.

For database work, start with [Access records](../../inframeld-access-models/references/identity-and-grant-records.md#access). [Application structure](../../inframeld-application-contracts/references/components-and-services.md) explains code ownership, and [API contracts](../../inframeld-application-contracts/references/http-mcp-and-generated-clients.md) covers HTTP behavior and adapters. [Deployment](runtime-deployment-and-storage.md) explains infrastructure boundaries, [model connections](../../inframeld-application-contracts/references/model-gateway-and-connections.md) covers outbound secrets and destinations, and [retention](../../inframeld-knowledge/references/deletion-and-retention.md) covers cleanup and history. The [ADR index](../../../../docs/adr/README.md) preserves rationale and historical evidence.

The shared Access foundation defines the permission rules, application contracts, and database constraints used by the surrounding workflows. Human browser sessions integrate through Kratos. The accepted CLI path adds Hydra with the qualification limits above. Private defaults belong to onboarding. Grant changes and handovers use Access administration. Knowledge applies document-access checks when it builds a permitted corpus, and the incoming-credential workflow manages application keys. Each domain adds its own real resource tables and grants. Describing these workflows here does not mean they are all implemented.

<a id="preserve-internal-extension-contracts-without-implementing-a-plugin-platform"></a>

### Preserve internal extension contracts without implementing a plugin platform

Keep the existing typed internal contracts:

| Contract | Responsibility and v1 scope |
| --- | --- |
| **`DocumentProcessor`** | Document conversion, with a built-in adapter. |
| **`Chunker`** | Bounded chunk production, with a built-in adapter. |
| **`Reranker`** | Candidate scoring/ordering, with explicit local cross-encoder, hosted and `none` choices under [ADR-0056](../../../../docs/adr/ADR-0056-support-explicit-local-hosted-or-disabled-reranking.md). Hosted calls retain ModelGateway enforcement. |
| **`PipelineHook`** | A synchronous, blocking stage contract with explicit timeout, egress, and failure behavior. It is not a privileged arbitrary-code runtime. |
| **`WebhookDispatcher`** | An asynchronous notification contract. Subscriptions and delivery remain deferred. |

A **synchronous, blocking hook** makes the pipeline wait for that stage to finish. Its timeout, outgoing-data rules, and failure behavior must be explicit. The internal interface does not permit remote hooks or user-supplied privileged code.

An **asynchronous webhook** would send a notification separately, without controlling the running pipeline. V1's in-app release workflow has no selected need for callbacks. The dispatcher interface therefore adds neither a delivery service nor a requirement for external CI.

Do not implement custom chunker registration, a plugin marketplace, arbitrary pipeline graphs, or remote hook execution. Custom evaluators also remain deferred under [Comparing pipeline versions with useful evidence](../../inframeld-evaluation/references/generation-and-review.md).

Evolve internal interfaces when a real feature needs them. If a public extension feature is selected later, version its contract then. These interfaces do not promise a plugin platform or require every future payload now.

<a id="provide-the-required-screens-without-adding-a-workflow-platform"></a>

### Provide the required screens without adding a workflow platform

The minimum product views are:

| View | Information and actions it provides |
| --- | --- |
| **Pipeline configuration and versions** | Working settings/revision/history, explicit save or restore, live version, and build progress or failure. |
| **Direct Pipeline query** | Effective saved settings and temporary overrides, exact inputs, preparation, answer/evidence/usage and protected execution attribution. No release controls are invoked by execution. |
| **Pipeline tests** | Test cases and the saved benchmark revision. |
| **Run history** | Evaluation runs associated with their execution-input snapshot or ready version, with current-access inspection and unavailable-content outcomes. |
| **Comparison and case detail** | Paired results, individual case details, and case history. |
| **Deployment** | Current, candidate, and previous targets. Cohort allocation. Explicit release-transition actions. |
| **Answer feedback** | CLI v1 counts, coverage, permitted comments and explicit own-answer rating/correction from [Understanding feedback on answers](../../inframeld-pipelines/references/answer-feedback.md), kept distinct from offline evaluation. A future Studio panel uses the same contract. |

The screens combine existing PostgreSQL records into views. They add neither services nor alternative owners of business state.

[Evaluation](../../inframeld-evaluation/references/generation-and-review.md) owns comparison evidence. Releases owns the rules every release change must preserve.

The required views, actions and old/new change presentation below are accepted. Remaining layout details, polling frequency and numerical resource budgets still need implementation choices and testing.

<a id="deliberately-deferred-capabilities"></a>

### Deliberately deferred capabilities

The current workflow does not require Inframeld to hand off work to an external workflow system. V1 therefore defers:

- **External workflow integrations:** webhook delivery, detached external notifications, GitHub and pull-request integration, runner coordination, and repository events.
- **General orchestration infrastructure:** a general-purpose scheduling or workflow platform.
- **Additional release automation and governance:** evaluation on every save or build, automatic promotion or rollback, traffic-ramp policies, continuous production judging, and multi-step approval governance.

Preserve the planned interface-only `PipelineHook` and `WebhookDispatcher` boundary without shipping executable hooks, subscriptions or a delivery service. These are accepted planned interfaces, not a claim that the current application implements them.

These deferrals preserve the in-app decisions and saved history described above. Automatic updates remains an authorized build followed by a checked publication attempt. It does not promote based on scores or introduce a general release-policy engine.

API and clients expose exact working-configuration/build inputs, progress, current readiness, release revisions, publication mode, pending updates, and defined conflicts. Reopening the CLI watcher or future Studio recovers that saved progress. Saving working settings does not authorize building or publishing them. CLI development loop illustrates the full loop.

For a manual change, Alice first compares the working configuration against P12. She saves any successful overrides, then builds P13 from the current saved settings. If P13 differs from the evaluated inputs, report that fact. She may explicitly compare P13 and P12 again. She can attach P13 at 0%, increase traffic, reject it while keeping P12, or promote it. [Evaluation](../../inframeld-evaluation/references/generation-and-review.md) explains fair comparisons and [feedback](../../inframeld-pipelines/references/answer-feedback.md) explains online counts. A direct Pipeline query is not the zero-traffic candidate: that candidate is already a release-ready version attached through Releases.

<a id="decisions-and-scope"></a>

<a id="decision-map"></a>

<a id="12-decisions-and-scope"></a>

## Decisions and scope

[ADR-0051](../../../../docs/adr/ADR-0051-use-ragas-for-generated-tests-and-faithfulness-evaluation.md) replaces the historical [OpenEvals decision](../../../../docs/adr/ADR-0030-use-openevals-for-groundedness-evaluation.md). [ADR-0031](../../../../docs/adr/ADR-0031-compare-fresh-executions-against-frozen-benchmarks.md) still requires fresh comparisons. [ADR-0052](../../../../docs/adr/ADR-0052-separate-experimental-execution-from-release-ready-pipeline-builds.md) partially supersedes only its ready-version-only restriction. CLI starter-evaluation journey illustrates starter evaluation and CLI development loop the development loop. [the data model](../../inframeld-evaluation/references/records.md#evaluation) owns records.

Manual blank-form authoring, automatic multi-hop/negative synthesis, correctness/relevance judges, custom evaluator platforms, ensembles, optimizers, automatic remedies, and external Phoenix/LangSmith exporters remain deferred. These exclusions do not defer starter generation, review, or claim extraction. No hosted evaluation account, graph database, separate runner, or workflow engine is required.

Official background: [single-hop generation](https://docs.ragas.io/en/stable/howtos/applications/singlehop_testset_gen/), [prechunked input](https://docs.ragas.io/en/stable/howtos/customizations/testgenerator/prechunked_data/), [faithfulness](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/faithfulness/), and [runtime configuration](https://docs.ragas.io/en/stable/howtos/customizations/run_config/). Use the version-bound source evidence in the Evaluation gateway reference when rolling examples have different API shapes.

<a id="keep-custom-model-access-in-oss-and-local-processing-separate"></a>

### Keep custom model access in OSS and local processing separate

The open-source product includes custom and private-network endpoints, customer language models, custom certificate-authority trust, customer-supplied keys (BYOK), and the core release workflow.

These work under Apache-2.0 without `/ee`, a licensing server, or a provider account funded by Inframeld. Future enterprise routing or administration features must not remove them from OSS.
