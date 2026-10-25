# Uploads, replacement and bounded source sync

Alice uploads two files and later connects a read-only S3 source. Both paths must admit trustworthy versions with deliberate audiences. Neither a local filename nor an upstream permission list can decide who reads a document in Inframeld.

## Follow an upload

1. Use private staging, bounded supported input, byte/metadata validation and server-generated storage keys. Treat filenames as display text.
2. Require Add documents on every selected same-project group, including defaults. The initial audience must be nonempty. Upload authority does not include reading, replacement, deletion, audience changes or publication.
3. Verify complete durable artifacts before admitting the source. A partial upload does not create a usable document.
4. For replacement, require Update documents on every group in the persisted current allowlist and recheck authority at commit. Preserve source identity and groups.
5. Freeze the complete authorized batch and full corpus, including unchanged documents. Parsing and verified index preparation follow their own owners.

Equal authoritative content reuses the existing version, while changed bytes create a new one.

Retries use the original admitted operation and durable artifacts. They must not reinterpret a lost response as permission to create another source or repeat uncertain paid work.

A complete batch still needs separate Build and target-specific publication authority before an automatic update can move traffic.

## Private onboarding

Starter projects, groups, collections and profiles are ordinary private resources. The creator is explicitly both ordinary member and manager of the starter group. Setup needs no benchmark or judge. Flexible first-answer timing must not weaken checks.

Changing upload defaults requires Manage upload defaults and management of every current/proposed group. It affects future admissions only. Those future uploads still require Add documents.

Automatic mode cannot turn upload-only rights, drafts or partial batches into release authority. New authorized selections supersede older publication requests. Manual mode leaves prepared inputs unpublished.

## Follow a source sync

1. Configure explicit destination audience IDs and saved bounded source scope. Supply separate backend-bound source credentials, not ambient laptop credentials.
2. Review the bounded sync separately before contacting the source. Use current group and collection mutation authority for the admitted effects.
3. Observe supported source identities and content. Preserve checkpoints and identity across retries. Do not import upstream ACLs or grant all project members document access.
4. Produce ordinary versions and a new corpus revision. An incomplete inventory cannot establish that an unobserved source disappeared. Missing observations never rewrite retained releases.

Manual read-only S3 sync is the accepted bounded path. Do not infer a connector framework, event bus or broad source-ACL platform. Collection/source retirement is different from document erasure. Imported configuration must not trigger implicit source contact.

## Status and sources

These are accepted admission, permission and sync boundaries. Exact public schemas, runtime bounds and delivery qualification remain in the owning guides. Inspect code before presenting these workflows as implemented.

- [Admission and replacement](../../../../docs/development/knowledge-lifecycle.md#admission), [Knowledge lifecycle](../../../../docs/development/knowledge-lifecycle.md), [ingestion security](../../../../docs/development/ingestion-security.md) and [jobs/retries](../../../../docs/development/jobs-and-idempotency.md).
- [Private onboarding](../../../../docs/development/onboarding.md), [Access rules](../../../../docs/development/access-control.md), [portable sources](../../../../docs/development/knowledge-lifecycle.md#portable-knowledge) and [Access contracts](../../../../docs/development/access-contracts.md).
- [Indexing](../../../../docs/development/indexing.md) owns preparation and [deployment](../../../../docs/development/deployment.md) owns artifact publication boundaries.

## Pending decisions for dependent implementation

The ordinary behavior above remains owned by its current sources. Before choosing an unresolved implementation contract, load only the matching entry:

- [PD-KNOWLEDGE-01: Finalize a complete collection selection without losing admitted input](decision-complete-batch-handoff.md). Before implementing batch completion, collection selection, parent/child recovery or the ingestion-to-automatic-update handoff.
