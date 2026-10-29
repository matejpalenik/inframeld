# Select a complete corpus after admission

Alice replaces B1 with B2. Admitting B2 makes a new version available. A separately authorized complete selection chooses whether a new CollectionRevision contains it and whether ordinary automatic-update work may follow.

## Finalize the original complete selection

The accepted [PD-KNOWLEDGE-01](decision-complete-batch-handoff.md#approved-resolution) fixes the parent manifest, child identities, effective audience and intended complete selection before finalization. Recover each confirmed admission instead of uploading it again. A failed sibling leaves successful versions saved but the original batch incomplete. Admission completeness does not claim parsing or search readiness.

Prepare large membership inventories in bounded pages. Under current authority and the expected base-selection revision, commit the exact new CollectionRevision, completion marker, safe outcome, audit and durable continuation together in one short application-owned SQL transaction. New child-job admission includes its finite capacity reservation. Storage/provider waits stay outside it. Do not nest independently transaction-owning complete services.

If Bob selects another revision before Alice finalizes, report a conflict and preserve her admitted versions. Replaying Alice's operation cannot silently merge Bob's changes or change its base. A new reviewed selection can combine both. A lost committed response recovers the original selection/handoff.

Downstream preparation and each explicitly named Deployment retain their ordinary admission, captured-input and release-authority checks. Selection completion is distinct from each target's accepted, denied or unfinished handoff. PD-PIPELINES-01 and PD-RELEASES-01 still own their separate receipt/control choices.

<a id="capture-inputs-before-preparation"></a>

## Capture inputs before preparation

1. Select exact authorized collection/source revisions for the operation.
2. Capture them before direct-query or evaluation preparation. The operation need not create a release-ready PipelineVersion.
3. Ask Indexing to prepare or reuse compatible data under the selected profiles. The same admitted bytes may support another profile without another upload.
4. Preserve that captured corpus throughout an admitted query or evaluation. Concurrent working-configuration edits and source replacements cannot silently retarget it.

Development-only uploads use ordinary collections outside live-watched inputs. Do not silently clone collections or suppress their normal automatic updates. Document-triggered live work retains the Deployment's selected configuration, not an unrelated working edit.

<a id="freeze-a-corpus-and-prepare-it"></a>

<a id="corpus"></a>

<a id="3-freeze-a-corpus-and-prepare-it"></a>

## Freeze a corpus and prepare it

A build or direct Pipeline query uses exact DocumentVersions selected for that request. It cannot switch to whatever happens to be newest when the worker starts. [Pipelines](../../inframeld-pipelines/references/direct-queries.md#preview) owns capture of working settings. Knowledge supplies exact corpus membership, not publication authority.

Alice can select versions in the collection editor. The first-use working design obtains the selection from one fixed upload batch.

PostgreSQL saves the CollectionRevision's complete membership. A separate immutable **manifest**, an inventory of those version IDs, can support verification.

Uploading alone does not change live answers. Accepting the document, selecting a collection revision, preparing search data, and releasing a pipeline are separate steps.

An authorized completed live-input upload can coordinate those steps automatically under the Deployment's existing input binding. Direct querying does not modify that binding or collection membership. For development-only uploads, explicitly select an ordinary collection outside the watched live inputs. Do not silently create a copy or suppress a live collection's update behavior. Changing a working corpus selection alone affects future queries/builds, not existing deployments. Current access and source erasure still apply to every retained execution-input snapshot.

<a id="step-4-freeze-and-run-the-build"></a>

### Step 4: freeze and run the build

A pipeline describes a limited **retrieval-augmented generation (RAG)** flow: find relevant document excerpts, then ask a model to answer from them. Its configuration selects the corpus, one processing profile, one embedding profile, retrieval limits, reranking, prompt, and generation settings.

V1 does not support arbitrary pipeline graphs or user-supplied Python execution.

When Alice selects Build, the server saves the current reviewed working configuration and exact corpus request with a background job. Later edits cannot alter that job's inputs. A name such as P13 can be reserved immediately, but a pending build is not a ready PipelineVersion. Direct-query/evaluation may prepare and use the same verified source data before this formal build, without creating P13 or granting release authority.

The worker reuses compatible existing results and creates only what is missing:

| Change | Expected work |
| --- | --- |
| Change the prompt or retrieval `top-k`, the number of results requested | Usually reuse the existing searchable data. |
| Replace the refund document B1 with B2 | Process and embed B2. Reuse compatible results for unchanged documents. |
| Change the embedding model or profile | Potentially embed the entire selected corpus again. |

Show Alice which work is needed. An incremental build reuses what it can, but changing an embedding model may still be expensive.

<a id="step-5-verify-readiness"></a>

### Step 5: verify readiness

An **IndexMaterialization** records the generations that make the selected corpus searchable and where their vectors live. Indexing marks it ready only after checking the required records, identities, and compatibility.

Collection membership stays in PostgreSQL, rather than in mutable `collection_revision_ids` lists attached to shared vectors. Indexing decides search readiness. Knowledge cannot declare a build ready or switch Deployment traffic.

A successful build does not attach a candidate or change live traffic. A separately authorized publication command does that. Automatic updates call the normal build and request publication only if the update is still eligible. In Manual releases, an engineer decides when to publish. Both use the same build behavior.

<a id="private-onboarding"></a>

## Private onboarding

Starter projects, groups, collections and profiles are ordinary private resources. The creator is explicitly both ordinary member and manager of the starter group. Setup needs no benchmark or judge. Flexible first-answer timing must not weaken checks.

Changing upload defaults requires Manage upload defaults and management of every current/proposed group. It affects future admissions only. Those future uploads still require Add documents.

Automatic mode cannot turn upload-only rights, drafts or partial batches into release authority. New authorized selections supersede older publication requests. Manual mode leaves prepared inputs unpublished.

<a id="treat-a-completed-batch-as-one-complete-selection"></a>

### Treat a completed batch as one complete selection

Use ordinary completed upload batches, not a continuous file watcher. Later files form another batch.

A partially failed batch may keep successfully accepted files, but must not quietly publish a smaller corpus. Alice can retry safe work or deliberately change the selection. Save exact source versions and settings when accepting the update, so the worker cannot substitute whatever is newest later.

The first batch may reserve document IDs through normal saved acceptance steps before building. If any admission fails, publication is blocked.

A manually requested S3 sync follows the same rule after establishing a complete revision. Its explicitly authorized live-input update starts preparation and conditional publication for the selected Automatic Deployment. It uses the Deployment's selected configuration, not an unrelated working edit. V1 adds no scheduled polling or publication after each incomplete listing page.

Removing a document from a collection changes a future selection. Revoking access or explicitly erasing it is different: [retention rules](deletion-and-retention.md) apply immediately and may make the current version unavailable in either mode. Old versions are not entitled to keep serving erased content.
