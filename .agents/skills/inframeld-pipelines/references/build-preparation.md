# Build a ready version without granting publication

Alice explicitly builds her saved configuration. Pipelines captures those inputs and prepares a complete immutable version. Releases separately decides whether the version may become live.

<a id="build-and-target-selection"></a>

## Build and target selection

The CLI coordinator selects the sole live Deployment or requires a choice when there are several. Never fan out. With none, ordinary Build leaves an unpublished version. Existing first-publication onboarding retains its separate creation authority. No separate CLI apply command is required.

The underlying build takes caller-captured authorized configuration/corpus. Explicit CLI Build supplies current saved settings. Document-triggered work supplies the Deployment-selected configuration. The common build must not re-resolve current working settings.

Build verifies readiness but cannot move traffic alone. Manual mode leaves ready output, while Automatic coordinates separate conditional publication under captured/current permissions. A denied policy-controlled automatic workflow cannot silently downgrade to another behavior.

Edits, restores, direct queries and evaluation neither publish nor supersede pending publication. Development-only documents stay outside live-watched collections. Re-enabling Automatic reviews the currently serving version's configuration first, not a stale automatic binding. A different saved selection is explicit.

<a id="freeze-and-build-a-version"></a>

<a id="build"></a>

<a id="2-freeze-and-build-a-version"></a>

## Freeze and build a version

A **build** prepares fixed settings for retrieval-augmented generation: finding document evidence, then generating an answer from it. It neither compiles customer code nor reads a Git branch.

The user-facing `inframeld build` workflow captures the saved configuration and follows the selected Deployment's policy. In Manual releases it leaves a ready version for explicit release. In Automatic updates its authorized admission requests preparation and a later conditional publication attempt. The underlying build operation only establishes readiness in both cases. An authorized completed document update may also invoke that operation using its Deployment's explicitly selected configuration, never the latest working copy.

For example, Production follows saved cfg_17 while Alice experiments with working cfg_18. A watched-document update supplies cfg_17 plus its exact admitted corpus to the underlying build. An explicit CLI Build reviews and captures current saved cfg_18 instead. The underlying operation validates the caller's frozen selection. It must not look up the working pointer and replace cfg_17. Both paths preserve current authorization, shared-current connection checks, verified preparation and separate release authority.

<a id="step-1-choose-the-exact-inputs"></a>

### Step 1: Choose the exact inputs

Alice reviews the Pipeline's current saved configuration: processing and embedding profiles, retrieval and reranking options, prompt, generation connection and settings, and the exact collection revisions resolved from its corpus selection. Build does not accept an evaluation run as its configuration source. Unsaved editor changes and temporary per-request overrides are excluded.

A **collection revision** identifies an exact set of document versions. Processing and embedding profiles identify how those documents are prepared for search. Retrieval and reranking settings control how evidence is found and ordered.

Editing the configuration does not change the deployed version. If earlier evaluation used different settings, prepared-data bindings or corpus, show that difference. A sample-only evaluation does not validate a full-corpus build. Lack of a matching evaluation is a warning, not a required judge call or automatic rejection. Even matching inputs do not guarantee identical external model behavior.

Include admitted/observed connection access revisions in that comparison. The same Pipeline settings with changed connectivity are not evidence of the same evaluated environment. A changed reviewed access revision during preparation or before a pending conditional publication requires new admission/review, not silent approval of newer settings. A separately committed connection update can already affect an existing live version. It does not authorize an unrelated pending publication. Readiness-only storage recovery of previously captured payloads remains distinct from publication authority.

<a id="select-the-publication-target-deliberately"></a>

### Select the publication target deliberately

The CLI target selects an installation. A Deployment selects a live serving endpoint inside the selected project. A direct Pipeline query endpoint is not a Deployment and is never a publication target.

| Deployments associated with this Pipeline | Build behavior |
| --- | --- |
| **Exactly one** | Resolve that Deployment and show its mode, current version and expected revision before admission. |
| **Several** | Require a choice. An interactive client may offer authorized choices. A script supplies the explicit Deployment. Never fan out implicitly or choose the first result. |
| **None** | Build an unpublished ready version. Do not create a live endpoint or invent release authority. |

An explicitly supplied Deployment must refer to this Pipeline in the same project and satisfy current Access checks. Unavailable or unauthorized selection fails without falling back to another target. Visibility filtering must not convert an ambiguous selection into silent publication elsewhere. The existing first-default-publication workflow is a separately authorized exception to the no-creation rule, as described in [Onboarding](../../inframeld-releases/references/deployment-creation-and-defaults.md#default-route).

Direct Pipeline querying needs no release authority. A manual build needs its ordinary Build and input rights. A policy-controlled automatic build also needs Manage releases on the selected Deployment. Missing publication authority fails that requested workflow instead of silently downgrading it to an unpublished build. Show the selected mode and consequence in both human and machine output. There is no separate CLI apply command.

<a id="step-2-validate-and-freeze-the-build-request"></a>

### Step 2: Validate and freeze the build request

Alice selects Build after reviewing the saved inputs and selected target's policy. The server captures those inputs, expected configuration/corpus and Deployment/control revisions, caller, request identity and any automatic-publication authority together. For automatic document updates, the source operation supplies its separately reviewed exact selection.

The server validates and saves the request. It may reserve the name P13 immediately, but P13 cannot serve while its build is pending.

Retries find the same build and target. To use later edits, Alice makes a new request rather than changing an already accepted build's inputs. If the reviewed configuration or publication policy changed before admission, reject the stale decision. Never refresh revisions and retry consent automatically.

<a id="step-3-reuse-compatible-results-and-create-what-is-missing"></a>

### Step 3: Reuse compatible results and create what is missing

The worker reuses compatible, ready processing results and **index materializations**, the prepared search data for the selected documents and profiles. It creates only missing results.

A prompt change or a change to **top-k**, the number of retrieval results requested, can reuse the whole index. A changed document needs new chunks and vectors. Changing the embedding profile may require embedding the entire selected corpus.

**The interface must not imply that every build is cheap or only processes a small change.**

<a id="step-4-verify-readiness-and-publish-immutable-bindings"></a>

### Step 4: Verify readiness and publish immutable bindings

After checking materializations, profiles, stored-file references, and compatibility with the query contract, Inframeld saves P13's complete, immutable bindings.

Until those checks pass, P13 is unavailable for version-based evaluation or live serving. This does not prohibit independent direct-query/evaluation with a complete execution-input snapshot and verified bindings. The build job reports progress and failure. A required dependency lost later can still make either a ready version or an execution-input snapshot unavailable.

Saving ready bindings does not release P13. The underlying build never changes Deployment references or sends customer traffic to its result. A user-facing Automatic Build workflow next requests a separate conditional Releases transition using its captured authority. A manual build stops ready and unpublished. Even attaching a ready version as a candidate is a separate release action.

Evaluation separately records the benchmark and evaluator used. Running it does not change P13's serving configuration.

<a id="expose-preview-and-policy-controlled-build-without-duplicating-execution"></a>

<a id="expose-pipeline-queries-and-policy-controlled-build-without-duplicating-execution"></a>

### Expose Pipeline queries and policy-controlled Build without duplicating execution

The [query-to-release lifecycle](working-configuration.md#working-configuration) requires protected application operations for working configuration read/edit/history/restore, direct-query preparation/execution, working-configuration evaluation and Build admission. A direct Pipeline query API operation is not an additional live Deployment or service. Ordinary live-query routing and the two existing MCP tools stay unchanged. No Pipeline Query access is added to a customer query through an unchecked override.

**Query on a Pipeline** runs its working configuration. **Query on a Deployment** uses that Deployment's ready-version serving path. These are separate permissions on exact resources, not an Execute experiments operation.

Humans and applications may receive either permission. Both still need current source and model access, an active account and sufficient budget. A credential with permission only on a Deployment cannot query the Pipeline directly. An application explicitly granted Pipeline Query can use the supported HTTP or CLI path.

Inspecting query traces requires `inspect-query-traces` on the exact Pipeline or Deployment, separately from `query`. None of these capabilities adds to MCP's two existing tools. The [reviewed Access catalogue](../../inframeld-access-models/references/actions-and-initial-grants.md#reviewed-capability-catalogue) selects these identifiers/targets. The Pipeline and tracing tickets retain their wire-representation work.

Inputs identify the selected Pipeline, expected saved revision, explicit permitted temporary overrides, exact source selection and ordinary operation context. Snapshots/results expose whether execution was a direct Pipeline query, evaluation or Deployment query, with exact effective-input identity, readiness, usage, safe failure and operation/job references. Build accepts the current saved Pipeline configuration and resolved corpus, not a run ID or a hidden copy of temporary overrides. Its public workflow selects a Deployment and captures publication policy/authority, while invoking readiness-only preparation and separate Releases operations internally.

That current-working input rule describes the explicit CLI Build workflow, not the common readiness-only operation. Automatic document-update admission supplies its Deployment-selected saved configuration and exact corpus to that same operation. Its contract must accept the authorized captured input without re-resolving the mutable working pointer. The Build specification gate records both callers and their distinct selection authority.

<a id="build-only-the-saved-configuration-the-user-selected"></a>

### Build only the saved configuration the user selected

After setup, Alice can edit the Pipeline's revisioned working configuration, query the protected direct Pipeline query API and evaluate it before creating a release version. [Pipelines and Releases](working-configuration.md#working-configuration) owns this loop. `inframeld build` captures the current saved configuration and corpus shown to Alice, not a run ID or unsaved per-request overrides. It follows the selected live Deployment's mode, with no separate CLI apply command. Explain when changed embedding/chunking requires preparation of the whole corpus and when earlier evaluation does not match these inputs.

Editing/saving/restoring working settings, preparing direct-query dependencies, evaluating, or testing a model role does not start publication. Automatic document updates keep the Deployment's explicitly selected configuration. Development-only uploads must not silently modify its watched collections. Replacing a provider credential changes current access to the service, but neither creates a pipeline version nor silently releases one or selects another model.

This later development loop is not a new setup prerequisite. Initial private provisioning, authorized automatic first publication and optional Finish remain unchanged. An ordinary Build with no live Deployment creates an unpublished version. It does not impersonate setup's separately authorized create-and-bind operation. A direct query can execute without a Deployment once its own inputs and dependencies are ready, but it must never be labelled a live/default answer.
