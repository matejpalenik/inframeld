# Change shared current model connectivity

<a id="change-shared-current-model-connectivity"></a>

Alice updates a connection used by two Pipelines. Future calls from both use its current committed settings. The change needs its own authority, reviewed impact and compatibility checks, independently of Pipeline publication.

> **Status:** accepted behavior is stated separately from proposed representations and qualification work. Existing Python types, generated OpenAPI and migrations own implemented shapes. Pending decisions are not accepted by this reference.

<a id="shared-current-connections"></a>

<a id="separate-stable-connection-identity-current-access-and-observed-history"></a>

### Separate stable connection identity, current access and observed history

A **connection** is a project-owned resource for reaching a model service. It has a stable ID and one current committed **access configuration**. Its non-secret access revisions record approved changes, not multiple configurations consumers may select. [ADR-0054](../../../../docs/adr/ADR-0054-use-shared-current-model-connections.md) supersedes consumer-pinned connection meaning.

Pipeline, profile and evaluator definitions select the connection ID and their own model settings. Gateway dispatch resolves the current permitted access configuration. Updating it is a separately authorized shared operation, not a Pipeline edit or release. Names are selectors only. Repeated runtime name resolution must not replace a saved ID with another resource.

A replaceable credential allows calls through that connection. It has its own lifecycle, independent of access revision history and immutable consumer settings. No secret is stored in a Pipeline, profile or execution snapshot.

| Logical information | Meaning and lifetime |
| --- | --- |
| **Connection identity/current access** | Owning project and stable ID. Current supported provider, endpoint/base path and applicable API/authentication settings. Metadata rename is separate from an access change. |
| **Access revision history** | Non-secret settings, predecessor, actor/time and optional restored-from revision. Restoration creates new current history through ordinary checks. History is not a runtime selector or a promise of permanent retention. |
| **Reviewed update** | Exact identity, expected access/credential state where relevant, proposed diff and reviewed dependency impact. Commit rechecks authority, compatibility and concurrent bindings. No physical review-token schema is selected here. |
| **Execution observation** | Selected connection ID, admitted access revision and actual revision/model/credential observations for each dispatched call. These explain results and guard subsequent calls. They never authorize use of an old revision. |

These are logical responsibilities, not a new table per row. [Model connections](#shared-current) owns activation and [Jobs](#connection-changes) owns interruption/replay. Current access and retention protect inspection of every historical record.

<a id="shared-connectivity"></a>

<a id="keep-shared-connection-administration-separate-from-pipeline-release"></a>

### Keep shared connection administration separate from Pipeline release

Suppose P12 selects `company-gateway`. A connection manager can update that connection's current access settings through [the guarded shared-update workflow](#shared-current). P12 still selects the same ID and model settings, but subsequent calls use current connectivity. This creates no Pipeline version or publication and does not require Manage releases on every affected Deployment. Pipeline Edit alone cannot authorize it. Manual mode is not protection against shared infrastructure changes.

Keep each version's Pipeline/model settings and verified data bindings immutable, with current access observations recorded separately on executions. Rolling back from P13 to P12 does not restore historical connection settings or credentials. Historical execution evidence remains attributable to what actually ran, not relabelled with the current connection revision.

For isolation, create another connection, select it on the Pipeline's working configuration, query the Pipeline directly, evaluate if desired, then save, Build and release. This can change the selected connection without changing the current release until publication. An embedding-model migration additionally needs [compatible preparation](../../inframeld-indexing/references/materialization-verification.md#embedding-compatibility). A shared update that would invalidate retained/in-progress embedding data, or whose compatibility is unknown, is rejected before activation instead.

P12 and P13 must both satisfy Production's query contract. Alice can then change prompts, the selected documents (the **corpus**), or compatible model settings without changing SupportBot's URL, credential, or request and response integration.

An incompatible API or schema change is outside this promise. Moving a pointer cannot make an incompatible version compatible.

A **canary** sends some traffic to a candidate while current serves the rest. The customer application supplies an opaque, stable **affinity key** for routing an end-user or session. Related requests stay in the same routing group, or **cohort**.

**An affinity key is routing input, not a verified end-user identity and not an additional permission.**

<a id="expose-shared-connection-administration-through-one-application-operation"></a>

### Expose shared connection administration through one application operation

Provide capabilities to inspect current access/history and permitted usage, review a proposed change, conditionally update it and propose restoration. [Model connections](#shared-current) owns their behavior. CLI flags, future UI and explicit configuration imports must invoke the same backend checks. A client-side confirmation is not authority. Connection management includes shared live impact, while Pipeline Edit and model use do not.

Logical update inputs identify the connection, expected current revisions, complete proposed supported settings and acknowledgment of the reviewed live impact. Destination-changing credentials use protected write-only input. Outputs distinguish unchanged, committed, rejected, stale review and uncertain response/recovered outcome, with safe current/result revision metadata. Incompatible or unproven embedding dependencies reject before mutation. Do not invent new endpoint paths, problem codes, permission IDs, physical tables or vendor-typed request bags in this documentation.

Pipeline/profile/evaluator definitions select stable connection IDs, not executable historical access revisions. Execution results expose actual safe revision observations and interrupted-work attribution through their owning contracts. Snapshot/history inspection must not become a way to dispatch against retired access settings or recover secrets. Specify exact wire mappings and tests when implementing the capabilities. This change generates no contract and adds no MCP tools.

<a id="connection-changes"></a>

<a id="preserve-operation-identity-across-shared-connection-changes"></a>

### Preserve operation identity across shared connection changes

Admitted work records selected connection IDs and the current access revisions it observed, separately from fixed Pipeline/model/corpus inputs. Before each model dispatch, resolve current access and apply [the gateway freshness rule](model-dispatch-and-destinations.md#dispatch-freshness). A relevant access change stops remaining model work. It is not permission to use the old revision, rebind the existing job or retry against new settings automatically. Credential-only rotation and metadata rename remain independent.

A known revision/precondition failure uses the existing failed outcome with a safe explanation. An uncertain dispatched paid call retains recovery-required handling. Keep completed checkpoints with actual revision attribution. Changed settings require new explicit admission and cost review. Resuming the same job must not relabel old units or adopt a newer access revision. Previously captured immutable vector payloads retain their ordinary bounded storage-retry path, but this permits neither new model calls nor automatic publication under changed consent.

Connection updates themselves are conditional, idempotent commands. Recheck reviewed revisions, current management authority, complete dependency impact and embedding compatibility in coordination with new bindings/preparation admission. Commit configuration, required credential transition, audit and safe replay outcome together. No external model call occurs inside that transaction. Lost responses recover the original metadata-only outcome. Replay after another update does not restore the earlier state. Exact public schemas and concurrency mechanisms remain implementation work, not another workflow framework.

<a id="shared-current"></a>

<a id="operate-one-current-connection-not-several-consumer-selected-revisions"></a>

### Operate one current connection, not several consumer-selected revisions

Connection creation, management/credential changes and deletion are human-only in v1. Applications may receive `view-model-connection-configuration` and `use-model-connection` on an existing connection, without provider secret access or management. Creation uses Project `create-model-connections` and the [four fixed human creator assignments](../../inframeld-access-models/references/actions-and-initial-grants.md#initial-assignments).

Alice uses `company-gateway` for Contracts and Support. Updating its supported access settings changes future calls from both Pipelines, including already released versions. It does not edit their prompts, change their selected model IDs, create versions or move Deployment pointers. Manual release mode controls Pipeline publication, not shared connection administration.

| Owner | Settings and identity |
| --- | --- |
| **Connection** | Stable project-owned ID, name/display name and one current supported provider/access configuration: endpoint/base path, provider API version and authentication method where applicable. No arbitrary provider-parameter, header or proxy bag. |
| **Credential slot** | Current protected credential and its independent revision. Reusing a connection reuses this slot without revealing or copying its value. |
| **Pipeline** | Selected generation/reranking connection IDs, model identifiers, supported parameters, prompts and retrieval settings. Built-in local reranking needs no remote credential. |
| **Embedding profile** | Expected provider/model identity and vector-space settings, plus its selected connection ID. Indexing owns compatibility with prepared data. |
| **Evaluation configuration** | Explicit generator/judge connection IDs and model/settings, separate from Pipeline answer-generation choices. |

**Current** means the complete committed access configuration, not unsaved editor input or the newest historical row. Keep non-secret access revisions for audit, comparison and actual call attribution. Consumers cannot select an old revision for execution. Metadata-only rename does not advance the access revision or invalidate admitted work. Credentials continue to have their own revision.

<a id="review-and-commit-a-shared-update"></a>

### Review and commit a shared update

1. Resolve the stable connection ID within the effective project and check current connection-management authority. This authority includes live impact. It does not additionally require Manage releases on each affected Deployment. Pipeline Edit or model-use authority alone never grants connection management. Use human-only `manage-model-connection` on that connection. The [fixed catalogue](../../inframeld-access-models/references/actions-and-initial-grants.md#capability-catalogue) separately names view, use, creation and deletion.
2. Validate the complete proposed configuration against supported provider contracts, operator destination policy and the compatibility rule below. No model call is hidden in review, dry-run, import or save. Optional paid preflight remains a separately authorized operation.
3. Review the diff, effective target/project, current access revision and affected Pipelines, live Deployments, retained embedding dependencies and active work. Show only permitted names/details. A filtered list cannot establish that no hidden dependency exists. Backend safety checks examine all relevant dependencies regardless of the manager's inspection rights.
4. If live consumers are affected, require deliberate typed acknowledgment in the CLI and an explicit machine equivalent. The backend binds acknowledgment to the reviewed identity, revision and impact, not to a generic `yes`. Connection restoration and explicit import updates use the same operation. Any changed proposal, authorization or relevant dependency state requires fresh review, not silently broadened consent.
5. In a short coordinated write, recheck those conditions and commit the whole configuration, any required credential transition, audit and idempotent outcome together. Coordinate this check with new consumer bindings and embedding-work admission so a concurrent new dependency cannot escape the review. The exact locking/storage mechanism is implementation work. A check performed only before the prompt is insufficient.

Rejected updates leave both access settings and credentials unchanged. A no-op makes no new access revision. A lost response is recovered from the original operation's metadata-only outcome, never by blindly applying the change again. Current permissions still protect replay. No provider network wait belongs inside the write transaction.

Changing origin, provider authentication destination or authentication method must not implicitly reuse a saved secret. Require explicit provision for the reviewed destination through protected input, even if the operator deliberately supplies the same value, and commit it with the access change. An explicitly permitted credential-free configuration clears the old slot atomically. A required new credential that is missing blocks activation. Ordinary new-connection setup may still save an incomplete, non-usable connection. Same-destination edits preserve the credential only when its authentication binding remains applicable. This introduces no additional provider authentication mechanism.

<a id="connection-compatibility"></a>

<a id="reject-incompatible-shared-embedding-changes-before-activation"></a>

### Reject incompatible shared embedding changes before activation

An index contains vectors produced under an embedding profile, not merely an array length. Before updating a connection, ask Indexing about all prepared or in-progress embedding dependencies, including retained versions and work not visible to the manager. If the proposal changes their vector meaning or compatibility cannot be established, **reject the shared update**. Do not save it and then disable consumers, accept a force confirmation, rewrite profiles or automatically re-embed data.

V1 compares the explicit expected provider/model identity and vector settings and uses supported identity evidence when available. A matching alias, matching dimensions or a successful probe is not proof of equivalent embeddings. In particular, do not assume that another provider, endpoint/base path or provider API version preserves existing vector meaning. Where supported evidence cannot establish that, the update is blocked. Credential-only replacement preserving the access/model contract and metadata-only rename do not require re-embedding.

The recovery path is another connection and the appropriate new embedding profile, then ordinary query/Build preparation and deliberate release. This still permits selecting a different embedding model for a direct query. [Indexing](../../inframeld-indexing/references/materialization-verification.md#embedding-compatibility) owns the exact mismatch and readiness outcomes. Unannounced changes inside an external service cannot always be detected. Record provider identity where available and never claim the checks certify the provider's internal implementation.

<a id="migrate-gradually-or-restore-settings-deliberately"></a>

### Migrate gradually or restore settings deliberately

For isolation, create `company-gateway-next`, supply its credential explicitly and select it on the Pipeline's working configuration. Query the Pipeline directly, evaluate if desired, save successful overrides, then Build and release under the ordinary policy. Other consumers remain on the original connection. This needs neither a second gateway service nor a gateway-release framework.

Restoring an earlier connection revision creates a new current access revision through the same reviewed update. It does not make old revisions selectable, restore historical secrets or waive current destination/embedding rules. Pipeline rollback restores Pipeline settings and selected connection identities, **not** connection access settings. An old version that selects `company-gateway` still uses its current configuration.

Project configuration export captures one current non-secret definition per included connection. Import can explicitly reuse an equivalent destination connection or create a new one. A same-name mismatch is not overwrite authority. Explicit updates reuse this guarded operation. Exporting a historical Pipeline's settings does not recreate its historical connectivity. The shared-connection administration ticket distinguishes portable settings, destination credentials and execution history.
