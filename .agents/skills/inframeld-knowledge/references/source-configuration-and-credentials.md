# Source configuration, audiences and credentials

<a id="source-configuration-audiences-and-credentials"></a>

Alice configures a read-only S3 source for Support. Its location, destination audience and authentication are explicit saved choices. Saving or importing a source definition does not synchronize it or copy the source system’s permissions.

> **Status:** accepted behavior is stated separately from proposed representations and qualification work. Existing Python types, generated OpenAPI and migrations own implemented shapes. Pending decisions are not accepted by this reference.

<a id="portable-knowledge"></a>

<a id="portable-collections-and-sources"></a>

<a id="recreate-collections-and-sources-from-configuration"></a>

### Recreate collections and sources from configuration

Collection/Source provisioning is human-only in v1, using Project `create-collections` or `create-sources` and [fixed exact-resource creator assignments](../../inframeld-access-models/references/actions-and-initial-grants.md#initial-assignments). Applications may view/edit/delete existing Collections through separate grants. Collection membership editing creates normal revisions and never erases Documents or widens their audiences. Collection deletion follows dependency checks and leaves admitted Documents intact.

Source configuration, credential administration and deletion remain human-only. An application with `sync-source` may run a separately admitted bounded sync against the saved approved configuration, with current Add/Update rights on the required groups and collection mutation authority. `view-source-configuration` reveals only permitted non-secret configuration. Retiring a Source stops future sync and removes its configuration/credentials. Already admitted Documents remain until separately authorized document erasure. [The catalogue](../../inframeld-access-models/references/actions-and-initial-grants.md#capability-catalogue) names these distinct actions.

Bob importing Alice's configuration receives empty collection definitions, not documents or vector data. Explicit reuse of an existing collection leaves its membership/history untouched. [Configuration portability](../../inframeld-application-contracts/references/configuration-export-and-import.md) specifies the complete export boundary and reviewed partial import.

Source definitions contain the supported non-secret read-only S3 location, collection reference and required document audience. Before creating a source, explicitly map each audience to permitted destination group IDs. Matching names may help suggest a mapping, but do not prove equivalent access. Creating groups and granting permissions remain separate operations. Changing configuration does not silently change existing documents' audiences.

Configure source authentication separately on the selected backend using protected input. Choose either an explicitly authorized operator-configured identity or credentials bound to that source. Do not borrow the CLI login, credentials found on the user's laptop or another source's identity. Saving configuration, supplying credentials, optionally testing access and starting synchronization are separate operations.

Before an explicit sync, review the location, audience, limits, potential charges and effects on live updates. Then discover the inventory within those limits during execution. Keep accepted documents and report partial results if work stops. An incomplete inventory cannot prove that a source object disappeared.

Report configuration, ingestion, preparation and publication separately. **Finish** is the default after import or sync. Optional continuation uses ordinary preparation and query operations. [V1 scope](../../inframeld-architecture/references/v1-scope-and-extension-boundaries.md) describes delivery boundaries. Knowledge and Access own source-credential, action and limit contracts and their qualification.

<a id="retained-logical-information"></a>

## Retained logical information

| Information | Owner and constraint |
| --- | --- |
| Source authentication binding | Knowledge source identity, explicit configured server identity or source-bound encrypted credential metadata, selected destination and expiry. Reuse encryption primitives without treating model/source credentials as interchangeable. |
