# Uploads, replacement and bounded source sync

<a id="uploads-replacement-and-bounded-source-sync"></a>

Alice uploads two files and later connects a read-only S3 source. Both paths must admit trustworthy versions with deliberate audiences. Neither a local filename nor an upstream permission list can decide who reads a document in Inframeld.

<a id="follow-an-upload"></a>

## Follow an upload

1. Use private staging, bounded supported input, byte/metadata validation and server-generated storage keys. Treat filenames as display text.
2. Require Add documents on every selected same-project group, including defaults. The initial audience must be nonempty. Upload authority does not include reading, replacement, deletion, audience changes or publication.
3. Verify complete durable artifacts before admitting the source. A partial upload does not create a usable document.
4. For replacement, require Update documents on every group in the persisted current allowlist and recheck authority at commit. Preserve source identity and groups.
5. Freeze the complete authorized batch and full corpus, including unchanged documents. Parsing and verified index preparation follow their own owners.

Equal authoritative content reuses the existing version, while changed bytes create a new one.

Retries use the original admitted operation and durable artifacts. They must not reinterpret a lost response as permission to create another source or repeat uncertain paid work.

A complete batch still needs separate Build and target-specific publication authority before an automatic update can move traffic.

## Recover a fixed batch

The accepted [complete-batch contract](decision-complete-batch-handoff.md#approved-resolution) retains the original manifest, effective audiences, input meanings and stable child identities. Changed upload defaults or later files cannot change a retry. Reconcile an uncertain child before admitting another. Keep successful original versions after a partial failure, but finalize only all confirmed original members and the exact reviewed selection. A competing collection selection conflicts without discarding those files or automatically combining changes.

<a id="follow-a-source-sync"></a>

## Follow a source sync

1. Configure explicit destination audience IDs and saved bounded source scope. Supply separate backend-bound source credentials, not ambient laptop credentials.
2. Review the bounded sync separately before contacting the source. Use current group and collection mutation authority for the admitted effects.
3. Observe supported source identities and content. Preserve checkpoints and identity across retries. Do not import upstream ACLs or grant all project members document access.
4. Produce ordinary versions and a new corpus revision. An incomplete inventory cannot establish that an unobserved source disappeared. Missing observations never rewrite retained releases.

Manual read-only S3 sync is the accepted bounded path. Do not infer a connector framework, event bus or broad source-ACL platform. Collection/source retirement is different from document erasure. Imported configuration must not trigger implicit source contact.

<a id="admit-and-replace-content"></a>

<a id="admission"></a>

<a id="2-admit-and-replace-content"></a>

## Admit and replace content

Alice uploads a supported PDF, Markdown, or text file.

The API streams the file into private temporary storage, checks its size and format, and gives it server-generated storage IDs. An application command then saves the accepted upload.

Saving acceptance is called **admission**. After that point, the application can track the work even if Alice closes the CLI progress view or, later, Studio.

A filename is a display label, never a filesystem path. Each upload is limited to **25 MiB** under the [upload rules](#admission). Parsing also needs time and output limits because a small compressed file can expand into much larger content.

Knowledge owns the Document and its versions. The application hashes the content to recognize it. Observing the same content again may reuse the version, while changed bytes create a new version.

SeaweedFS stores the original bytes through the application's `ArtifactStore` interface. PostgreSQL records which stored object belongs to the accepted document. Merely placing an object in storage does not make it application knowledge.

<a id="step-2-parse-the-document-and-create-chunks"></a>

### Step 2: parse the document and create chunks

The restricted parser converts the accepted source into text excerpts called **chunks**. The worker validates these outputs. Follow the [processing explanation](../../inframeld-indexing/references/parser-isolation-and-validation.md#separate-coordination-from-conversion) for the isolation rules. Successful parsing does not yet mean the index or pipeline is ready.

Before accepting content, verify that all bytes are complete and durably stored under server-generated keys. A partial upload or guessed filename is insufficient. Reusing identical content still requires authorization and must not reveal another document's existence.

Creating a Document needs Add documents on every selected initial group. That permission does not include reading, replacing, deleting, sharing, or releasing it. Replacement needs Update documents on every group in the saved current audience, checked when saving the change. It preserves the Document's identity and audience. [Access](../../inframeld-access-models/references/query-and-document-authorization.md#documents) defines the complete permission rules.

<a id="synchronize-a-source-safely"></a>

<a id="source-sync"></a>

<a id="4-synchronize-a-source-safely"></a>

## Synchronize a source safely

V1 also supports a manually started, read-only source sync with explicit limits. It uses the **S3 object-storage API**, which does not require running Inframeld on AWS.

An operator approves a bucket and key prefix and supplies a credential limited to the access needed. The connector lists only that location, saves progress checkpoints, and submits changed files through the normal upload-acceptance path.

The connector and normalized bucket/key identify the source across syncs. An S3 ETag is not always a content hash. If the provider's metadata cannot establish content identity, use the downloaded bytes.

Unchanged content may reuse a DocumentVersion. A missing source object may be omitted from a new collection revision, but does not rewrite a revision already used by a Deployment.

Imported documents receive an explicit list of Inframeld access groups. The source system's access-control lists, or ACLs, are not copied automatically.

<a id="validate-before-admission"></a>

<a id="1-validate-before-admission"></a>

## Validate before admission

Accept **one PDF, Markdown, or plain-text file per upload request**, with a maximum size of **25 MiB**.

Stream bytes into private temporary storage, where queries cannot see them. Count the actual bytes received. Reject files exceeding the limit before saving that the application has accepted the upload, a step called **admission**.

The backend may need to write some temporary bytes before discovering an oversized file. It must remove its own rejected staging file and never expose it to queries. The promise is limited, private handling and cleanup, not that no byte reaches disk.

Check the extension, the one-file request shape, parser support, and a limited inspection of file signatures or text encoding. A signature helps identify the actual format from bytes. An extension alone cannot prove that a file is a supported PDF or text document.

Unsupported, ambiguous, or invalid uploads fail before document processing or model calls.

The server chooses storage keys. Original filenames are display text, never paths to open. Normal application commands and content hashes establish DocumentVersion identity. The parser cannot create a separate identity scheme.

<a id="alice-changes-the-default-audience-for-uploads"></a>

### Alice changes the default audience for uploads

Changing upload defaults requires both Manage upload defaults on the project and management of every group in the old or new defaults. The new default must contain at least one group, all from the same project.

Changing the default from HRPrivate to SupportKnowledge affects future uploads, not existing documents. Each upload still needs Add documents on every selected group. If that fails, the backend must report the failure rather than silently choose a different audience.

Starter uploads use the private group saved in the project's defaults. Future source connectors also select Inframeld groups explicitly. They do not automatically copy the source system's permissions. V1 source configuration is human-only under the [fixed Source capabilities](../../inframeld-access-models/references/actions-and-initial-grants.md#capability-catalogue). Separately granted sync remains eligible for applications.

<a id="maintainer-checks"></a>

<a id="6-maintainer-checks"></a>

## Maintainer checks

| Scenario | Expected outcome |
| --- | --- |
| Alice replaces B1 with B2 and an authorized selection includes it | The new collection revision uses B2. Replacing bytes alone does not select a corpus. Older revisions retain B1. |
| The same upload is retried | Existing accepted identity may be reused without bypassing permission checks. |
| S3 lists an unchanged ETag | Treat it as a provider marker, not necessarily a content hash. |
| A source disappears | A new corpus may omit it. Old revision membership is unchanged. |
| Parsing succeeds but indexing fails | Source admission remains distinct from readiness and publication. |
| Deletion races a build | The tombstone prevents late publication or disclosure. |
| An upload default is changed | Existing document audiences do not change. |

<a id="pending-decisions-for-dependent-implementation"></a>

## Decision references for dependent implementation

Apply accepted entries when their scope matches. Discuss only choices still explicitly pending:

- [PD-KNOWLEDGE-01 (accepted): Finalize a complete collection selection without losing admitted input](decision-complete-batch-handoff.md). Before implementing batch completion, collection selection, parent/child recovery or the ingestion-to-automatic-update handoff.

<a id="status-and-sources"></a>

## Status and sources

These are accepted admission, permission and sync boundaries. Exact public schemas, runtime bounds and delivery qualification remain in the owning guides. Inspect code before presenting these workflows as implemented.

- [Admission and replacement](#admission), [Knowledge lifecycle](documents-and-collections.md), [ingestion security](./uploads-and-source-sync.md) and [jobs/retries](../../inframeld-application-contracts/references/jobs-and-recovery.md).
- [Private onboarding](../../inframeld-architecture/references/first-use-and-private-defaults.md), [Access rules](../../inframeld-access-models/references/authorization.md), [portable sources](source-configuration-and-credentials.md#portable-knowledge) and [Access contracts](../../inframeld-access-models/references/actions-and-initial-grants.md).
- [Indexing](../../inframeld-indexing/references/profiles-and-preparation.md) owns preparation and [deployment](../../inframeld-architecture/references/runtime-deployment-and-storage.md) owns artifact publication boundaries.
