# ADR-0019: Default onboarding and reversible publication modes

**Status:** Accepted — private defaults and reversible Automatic updates / Manual releases. Implementation qualification is pending. **Date:** 19 September 2026. **Required approach:** Private first-use setup, persistent model credentials, and ordinary builds followed by separately authorized publication. **Source:** [Canonical architecture guide](../ARCHITECTURE.md). **Related:** [API contract](ADR-0002-product-owned-openapi-contract.md), [lineage](ADR-0003-immutable-rag-lineage-and-release-identities.md), [Access](ADR-0005-api-enforced-tenancy-and-authorization.md), [models](ADR-0006-byok-provider-boundary.md), [jobs](ADR-0007-durable-jobs-idempotency-and-recovery.md), [releases](ADR-0009-sticky-logical-canary-deployments.md), [bindings](ADR-0015-profile-specific-index-materializations-and-pipeline-bindings.md), [credentials](ADR-0020-persistent-outbound-credentials.md).

## Context

A new user should be able to configure models, save their credentials, upload local documents, and ask a question answered from those documents with citations. They should not need to understand Inframeld’s internal resource setup before receiving that first useful answer.

A **Pipeline** holds the configuration for retrieving evidence and generating answers. A **PipelineVersion** is a complete, immutable version of that configuration and its prepared data. A **Deployment** is the serving target that selects which version answers requests. Creating a Pipeline does not create a ready version or a serving endpoint.

From first principles, **hiding setup complexity must not hide incomplete data, remove permission checks, or give background work unlimited authority to publish**. The simple path therefore needs real private resources and the same verified builds as the rest of the product. It also needs a clear choice between automatically applying selected changes and reviewing releases manually.

## Decision

**Provision ordinary private starter resources for each admitted user. Start the default serving path in Automatic updates, where an authorized completed upload or configuration action requests a build and conditional publication. Allow users to switch to Manual releases and back without replacing their resources or endpoint.**

Users configure embedding and generation models, save any required credentials, upload their documents, and ask through the normal retrieval/generation path. An **embedding model** converts text into numerical vectors for search; a **generation model** produces the answer. No benchmark, evaluation, or judge configuration is required first. A benchmark is a set of test cases; a judge is a model used to assess answers.

This replaces the earlier first-publication-only policy. Keep the filename `ADR-0019-default-onboarding-and-first-publication.md` for existing links, but there is **no one-time publication permission and no separate Prepare and ask operation**.

Application services connect existing builds to separate publication commands. No new runtime service, scheduler, general policy engine, or quickstart retrieval implementation is introduced. The design is accepted; performance, concurrency, and usability still need testing.

### 1. Give each Deployment its own publication mode

Both modes use the same source versions, build behavior, ready pipeline versions, and query path. They differ in how a change becomes authorized to serve.

| Mode | Document changes | Pipeline configuration | Release control |
| --- | --- | --- | --- |
| **Automatic updates** | A completed, authorized batch requests a build and publication of its complete frozen selection. | **Save and apply** selects configuration and authorizes its update. Unrelated drafts are ignored. | Publish only the eligible, complete, ready result. Do not automatically run an evaluation or start a canary. |
| **Manual releases** | Admit new versions as unpublished inputs. | Save draft settings without changing traffic. | Use explicit Build, Compare, candidate/canary, promote/reject, and rollback actions. |

A **batch** is a bounded, fixed selection of files. **Frozen inputs** record exactly which source versions and configuration an operation will use; they do not change while it runs. A **canary** tries a candidate with a selected portion of traffic before promotion.

The default onboarding path starts in **Automatic updates**. An explicitly created Deployment defaults to **Manual releases**, unless its creator chooses Automatic updates. Both modes are available at creation and can be changed later.

**The mode belongs to the Deployment, not to the Pipeline.** Studio, Inframeld’s console, may present the choice alongside pipeline setup, but two Deployments using the same Pipeline retain independent modes and selected configurations. A change for one endpoint does not automatically update every endpoint using that Pipeline.

#### Follow selected documents, not every draft edit

An automatic-update binding records the source Pipeline, its selected configuration revision, and selected logical collections in the same project. A **logical collection** groups source documents. Each build freezes exact **CollectionRevisions**, immutable selections of document versions, and profiles from that binding.

This makes the difference explicit: the Deployment can follow authorized changes to its selected documents without following arbitrary draft configuration changes.

The starter flow presents its default mode without adding another release question. The upload action explains that complete changes become available automatically after preparation. A consuming application accepts that behavior: **its URL stays stable, while future answers may use newly published versions**. The API and Studio expose the mode, current version, and pending update.

### 2. Provision private resources through ordinary access rules

Use one installation organization. **Kratos** verifies human identity; Inframeld maps that verified identity and creates its normal scoped resources.

Secure bootstrap establishes the first verified human as installation administrator through a **one-time operator-controlled claim**. It does not give administration to the first arbitrary public registration. Later account admission follows the existing controlled account policy, not an assumed public SaaS signup flow.

When an admitted human first enters setup, create a **starter project** and a **project-local private group containing that human**. Grant project administration and the actions needed for setup, document use, model-connection management, build, and release within that project.

Other users receive different starter projects/groups. There is no installation-wide knowledge pool, and installation administration does not bypass document-read checks. These are ordinary project-owned resources, not another personal-tenant domain. Existing ownership-transfer and deletion rules apply if the creator leaves.

#### Make provisioning safe to repeat

After Kratos verifies the account, perform starter provisioning in one short PostgreSQL transaction. Use a unique ownership/purpose key such as:

```text
(organization, verified human principal, starter)
```

A **principal** is the stable verified identity the application recognizes as the caller. This key finds the same starter project on a retry. Recorded default bindings then identify its group, collection, preset, and pipeline by ID. A separate unique bootstrap claim establishes the one installation organization and administrator.

Do not hold the transaction open across Kratos or model calls. If it rolls back, a later request can complete the same scoped setup. If it committed but the response was lost, return the same IDs rather than create duplicates.

Keep completion and removal markers so an intentional deletion is not mistaken for unfinished setup. Database uniqueness and transactions provide this behavior; no distributed bootstrap coordinator is needed.

#### Store a real allowlist on every starter upload

Apply the private group’s **nonempty allowlist** on the server. An allowlist identifies groups permitted to access a document. The first-upload screen need not ask the user to select it, but each Document receives an explicit stored grant.

Changing the project’s upload default affects **future admissions only**. It must not rewrite existing document policies. A shared project can later select another permitted default through authorized access configuration. An empty allowlist never means public access.

The first connector uses explicitly selected Inframeld groups, without importing source-system access-control lists (ACLs).

No integration credential is issued or shared automatically. A project administrator may later create one with a document-group **ceiling**, the maximum scope safe for all of its consumers. It uses fixed application authority, not delegated end-user identity.

This establishes the minimum private setup only. It adds no enterprise organization administration, external group synchronization, nested groups, or role designer. Both publication modes use these same permissions.

### 3. Distinguish resources that exist from resources that are ready

A small **project-default binding** records stable resource IDs and an expected revision for detecting concurrent changes. It is application configuration on the ordinary project, not a duplicate set of domain resources. Display names are editable and never used as lookup keys.

Before the default Deployment exists, this binding holds the selected mode and publication control revision. First publication transfers that control state into the actual Deployment atomically. **There must never be two independent authorities for its mode.**

| Resource | State after authorized provisioning | What makes it usable or ready |
| --- | --- | --- |
| **Organization, project, and private group** | Ordinary records and creator membership. | Verified account/bootstrap authorization and the completed provisioning transaction. |
| **Default Collection** | An empty named collection referenced by project defaults. | An admitted batch produces an exact usable CollectionRevision. An empty collection is not evidence. |
| **Built-in ProcessingProfile** | An immutable conservative text-first preset. | Its pinned parser and assets pass normal readiness checks. No per-user profile editor is required. |
| **Default Pipeline** | A named root with incomplete draft configuration linked to the collection and preset. | Model roles and exact inputs are selected, and a successful build produces a complete PipelineVersion. |
| **Provider connection and credential** | No fictional valid credential or ready connection. | Required credentials are saved, endpoint policy permits the origin, and role-specific validation succeeds. |
| **EmbeddingProfile** | Absent until the model’s semantics and dimensions are established. | Validated embedding selection creates the immutable profile used for document and query embeddings. |
| **Generation configuration** | Incomplete until selected. | Connection revision, model, and settings are validated and frozen into build inputs. |
| **Materialization and PipelineVersion** | Absent. | Parsing, chunking, embedding, and index verification succeed for the frozen corpus and profiles. |
| **Logical default route** | A stable project-scoped address, initially unbound, with Automatic updates selected. | First publication creates and binds a genuinely ready Deployment. |
| **Deployment** | **Absent**, not an idle or fake-ready record. | An authorized creation commits one ready current version, with no candidate or previous target. |
| **Benchmark and judge** | Neither required nor silently configured. | The user later chooses comparison and configures its evaluator inputs. |

A **ProcessingProfile** defines document conversion and chunking. A **chunk** is a source excerpt prepared for retrieval. An **EmbeddingProfile** fixes the model behavior and numerical vector dimensions used for search. A **materialization** is the verified searchable data for the selected collection revision and profiles. The **corpus** is the selected body of documents.

#### Nondefault Deployments also start with a real ready version

An explicitly created Deployment selects a ready, compatible initial PipelineVersion and requires an authorized creation decision. Choosing Automatic updates also selects its update binding and authorizes a fresh update for any explicitly displayed pending corpus/configuration.

The ready initial version remains current while that update runs. If the selected inputs already match, report up-to-date without another model call. Creation must never treat an unfinished build as current.

The default logical route is the special case that can be displayed before its Deployment exists. It remains visibly not ready until first publication.

### 4. Save credentials and validate model roles separately

**Saving a credential and proving that a model role works are different operations.** A saved key can be unusable, and successful generation does not establish embedding support.

The simplest form lets the user enter one provider connection/key and select distinct embedding and generation model IDs. Share the connection when origin and authentication match. Otherwise configure separate connections without copying the secret to another origin automatically. An **origin** identifies the endpoint’s scheme, host, and port.

Validate generation and embedding independently through `ModelGateway`, the application’s shared model-call interface. Record the connection and credential revisions tested and the actual embedding dimensions.

Replacing or removing a credential invalidates its previous role-probe status. First-publication readiness checks the **current credential revision**, not a successful test of an older key. Changing the origin requires a new connection and explicit credential entry.

Capability probes are bounded model calls explicitly authorized by the configuration action. They are not an offline benchmark or a general qualification catalogue.

Persistent application-entered credentials use the accepted PostgreSQL/PyNaCl mechanism in [ADR-0020](ADR-0020-persistent-outbound-credentials.md). No valid connection is invented to bypass that setup.

#### Keep optional work out of the initial path

Use the existing explicit **`none` reranker** and a tested, bounded text-first processing preset. A reranker reorders retrieved candidates; `none` deliberately skips that optional step. Text-first processing favors files whose text is already present rather than requiring optical character recognition (OCR) of scanned pages.

Do not silently add profile/model downloads, a local language model, OCR, an optional reranker, or a judge. Richer settings use ordinary later configuration and versioning. Changing the embedding model creates a new profile/materialization; it is not a mutable switch on old vectors.

### 5. Resolve one default route through normal serving behavior

The recommended HTTP route is:

```text
POST /v1/projects/{projectId}/deployments/default/query
```

`default` is a reserved selector resolved by the same application service as an ordinary Deployment ID. It becomes bound to an actual Deployment only after first publication. It is not a fabricated Deployment row, version, or readiness state.

An authorized read of project defaults returns the ordinary resource IDs, current binding, safe readiness/progress, and next action. Check project/query permission **before** revealing setup information. An inaccessible project receives the normal non-enumerating result, which avoids revealing its existence or detailed setup state.

#### Before first publication, reject the query before admission

An unbound or not-ready alias returns **`409 deployment_not_ready`**, with a safe reason such as models required, documents required, preparing, failed, or explicit release required.

It does not generate an answer, create resources through GET/query, skip retrieval, or return a canned demonstration. This is a **pre-admission rejection**: no query/job/model side effect commits, and any provisional idempotency reservation rolls back. The caller can read setup status and retry after readiness; no completed answer is being replayed.

After binding and publication, a dependency that becomes unavailable follows normal unavailable behavior. Do not silently unbind the route or rebuild it as though setup never happened.

#### Identify what actually served, not the convenience alias

At query admission, resolve and pin the actual Deployment revision and PipelineVersion under ordinary retention and concurrency rules. A **pin** protects selected artifacts against routine cleanup while the admitted query uses them.

Responses and `AnswerReceipt` records identify the actual Deployment, revision, PipelineVersion, and cohort. A receipt records an answer operation’s origin and outcome; a cohort identifies its routing group. The alias never replaces those facts or grants additional access.

#### Deduplicate the requested route before selecting a fresh target

An **idempotency key** identifies a retry of the same requested operation. Authenticate and look up or reserve its record using the stable requested logical route, project, and principal **before resolving a fresh serving target**. The first admitted operation stores its actual target/version selection.

If that request is retried after promotion or explicit alias rebinding, return the original currently authorized operation/receipt. Do not reinterpret its key against the new target and dispatch another paid query. Rebinding means changing which actual Deployment the alias selects.

HTTP and MCP share this logical-route mapping. An alias request and an explicit Deployment-ID request are different requested routes; cross-route deduplication is not promised.

#### Keep HTTP, generated clients, and MCP aligned

Represent the alias in the authoritative OpenAPI contract and consume it through the externally generated SDK, the client library used by Studio.

For **MCP**, the Model Context Protocol, retain the existing two tools. The recommended selector is `deploymentId: "default"` with a required `projectId`; ordinary opaque Deployment IDs keep their existing meaning. Both interfaces call the same resolver/query use case and apply the same affinity and receipt rules. Affinity keeps a routing identity in a consistent canary cohort; it is not user authentication.

`get_answer_receipt` is unchanged. No third tool, mode-administration tool, or alternate retrieval engine is added. **The exact HTTP/MCP selector shapes remain implementation details recommended here; the onboarding behavior and two-tool scope are accepted.**

### 6. Authorize each complete update, not every uploader

**Automatic mode enables a workflow; it does not grant extra permissions.** Enabling it requires the normal build/deploy grants for the target and access to the selected inputs. Each source or configuration action that applies an update also requires its ordinary mutation permissions and those build/deploy grants.

Capture the initiating verified principal and authorization in the durable update. Recheck current scope and required permissions before dispatch and publication. Revoking the actor’s authority must prevent a previously queued job from publishing.

The starter creator already has the required project grants. A principal with ingestion-only permission can save source changes through the ingestion-only operation, but cannot publish them. Studio explains that applying them requires an authorized operator. Upload and query permissions never silently become deployment permission.

If several automatic Deployments select the same collection, the operation explicitly identifies the targets it is authorized to update. Each target has its own request and outcome; there is no cross-Deployment transaction or publication using another person’s authority.

#### Treat a completed batch as one complete selection

Use ordinary completed upload batches, not a continuous file watcher. Later files form another batch.

A partially failed batch may retain successfully admitted bytes, but **must not publish a silently smaller corpus**. The user retries safe work or deliberately revises the batch. Freeze exact source versions and the selected configuration at update admission, not mutable references to whatever is latest when the worker runs.

The first batch may reserve document identities through existing durable admission steps before the downstream build. Any failed admission blocks publication.

An explicitly requested S3 synchronization follows the same rule once it establishes a complete selected revision: an authorized apply action targeting the automatic Deployment admits the update. There is no scheduled polling feature or publication from each page of a partial sync.

Ordinary removal from a collection creates a new corpus selection. **Security revocation and explicit erasure are different:** ADR-0014 applies immediately and may invalidate the current version in either mode. The old version is not promised to keep serving deleted content.

#### Apply only the configuration the user selected

For model or pipeline changes, **Save and apply** freezes the displayed configuration for the target. Explain when an embedding-profile change may require work across the whole corpus.

Saving an unrelated draft, editing a form field, or running a capability probe is not an update trigger. Credential rotation is a live capability change, not a new pipeline version; it does not silently create a release or choose another model.

### 7. Build a ready version, then request publication separately

One small durable application operation records the actor, target, captured control revision, requested update identity, frozen inputs, and stable child operation IDs. A **child operation** is one constituent action, such as the build requested by the update.

```text
Authorized completed batch or Save and apply
    -> Durable update with frozen inputs and publication authority
        -> Ordinary source-admission and Build use cases
            -> Complete ready PipelineVersion
        -> Separate Releases publication command
            -> Publish only if the original request remains eligible
```

Progress distinguishes upload, preparation, ready version, and publication outcome. **A ready version whose publication was skipped is not an updated endpoint.**

The publication command belongs to **Releases**. It checks scope, readiness, input/target compatibility, current authorization, absence of a candidate, and the concurrency guards below.

| Publication case | Effect |
| --- | --- |
| **First default publication** | Create the actual Deployment and bind the route in the same short SQL transaction, transferring publication-control state. It has one ready current version and no previous target. |
| **Later eligible automatic publication** | Replace current and retain the former current as the designated one-step previous target. Do not manufacture a canary candidate or traffic ramp. |
| **Result identical to current** | Do nothing to the serving pointers, including the previous target. |

A **pointer** is a stored reference to the selected version. Record the initiating action, mode/control revision, exact versions, and automatic-publication outcome in ordinary history. Record that benchmark review was not part of this authorized update; do not invent a passed evaluation or manual approval. Scores and answer feedback never initiate publication.

Queries and receipts retain the actual version, Deployment revision, and cohort they selected even after another publication.

**Build publishes readiness only.** The update operation requests publication; Indexing and job-completion handlers cannot independently move Deployment pointers. Checkpoints and idempotency recover a crash after build or publication without redoing chargeable work. Frozen Chroma writes keep their safe exact-payload retry path, while ambiguous paid-model calls keep their explicit recovery requirement. Automatic mode changes neither rule.

### 8. Switch modes through explicit, concurrency-checked commands

A mode change requires authorization, an idempotency key, and an expected revision. The key identifies a retried command; the revision checks that its decision is still based on the current state.

Reject stale decisions rather than silently accepting a newer revision. Commit the mode change and its audit record atomically. **A mode change itself preserves current, previous, history, and the endpoint.** A subsequent authorized publication is a separate transition.

#### Automatic updates → Manual releases

Immediately invalidate pending automatic publication authority. Running work may finish a useful immutable version, but cannot publish it. Stop undispatched work when practical through existing cancellation/checkpoint rules; a provider call already sent cannot be promised canceled.

No re-upload or index copy is needed. A successful switch leaves the version then current in place.

Publication and switching can race:

| Which transaction commits first? | Result |
| --- | --- |
| **The switch** | The old automatic publication fails its guard. |
| **The publication** | It changes the Deployment revision. A switch expecting the old revision conflicts and leaves the mode unchanged. The user reloads and makes a fresh decision. |

The client must not replace the expected revision and retry blindly. **A rejected switch must not be displayed as automation disabled.** Switching is not rollback and does not undo publication that already committed.

#### Manual releases → Automatic updates

The action is **Enable automatic updates and apply pending changes**. Show the complete corpus and configuration to be applied, then atomically change mode and admit a fresh update for those frozen inputs.

Default the displayed configuration to the currently serving version, or to validated selected settings before first publication. Choosing a different saved configuration is explicit. Do not resurrect former automatic settings after manual releases changed them, or include unselected drafts.

Applying pending changes is part of this action, not a surprise deferred until the next upload. Missing models/documents or an incomplete selection prevents the command and leaves the mode unchanged, with an explanation of what is needed. The automatically provisioned default may still start automatic before inputs exist; it simply has no admitted update yet.

Any attached candidate, including one at **0%**, returns **`409 candidate_active`**. The operator first promotes or rejects it in Manual releases. Enabling automation must not secretly cancel a canary or change its percentage.

Keep the current version active until the fresh update succeeds. If that update fails, leave Automatic updates selected and display the failure; ordinary retry/supersession rules apply. If the selected inputs already match current, report up-to-date without rebuilding solely to toggle the mode.

**Never restore an earlier disabled job’s publication authority.** Enabling automation is a fresh decision even when it can reuse earlier artifacts.

#### Manual review, canaries, and rollback

Attaching candidates, changing canary traffic, promoting/rejecting candidates, and rolling back require Manual releases. In Automatic updates, return a clear mode conflict rather than changing mode implicitly.

Comparisons and history remain available in either mode. A comparison neither pauses automatic publication nor promotes its preferred result. Switch to Manual releases before a controlled review that needs the serving baseline to remain fixed.

Automatic publication retains the former current as previous. An operator can switch to manual and use the ordinary one-step rollback if its dependencies can still serve. Rollback consumes the previous pointer and leaves the mode manual.

Re-enabling Automatic updates later explicitly applies the selected inputs again and may replace the version just restored. Show that consequence. Neither rollback success nor a restart re-enables automation.

### 9. Publish only the newest request whose original authority still holds

Keep two small release-control values alongside existing jobs:

| Guard | What changes it |
| --- | --- |
| **Monotonically increasing control revision** | Mode switches, changes to the automatic-update binding, and explicit invalidation. |
| **Newest authorized update-request identity** | A newly authorized complete document batch or explicit apply action. Draft edits alone do not supersede work. |

These are guards, not a new family of domain objects. Reuse existing revision mechanisms where they provide these semantics.

A job captures both values and the expected serving revision when its execution is admitted. **Finishing a build cannot refresh those captured values to acquire new publication authority.**

#### Run at most one active automatic update per Deployment

If another authorized batch arrives, persist its complete frozen selection and mark it as the newest request. Older pending requests remain identifiable as skipped/canceled; do not execute them merely to empty a queue.

An already-running older build can finish reusable artifacts, but its publication guard fails once superseded. The worker next handles the newest eligible request.

That newer request includes the chosen existing corpus as well as the new files. Skipping an old update must not silently drop its already-admitted source changes.

#### Check all publication conditions in one transaction

The final release transaction requires:

| Check | Required condition |
| --- | --- |
| **Publication mode** | Automatic updates is still selected. |
| **Control and request identity** | The captured control revision and newest authorized request identity still match. |
| **Job ownership** | This attempt still owns completion. |
| **Expected serving state** | The current Deployment or default binding still matches the captured expectation. |
| **Candidate** | No candidate is attached. |
| **Permissions and inputs** | Current authorization and input lifecycle still permit the result. |
| **Readiness and retention** | All required dependencies are ready, and relevant deletion/retention gates still allow publication. |

These checks, the pointer update, and history commit together. Initial default creation and mode switching lock/check the same binding so they cannot create competing mode authorities.

If newer work is admitted first, old publication is skipped. If old publication commits first, it can serve while the newer request is prepared. Neither ordering permits an old job to overwrite a newer published version.

**Failure of the newest request never revives a superseded request or publishes an older selection as fallback.** Continuous updates can delay publication. Show current versus pending state rather than adding an unbounded scheduler.

#### Example: switching off and on does not revive an old update

| Event | Control revision and authority |
| --- | --- |
| **U1 is admitted for P13 in Automatic updates.** | U1 captures revision **10**. |
| **The user switches to Manual releases.** | Control advances to **11**; U1 loses publication authority. |
| **The user enables Automatic updates again.** | Control advances to **12**, and a fresh request U2 is admitted. |
| **U1 finishes late.** | It still carries **10** and cannot publish, even though the mode is automatic again. |

U2 may reuse compatible P13 artifacts, but it owns a new decision and input snapshot. Checking only a boolean automatic-mode flag would wrongly permit U1 to publish.

#### Retries preserve identities; cancellation does not undo history

Duplicate admission keys return the same operation. Repeated completion cannot move pointers twice. Exhausted safe retries, uncertain provider calls, and unavailable dependencies keep their distinct visible outcomes.

Canceling an update invalidates pending publication, not an already-committed release, and never restores an older pending request. A crash after publication but before job acknowledgment recovers from the recorded publication identity rather than creating a second transition.

### 10. Make defaults discoverable, editable, and deliberately repairable

Studio marks ordinary default resources with a **Default** badge and shows publication mode, current version, selected configuration, and pending update status.

Renaming a resource changes its display name, not its stable ID, binding, mode, or settings. Creating another Deployment uses the normal Manual releases default, with an explicit Automatic updates option and input binding.

Changing an automatic-update binding requires build/deploy authority, an expected revision, and a fresh apply decision.

**Rebinding the default route is a serving change, not a label edit.** It cannot silently override an active candidate. It invalidates work aimed at the old binding and adopts the selected Deployment’s own mode. It must not copy the old default’s automatic setting onto an existing manual Deployment.

Do not recreate deliberately deleted defaults on restart. Preserve provisioning/removal markers; repair is an explicit, authorized selection of resources and mode. Deletion cancels pending publication, and an old job cannot recreate a removed Deployment because it once targeted the default route.

A missing default access group blocks admission instead of granting public access. These ordinary lifecycle checks replace the earlier `everPublished` eligibility test. There is no one-time permission to reset.

### 11. Worked example: from the first answer to manual review and back

#### First answer

Mira completes account setup, saves a provider connection, and selects embedding model **E** and generation model **G**. Her private default starts in Automatic updates.

She completes one batch containing `installation.md` **A1** and `refunds.md` **B1**. The worker builds **P1** against **R1 = {A1, B1}**, then the separate publication command creates the first Deployment and binds the route.

Studio shows preparation progress, then **Ready to ask**. Her answer has normal citations and **AnswerReceipt A77**. No judge or release screen is required.

#### Successful replacement

Mira uploads **B2**. The update freezes **R2 = {A1, B2}** with the selected configuration. P1 continues serving during the build. After verification and eligible publication, **P2 becomes current and P1 becomes previous**.

Feedback submitted later for A77 still belongs to P1.

#### Failure and overlapping updates

Another batch requests **P3**, but its build fails. Healthy P2 continues serving. If a newer authorized batch supersedes P3 while it retries, P3 cannot publish late; the newest complete selection is handled next.

A failed newest update remains visible. It does not authorize a partial corpus or an older superseded selection.

#### Manual review

Mira switches to Manual releases, invalidating outstanding automatic publication authority. She builds **P4**, explicitly compares it with P2, attaches it for a canary, and promotes or rejects it.

Enabling automation while that candidate remains attached is rejected. A later rollback leaves Manual releases selected.

#### Automatic again

After resolving the candidate, Mira selects **Enable automatic updates and apply pending changes**. She reviews the corpus/configuration, authorizes fresh work, and keeps the current version serving while it builds. Old disabled jobs cannot publish.

The route, permissions, data, and historical evaluations remain the same ordinary resources throughout.

### 12. Qualify concurrency, access, and client behavior against the implementation

Use real PostgreSQL concurrency tests and the existing adapter-qualification tests. These are requirements, not tests already passed by this design.

| Area | Required verification |
| --- | --- |
| **Provisioning and creation** | Defaults start automatic without a fake-ready Deployment. Explicit creation defaults manual and honors an explicit automatic choice. A failed or incomplete first batch never serves. |
| **Successful and failed replacements** | Automatic publication uses complete ready bindings, records previous/history, and preserves answer/feedback attribution. Failed replacement preserves healthy current serving; erasure and unavailability retain their separate rules. |
| **Mode-switch races** | Exercise publication versus switching to manual in both commit orders, and automatic → manual → automatic while an old build runs. Only still-authorized work may publish. |
| **Overlapping batches** | Supersede both queued and running work. Verify complete corpus membership, no stale overwrite, and no fallback to an older result when the newest request fails. |
| **Crashes and retries** | Restart between build completion, publication, and acknowledgment. Retry mode/update commands with the same and different keys. Prevent duplicate admission, duplicate pointer transitions, and implicit repetition of uncertain paid calls. |
| **Candidate and rollback rules** | Reject enabling automation with a candidate at 0% or nonzero traffic. Reject manual canary/release commands in automatic mode. Rollback stays manual; re-enabling clearly authorizes the selected pending update. |
| **Current access and lifecycle** | Test revoked grants, upload-only/query-only actors, differing target permissions, erased inputs, default deletion/rebinding, and unavailable rollback targets. Neither mode nor an old job bypasses current policy. |
| **Client parity** | Verify HTTP/Studio/SDK status and MCP query/receipt behavior through mode changes. Add no administrative MCP tools. A comparison neither pauses publication nor promotes its preferred version. |

**Parity** means that different clients observe the same application behavior and state, not that they implement separate versions of it.

### 13. Measure a simple first answer without inventing a timing guarantee

The first-answer scenario is a usability exercise. **Two minutes is an aspiration, and roughly ten minutes is also acceptable.** There is no hard 120-second gate, no guaranteed support limit, and no reason to weaken correctness or add infrastructure solely to meet a timer.

#### Use a small, explicit fixture and prepared environment

A **fixture** is a defined set of test inputs used to repeat the scenario.

| Part of the scenario | Assumption or bound |
| --- | --- |
| **Documents** | Two UTF-8 Markdown/plain-text files, each at most **25 KiB**, about **10 chunks combined**, with a hard test cap of **20 chunks**. UTF-8 is the text encoding used by the files. |
| **Retrieval evidence** | Include facts absent from the question, such as a fictional product’s exact refund period and installation port. Success must depend on retrieving them. |
| **Excluded document work** | PDFs remain supported elsewhere, but scanned PDFs/OCR, tables, and larger documents are outside this timing scenario. |
| **Proposed host** | A laptop with **16 GiB RAM**, roughly **four CPUs and 8 GiB available to Docker**, local SSD, and the existing small-trial disk allowance. These are proposed test assumptions, not measured minimum requirements. |
| **Concurrency** | One user and one parser job, with no concurrent builds/evaluations and no local language-model or cross-encoder loading. |
| **Prepared installation** | Product images and pinned parser text assets are already downloaded. Application volumes are empty, so migrations, account setup, and default provisioning still happen. |
| **Protected configuration** | The operator supplies persistent encryption/bootstrap secret files through normal one-time installation preparation. This is a stated prerequisite, not a substitute for saving provider credentials in the application. |
| **Model endpoint** | An available, pre-approved endpoint, with valid credentials at hand. Configure embedding and generation separately, sharing a connection where appropriate. No judge is needed. |

Origin and certificate-authority approval are already satisfied by the chosen launch configuration. An unfamiliar private gateway needing operator certificate/network setup has a separate measured setup cost and cannot be promised the same result.

Record role-probe, embedding, and generation latency, including throttling or a cold provider deployment when encountered. **Do not assign mandatory per-stage second budgets before measuring the implementation.**

#### Report three different journeys rather than substituting the easiest one

| Journey | What its clock includes |
| --- | --- |
| **Prepared installation launch → first answer** | Start when the user launches the already-installed product, before services are healthy. Include startup/migrations, account/private-resource setup, model/credential entry and probes, upload, parsing/chunking, embeddings, index verification, authorized publication, and question generation. Include human interaction time. |
| **Clean installation → first answer** | Also include obtaining Docker if absent, image/model downloads, generating initial protected configuration, and host/network setup. Report these real first-run costs rather than moving them outside both clocks. |
| **Restart with existing accounts/configuration → answer** | A separate, easier case. It must not replace the empty-application-state journey. |

Large image downloads can themselves exceed two minutes. Do not claim “two minutes from a fresh machine.” Record automated substep times separately, but do not treat an API test that supplies configuration instantly as a test of human onboarding.

Likely bottlenecks to investigate are service startup/migrations, human credential entry, parser initialization, and provider cold starts or rate limits. Keep assets prepared, text work bounded, model roles clear with shared credentials where appropriate, and optional OCR/reranker/judge setup out of the path.

**Authentication, parser isolation, index verification, and evidence generation remain required.** Use measured phases to improve slow or confusing setup. Longer elapsed time alone does not require reopening the architecture.

#### Lightweight end-to-end acceptance scenario

1. **Start with prepared images and empty application state.** Start the full journey clock. Complete real account setup and save actual role configurations and a credential through the API-backed flow.
2. **Upload the complete two-file batch with Automatic updates selected.** Its admission authorizes the ordinary build and first publication without a separate Prepare and ask command. Record source versions, collection revision, job/build, ready PipelineVersion, and the actual first Deployment. Verify that no Deployment existed before readiness.
3. **Ask for a fixture-specific fact.** The answer must match permitted retrieved content, contain valid source citations and an answer identity, and use the real `ModelGateway` and Chroma paths. A canned answer or ungrounded fallback does not pass.
4. **Report the full journey, not only the fastest run.** Repeat a few clean-application-state runs. Record total and phase times, available provider model/revision, chunk counts, hardware, and image versions. Check whether a new user completes the path without learning internal resource setup. Neither two minutes nor roughly ten minutes is a hard gate or promised support limit.
5. **Check the essential behavior separately.** Restart preserves credentials/default IDs; another user cannot read starter data; retries do not duplicate setup; failed batches never publish; cancellation or control changes defeat stale publication; and a later failed update leaves healthy P1 serving. Verify API/MCP default resolution and feedback attribution against the actual version. Retry an alias query after promotion/rebinding and confirm the original operation/receipt with no new model call.

During backend-first development, use authenticated API integration tests and a test client. They establish application behavior and server timings only. The full human timing/discovery scenario waits for Studio and its qualified external TypeScript SDK.

**SDK Kit blocks Studio, not backend work.** This is a focused acceptance test, not a new certification or operations programme.

## Consequences

### Positive

- **First use does not require manual domain setup.** Private projects, groups, collections, and pipeline defaults give users a path from saved model settings and documents to a normal cited answer.
- **Automatic and manual operation use the same product.** Users can switch modes without re-uploading data, copying indexes, changing their integration URL, or moving to a separate quickstart engine.
- **Publication remains attributable and controlled.** Exact inputs, current permissions, revision checks, and update identities prevent late work from overriding newer decisions. Receipts and feedback retain the version that actually served each answer.

### Negative

- **Automatic updates intentionally change future answers.** Consumers of the stable endpoint must understand this behavior. A fixed serving baseline for review requires Manual releases; comparisons alone do not pause publication.
- **Simple setup still requires careful coordination underneath.** Provisioning, role validation, readiness, publication guards, retries, deletion, and rebinding remain real implementation responsibilities. Continuous superseding updates can delay publication, and a failed newest update has no fallback to older pending work.
- **Setup speed depends on explicit prerequisites and measured behavior.** Downloads, host readiness, human input, and provider latency remain visible costs. A prepared-installation aspiration is not a fresh-machine guarantee or justification for weakening security.

## Alternatives considered

The source records superseded or excluded approaches, not a separate comparative evaluation.

### Allow automatic publication only once during first use

**Replaced.** The default continues applying authorized complete updates until the user chooses Manual releases. There is no one-time publication permission, `everPublished` gate, or separate Prepare and ask operation. Reversible mode control and lifecycle checks prevent stale work without prohibiting later automatic updates.

### Publish every draft, partial upload, or change to a shared collection

**Ruled out.** Updates need complete frozen selections and an authorized apply action for explicit targets. Unrelated drafts remain drafts; partial failures do not silently shrink the corpus. Sharing a collection does not authorize publication to every Deployment that uses it.

### Treat a Pipeline or pending build as a ready Deployment

**Ruled out.** The logical default route can exist unbound and report not-ready. A real Deployment starts only with a genuinely ready version and an authorized creation decision. Reads and queries do not create missing setup resources or provide a demonstration answer instead of retrieval.

### Publish on build completion using only an automatic-mode flag

**Insufficient.** A mode can switch off and on while an old build runs. Publication also requires the originally captured control revision, newest request identity, current job ownership, expected serving state, authorization, and readiness. A completed build cannot refresh its own authority.

### Build a separate onboarding engine or general scheduler

**Not selected.** A small durable application operation calls existing source-admission, Build, and Releases use cases. Ordinary private resources and normal queries support both first use and later changes. No new domain hierarchy, runtime service, continuous watcher, general policy engine, or workflow scheduler is required.

## References

| Reference | Responsibility |
| --- | --- |
| [Canonical architecture guide](../ARCHITECTURE.md) | Overall product architecture and existing resource ownership. |
| [ADR-0002: API contract](ADR-0002-product-owned-openapi-contract.md) | Authoritative HTTP contract, generated clients, and backend-first implementation. |
| [ADR-0003: Lineage](ADR-0003-immutable-rag-lineage-and-release-identities.md) | Immutable source/configuration identities and historical attribution. |
| [ADR-0005: Access](ADR-0005-api-enforced-tenancy-and-authorization.md) | Verified principals, controlled account admission, private groups, and fixed integration authority. |
| [ADR-0006: Models](ADR-0006-byok-provider-boundary.md) | Model roles, approved connections, independent capability checks, and credential changes. |
| [ADR-0007: Jobs](ADR-0007-durable-jobs-idempotency-and-recovery.md) | Durable operations, safe retries, uncertain outcomes, and logical-route deduplication. |
| [ADR-0009: Releases](ADR-0009-sticky-logical-canary-deployments.md) | Initial Deployment creation, mode changes, pointer transitions, and one-step rollback. |
| [ADR-0015: Bindings](ADR-0015-profile-specific-index-materializations-and-pipeline-bindings.md) | Frozen builds, verified materializations, and complete ready pipeline bindings. |
| [ADR-0020: Credentials](ADR-0020-persistent-outbound-credentials.md) | Accepted persistent application-entered credentials using PostgreSQL/PyNaCl. |

The source records an [inspection of the old repository](../reviews/onboarding-reference.md) that identified continuous managed-default publication code. That code was inspected, not executed. This design adopts the automatic experience while retaining the new application’s version, authorization, and job boundaries. It does not import the old `Context` hierarchy or treat the old implementation as proof of this protocol’s failure handling.

Private provisioning, reversible modes, and credential persistence are accepted. Exact endpoint/selector schemas remain implementation details, and the timing scenario remains flexible. No unrelated recovery, compliance, or infrastructure scope is added.
