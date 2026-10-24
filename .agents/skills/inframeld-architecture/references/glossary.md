# Shared vocabulary

Alice can change a handbook, a model setting or the version serving Production. Each change has a different owner and identity. Use these definitions to keep those changes distinct. This is a vocabulary aid, not a replacement for exact record definitions.

| Term | Owner | Meaning and example | Distinction |
| --- | --- | --- | --- |
| Principal | Access | Alice's or SupportBot's stable local identity. | A credential identifies a principal. It does not contain permanent product authority. |
| Product admission | Access | A verified person is allowed into the local product under current account rules. | OAuth consent can happen before this and grants no project permission. |
| Project membership | Access | Alice belongs to Support. | Membership alone does not grant Query or document reading. |
| Access group | Access | SupportKnowledge identifies a document audience. | Group membership, group management and action grants solve different problems. |
| Action grant | Access | SupportBot may Query Production. | Permission on Test does not cover Production. Delegation requires separate authority. |
| Document | Knowledge | The stable identity of the handbook source. | A filename or resource name is not its permanent identity. |
| DocumentVersion | Knowledge | Immutable bytes such as handbook B1. | Replacing bytes creates B2 and never edits B1. |
| CollectionRevision | Knowledge | A fixed selection such as A1 and B2. | A logical corpus is not a physical Chroma collection. |
| ProcessingProfile | Indexing | Immutable parser and chunker settings. | A ProcessingGeneration records actual output for a source version. |
| EmbeddingProfile | Indexing | The settings that define the meaning of numerical vectors. | Matching dimensions or model aliases do not prove compatibility. |
| Vectorization | Indexing | A semantic reuse key for the requested vector work. | A VectorGeneration identifies an actual numerical execution. |
| Shard | Indexing | One physical Chroma collection in a saved layout. | It does not own logical corpus membership or permissions. |
| Materialization | Indexing | Verified search data for exact revisions, profiles and generations. | A ready label is not proof of current health or release authority. |
| Working configuration | Pipelines | The Pipeline settings Alice currently saves and edits. | Temporary query overrides do not save it. |
| Execution-input snapshot | Pipelines | The exact settings, corpus and verified bindings captured for an admitted run. | It is not a new Experiment resource or a release-ready version. |
| PipelineVersion | Pipelines | The successful result of a release build. | A reserved build identity is not yet ready or serving. |
| AnswerReceipt | Pipelines | Limited attribution for a live answer and its evidence. | It is not a full-answer replay cache. |
| Benchmark | Evaluation | Frozen case revisions used for a run or comparison. | Later case edits do not change admitted membership. |
| Faithfulness | Evaluation | Support for generated answer claims in the final supplied context. | Reference answers and expected passages must not supply extra judge evidence. |
| Deployment | Releases | Production's stable serving destination. | Its selected version is separate from the Pipeline's working settings. |
| Canary | Releases | A candidate version assigned to a stable share of caller identities. | A percentage is not an exact request count or a permission. |
| Model connection | Shared model boundary | A stable destination/access definition used by selected model roles. | It has one current access configuration, not consumer-selected old settings. |
| Provider credential | Shared model boundary | A saved secret used for an outbound provider call. | It is separate from an incoming Inframeld application key. |
| ModelGateway | Shared application boundary | The controlled route for remote model calls. | It is not a new business domain or a client-side permission engine. |
| Work admission | Shared jobs | The server durably accepts an operation and its retry identity. | Successful admission is not successful completion. |
| Idempotency | Shared jobs | Recognizing the same caller's repeated request and meaning as one operation. | An expected revision separately detects competing state changes. |
| Fencing | Shared jobs | Checking an attempt or revision so stale work cannot publish. | It does not undo an already sent provider request. |
| Retention pin | Shared lifecycle | A bounded record that current work still needs an artifact. | Ordinary expiry respects it, while authorized erasure can invalidate the artifact. |

Names are scoped selectors, display names are presentation labels, and IDs are permanent relationship identities. For example, Alice may select Name `legal-research` while seeing Display name `Legal Research`. Display names never resolve identity. Preserve the distinction from existing physical fields and wire names.

The [data model](../../../../docs/development/data-model.md) owns record definitions, constraints and implementation status. Its [resource naming contract](../../../../docs/development/data-model.md#resource-naming) owns selectors. The [architecture introduction](../../../../docs/ARCHITECTURE.md) and each topic guide explain lifecycle behavior. Do not create an entity, table, repository or aggregate merely because a term appears here.
