# Move definitions without copying an installation

Alice exports Support and Bob reviews it in Test. A configuration transfer carries reusable definitions. It does not carry the documents, live release state or credentials that made the original installation work.

## Apply accepted PD-CONTRACTS-04

Accepted [PD-CONTRACTS-04](decision-import-review-and-recovery.md#approved-resolution) selects this workflow's detailed contract. Import should apply exactly the configuration Bob reviewed and tell him which changes actually happened if a later step fails. Apply its exact bounds, current-state checks and failure outcomes. Native implementation and qualification remain separate.

## Three different operations

1. **Export** captures one coherent permitted definition set. A name is portable text, while a permanent resource ID belongs to its installation. Export is a read and must not probe a provider or change source state.
2. **Review** resolves those names against the destination and shows reuse, supported updates and creation separately. Bob reviews actual destination revisions and supplies credentials independently. A difference is not authorization to apply it.
3. **Apply and recover** uses ordinary owner operations. Earlier completed changes remain if a later one fails. An uncertain child must be inspected through its original operation before it can safely be repeated.

A global database transaction cannot cover remote work and all of these independently owned effects. The import coordinator preserves reviewed inputs and child identities rather than pretending a partial operation rolled back everything.

## Choose the precise reference

- For TOML scope and coherent reads, use [Configuration export](configuration-export.md).
- For equivalence, destination bindings, reviewed revisions and credentials, use [Import review](configuration-import-review.md).
- For apply, partial results, changed inputs and recovery, use [Import recovery](configuration-import-recovery.md).
- Evaluation datasets have their own [JSONL transfer](../../inframeld-evaluation/references/history-and-dataset-transfer.md), including source proof and audiences.

## Status and decision boundary

These are accepted behavior boundaries. Accepted PD-CONTRACTS-04 selects versioned portable semantics, equivalence and reviewed action policy. Native schemas and integration remain implementation work. Load [PD-CONTRACTS-04](decision-import-review-and-recovery.md) before choosing those representations. Examples in the workflow references must not be treated as invented runtime request types.
