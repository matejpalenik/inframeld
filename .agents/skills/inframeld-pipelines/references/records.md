# Pipeline configuration, execution inputs and receipts

<a id="pipeline-configuration-execution-inputs-and-receipts"></a>

Alice edits working revision 18 while an earlier question runs. That question keeps its captured settings and corpus. A release-ready version and a live answer receipt record different events and do not follow the new working revision.

> **Status:** accepted behavior is stated separately from proposed representations and qualification work. Existing Python types, generated OpenAPI and migrations own implemented shapes. Pending decisions are not accepted by this reference.

<a id="pipelines"></a>

<a id="pipelines-configuration-answers-and-feedback"></a>

## Apply accepted PD-PIPELINES-01

Accepted [PD-PIPELINES-01](decision-execution-build-receipt-contracts.md#approved-resolution) selects this workflow's detailed contract. Alice starts a question using saved configuration 17. Bob saves configuration 18 while it runs. Separately, Production may serve a ready version using configuration 16. The application must keep each execution's chosen meaning and distinguish a ready build from permission to publish it. If an answer response is lost, a retry must not buy another answer. Apply its exact bounds, current-state checks and failure outcomes. Native implementation and qualification remain separate.

## Pipelines: configuration, answers, and feedback

A **Pipeline** is a stable named configuration with one current saved working revision. Each immutable **PipelineVersion** is a release-build result saving exact collection revisions, one processing profile, one embedding profile, an optional configured reranker, retrieval limits, prompt, generation settings, and the complete configuration fingerprint. `PipelineIndexBindings` point to compatible ready materializations without copying them. Direct Pipeline querying uses the records below without creating a PipelineVersion or Deployment.

Missing, stale, failed, retired, or incomplete dependencies block serving. Changing a prompt, retrieval setting, or reranker can reuse compatible vectors. Changing source bytes or model meaning creates new history. Replacing a credential alone does not. The [serving guide](answer-execution-and-receipts.md#serving) owns live permission and health checks.

<a id="experimental-execution-records"></a> <a id="query-execution-records"></a>

<a id="keep-working-revisions-execution-snapshots-and-release-versions-distinct"></a>

### Keep working revisions, execution snapshots and release versions distinct

Alice saves configuration revision 18 and queries it directly with an override. If she likes the result, she saves those settings as revision 19 before Build. The query itself creates neither revision 19 nor a release version.

The following are accepted **logical record responsibilities**, not implemented tables or classes. Captured inputs record what a query or evaluation used, within the required storage bounds. There is no separate Experiment aggregate, resource, lifecycle or permission. The older section anchor is retained for existing links.

| Concept | Minimum responsibility |
| --- | --- |
| **Working configuration revision** | Pipeline/project identity, revision identity, predecessor and optional restored-from reference, actor/time, saved corpus selection, processing/embedding profiles, reranker, retrieval limits, prompt, selected connection IDs and model settings. The Pipeline identifies one current revision. Save/restore uses an expected current revision and creates new history. Shared access configurations are not pinned by this record. |
| **Captured execution inputs** | Pipeline/project, originating working revision where applicable, explicit overrides and complete effective configuration/fingerprint, exact resolved source/collection revisions, profiles, initiating actor and operation identity. No release version or Deployment is required. |
| **Prepared query bindings** | Exact compatible materialization/generation references established before question execution, readiness/progress outcome and bounded artifact retention references. Freeze chosen execution bindings once complete. Preparation cannot mutate live artifacts or change admitted source/settings. Failed preparation does not create an executable snapshot. |
| **Direct-query outcome** | Snapshot and operation identities, direct-query/evaluation purpose, outcome, timestamps, bounded safe usage/error metadata and references to separately protected result/trace records where applicable. No fictional live version, cohort or publication authority. |
| **Policy-controlled Build admission** | Current saved configuration revision and resolved corpus, expected reviewed revisions, chosen Deployment or explicit absence, captured mode/control/request identity and initiating authority, plus ordinary build/publication child-operation identities. It does not use a run ID as configuration. |

The Pipeline owner records configuration and execution provenance. Indexing owns readiness and reusable data. Evaluation owns benchmark runs and evidence. Releases owns any live target selection. An execution input distinguishes a ready PipelineVersion from an execution-input snapshot. The shared execution path receives complete fixed Pipeline inputs from either, not an untyped bag of overrides or a mutable working-configuration lookup during retrieval. Both forms select stable connection IDs. Admission records current access revisions as execution preconditions. Subsequent calls must satisfy [shared-connectivity freshness](../../inframeld-application-contracts/references/model-dispatch-and-destinations.md#dispatch-freshness), not execute historical access settings. Safe actual observations belong to the execution outcome, independently of diagnostic trace capture.

Policy-controlled Build admission in the table describes the explicit CLI workflow. The underlying readiness-only build instead retains whichever exact authorized saved configuration and corpus its owning caller captured. Automatic document-update admission supplies the Deployment-selected configuration, which can differ from the current working revision. Neither operation follows a mutable configuration pointer after admission, and neither treats an evaluation run or unsaved override as a release-build source.

Keep configuration identity, effective input fingerprints and actual physical bindings distinct. Equal settings with a different corpus, scope or fresh numerical generation are not proof of identical evaluated inputs. Build can reuse verified artifacts but must disclose mismatches with referenced evaluation evidence. Retained snapshots can support fresh comparisons. They are not release targets or a build-from-run API.

Secrets never belong in these records. History is bounded by retention and current access. Restoring configuration creates a new current revision and does not resurrect erased content, expired artifacts or credentials. Snapshot retention does not pin every historical index forever. Active operations use ordinary bounded pins. Explicit evaluation evidence and diagnostic traces keep their separate capture, inspection and erasure rules. Pipeline Query/inspection identifiers and creator grants are settled in the [Access contract](../../inframeld-access-models/references/actions-and-initial-grants.md). Exact physical storage, API schemas, resource bounds and runtime enforcement remain delivery work under their owning guides.

### Consume prepared materializations

Accepted [PD-INDEXING-01](../../inframeld-indexing/references/decision-capability-binding-contracts.md#approved-resolution) gives each captured execution a complete set of exact scoped materialization references and bounded verified projections. Large inventories remain immutable paged manifests. Active execution pins use the shared retention gate and do not freeze authority. Missing/retired required data fails instead of selecting latest data or silently reconstructing historical bindings. Accepted PD-PIPELINES-01 owns capture, preparation continuation and receipt finalization.

<a id="record-the-actual-serving-selection-before-accepting-feedback"></a>

### Record the actual serving selection before accepting feedback

An answer receipt records the version that answered and why it was selected. For example, a canary candidate may answer Alice even if it never becomes Production's current version.

| Receipt information | Purpose |
| --- | --- |
| **Server-generated, unpredictable `answerId` and operation identity** | Identify the response and its originating operation. |
| **Organization/project and originating stable principal** | Establish ownership and access scope. A principal is the verified human or application identity recognized by Inframeld. |
| **Pipeline-version identity** | Identify the exact version that produced the response. |
| **Safe actual connection observations** | Record selected connection IDs and the access/credential revisions and model identities actually used, where available. A version can run before and after a shared access update without becoming a new version. These observations contain no secrets, full model inputs or hidden diagnostic trace stream. |
| **Deployment identity and revision** | Record which serving target and state selected that version. |
| **Rollout identity and actual cohort** | Preserve the particular canary assignment. The rollout may be absent when there is no canary. |
| **Creation time, completion outcome, and expiry** | Establish when the response originated, how execution finished, and how long the receipt remains eligible and retained. |
| **Bounded identities of every document/version used in final generation context** | Support current access checks, including for sources that were used but not cited. |

The **final generation context** is the evidence sent to the answer model. Record every source it contains, including uncited ones. A later feedback comment might quote evidence the answer did not cite.

<a id="reserve-the-identity-at-admission-finalize-before-releasing-the-response"></a>

<a id="reserve-the-identity-at-admission-and-finalize-before-releasing-the-response"></a>

### Reserve the identity at admission and finalize before releasing the response

```text
Admit query and reserve answer identity
    -> Record the selected version and release context
        -> Execute the query
            -> Finalize its safe completion outcome
                -> Release the completed response
```

Only a successfully finalized, eligible serving receipt accepts feedback.

| Execution outcome | Feedback treatment |
| --- | --- |
| **Successfully completed answer** | Eligible while the receipt is retained and currently accessible. |
| **Completed explicit insufficient-evidence response** | Eligible and labelled as insufficient evidence. This is a deliberate completed response, not a provider failure. |
| **Provider failure or uncertain operation** | Not an answer to rate. |
| **Offline evaluation execution** | Does not enter the production feedback denominator. |
| **Direct Pipeline query execution** | Does not create a live serving receipt eligible for production feedback or enter its denominator. Snapshot/operation attribution remains separate. |
