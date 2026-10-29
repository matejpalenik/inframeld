# Knowledge identities and relationships

<a id="knowledge-identities-and-relationships"></a>

Alice replaces handbook B1 with B2. The Document stays the same, its content version changes and an authorized selection may create a new CollectionRevision. An older revision keeps its exact original membership.

> **Status:** accepted behavior is stated separately from proposed representations and qualification work. Existing Python types, generated OpenAPI and migrations own implemented shapes. Pending decisions are not accepted by this reference.

<a id="knowledge"></a>

<a id="knowledge-source-identities-and-exact-membership"></a>

## Knowledge: source identities and exact membership

| Logical record | Meaning and constraint |
| --- | --- |
| Document | Stable project-owned source identity and current nonempty group allowlist, protecting all its versions. |
| DocumentVersion | Immutable source content and authoritative hash/reference. Equal content for the same Document can reuse the version. Changed bytes create another. |
| Collection | Stable named corpus, such as Support Knowledge. It does not own private vector copies. |
| CollectionRevision | Exact DocumentVersion membership. Never a mutable “latest” selector. |
| Upload batch / source sync | A bounded admitted selection and progress. Exact physical representations belong to their workflows. No new tables are prescribed here. |

Suppose R1 contains A1, B1, and C1, and B1 describes a 30-day refund period. Alice replaces B with a 14-day policy, producing B2 and R2={A1,B2,C1}. R1 still names B1. [Knowledge lifecycle](documents-and-collections.md) explains replacement, admission, and source disappearance.

For an imported source, the connector and normalized bucket/key identify the logical Document. A provider ETag is not necessarily a content hash. Parsed output belongs to Indexing and does not create another DocumentVersion.

<a id="knowledge-application-boundaries"></a>

### Knowledge application boundaries

[ADR-0075](../../../../docs/adr/ADR-0075-separate-document-lifecycle-from-collection-selection.md) separates document/version operations from collection-selection operations, coordinated by an application workflow for complete batches. The records above do not each imply an aggregate or repository. The accepted [PD-KNOWLEDGE-01](decision-complete-batch-handoff.md#approved-resolution) specifies fixed parent/child identities, conditional complete selection and atomic durable handoff. The parent retains its original manifest, principal/scope, effective audience, intended membership and expected base revision. Child outcomes remain recoverable independently. No physical table or new aggregate per record is prescribed.
