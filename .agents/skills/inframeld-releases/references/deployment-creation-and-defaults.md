# Create a real Deployment and bind the default

Alice completes the first Support setup. A logical default route may exist before a Deployment, but a real Deployment requires a complete ready version and authorized creation. An empty placeholder must not look live.

<a id="distinguish-resources-that-exist-from-resources-that-are-ready"></a>

### Distinguish resources that exist from resources that are ready

The **project-default binding** stores stable resource IDs and an expected revision for detecting competing changes. It is configuration on the ordinary project, not a second set of domain resources. Display names are never lookup keys. Resource names can select a resource through authorized resolution, but the saved default binding retains its ID rather than re-resolving a name on every request.

Before the default Deployment exists, the binding stores its selected mode and publication control revision. First publication transfers that state into the real Deployment in one transaction. **Only one record may control its mode at a time.**

| Resource | State after authorized provisioning | What makes it usable or ready |
| --- | --- | --- |
| **Organization, project, and private group** | Ordinary records and creator membership. | Verified account/bootstrap authorization and the completed provisioning transaction. |
| **Default Collection** | An empty named collection referenced by project defaults. | An admitted batch produces an exact usable CollectionRevision. An empty collection is not evidence. |
| **Built-in ProcessingProfile** | An immutable conservative text-first preset. | Its pinned parser and assets pass normal readiness checks. No per-user profile editor is required. |
| **Default Pipeline** | A named root with incomplete draft configuration linked to the collection and preset. | Model roles and exact inputs are selected, and a successful build produces a complete PipelineVersion. |
| **Provider connection and credential** | No fictional credential or successful validation. | Complete configuration, a usable required credential and permitted destination allow a real call without prior preflight. Successful use can then establish role-specific validation evidence. |
| **EmbeddingProfile** | Absent until the model's semantics and dimensions are established. | Supported metadata, explicit validated configuration or an optional probe supplies the immutable profile. Every real embedding result must match it before index readiness. |
| **Generation configuration** | Incomplete until selected. | Connection revision, model and structurally valid settings are frozen into build inputs. Prior synthetic success is not required. |
| **Materialization and PipelineVersion** | Absent. | Parsing, chunking, embedding, and index verification succeed for the frozen corpus and profiles. |
| **Logical default route** | A stable project-scoped address, initially unbound, with Automatic updates selected. | First publication creates and binds a genuinely ready Deployment. |
| **Deployment** | **Absent**, not an idle or fake-ready record. | An authorized creation commits one ready current version, with no candidate or previous target. |
| **Benchmark and judge** | Neither required nor silently configured. | The user later chooses comparison and configures its evaluator inputs. |

The table uses the [Indexing records](../../inframeld-indexing/references/records.md#indexing) defined above. “Corpus” means the selected documents. Provisioning records is only the beginning of making that corpus searchable.

<a id="a-default-route-can-exist-before-its-deployment-is-ready"></a>

### A default route can exist before its Deployment is ready

The project-default route exists as a logical address before its real Deployment. Its binding initially holds Automatic updates and the publication control revision.

Until ready, it returns a defined not-ready outcome without generating an answer.

```text
Stable project route exists; no ready Deployment yet
    -> Authorized update invokes the ordinary Build operation
        -> A complete pipeline version becomes ready
            -> Separate conditional first-create command
                -> Create Deployment and bind the route atomically
```

First creation transfers those publication-control settings and binds the route in the same transaction. A simultaneous mode change checks the same record and cannot be ignored merely because this is the first publication.

An explicitly created Deployment instead selects an already-ready initial version directly. **Creating a Pipeline alone never makes it serve traffic.**

<a id="resolve-the-default-through-normal-serving"></a>

<a id="default-route"></a>

<a id="4-resolve-the-default-through-normal-serving"></a>

## Apply accepted PD-RELEASES-01

Accepted [PD-RELEASES-01](decision-deployment-state-and-concurrency.md#approved-resolution) selects this workflow's detailed contract. An automatic update is building while Alice switches Production to Manual and back to Automatic. Bob might promote, roll back or change the default route at the same time. Checking only the current mode could revive an old update's authority and overwrite a newer decision. Apply its exact bounds, current-state checks and failure outcomes. Native implementation and qualification remain separate.

## Resolve the default through normal serving

The recommended HTTP route is:

```text
POST /v1/projects/{projectId}/deployments/default/query
```

`default` is a reserved selector handled by the same resolver as an ordinary Deployment ID. Before first publication it is unbound. It does not pretend that a ready Deployment or version already exists.

An authorized defaults read shows the normal resource IDs, current binding, safe progress and readiness, and the next action. Check project membership and Query permission before showing setup information. The usual response for inaccessible projects must reveal neither existence nor setup details.

<a id="before-first-publication-reject-the-query-before-admission"></a>

### Before first publication, reject the query before admission

An unbound or not-ready alias returns **`409 deployment_not_ready`**, with a safe reason such as models required, documents required, preparing, failed, or explicit release required.

This rejection happens before accepting a query. It generates no answer, creates no job or resources, and makes no model call. Any temporary idempotency reservation rolls back. The caller can inspect permitted setup status and try again after readiness. A GET or query never supplies a canned answer or bypasses retrieval to complete setup.

If dependencies fail after publication, report normal unavailability. Do not silently unbind the route or act as if setup never happened.

<a id="identify-what-actually-served-not-the-convenience-alias"></a>

### Identify what actually served, not the convenience alias

When accepting a query, choose its actual Deployment revision and PipelineVersion and protect them with the normal retention and simultaneous-change rules. A temporary **pin** keeps the selected artifacts from ordinary cleanup during that query.

The response and AnswerReceipt name the actual Deployment, revision, version, and routing group, or **cohort**. The default alias replaces none of these facts and grants no extra permissions.

<a id="deduplicate-the-requested-route-before-selecting-a-fresh-target"></a>

### Deduplicate the requested route before selecting a fresh target

An **idempotency key** identifies one requested operation. After authentication, find or reserve it using the requested logical route, project, and principal **before choosing a fresh serving target**. The first accepted request saves its actual target and version.

After promotion or rebinding the alias to another Deployment, a retry still returns the original operation or receipt, subject to current access. It cannot reinterpret the old key as a new paid query against the new target.

HTTP and MCP identify the route in the same way. A request through the alias and one using an explicit Deployment ID are different routes. Recognizing duplicates across them is not promised.

<a id="keep-http-generated-clients-and-mcp-aligned"></a>

### Keep HTTP, generated clients, and MCP aligned

Represent the alias in the authoritative OpenAPI contract and consume it through the externally generated SDK, the client library used by Studio.

MCP retains its two tools. The recommended default selector is `deploymentId: "default"` with `projectId` required. Ordinary Deployment IDs keep their meaning. HTTP and MCP call the same resolver and query, with the same receipt and affinity rules. Affinity keeps related requests on the same canary version and is not proof of human identity.

`get_answer_receipt` stays unchanged. Setup needs no third tool, mode-administration tool, or separate retriever. The onboarding behavior and two-tool scope are accepted. The exact HTTP and MCP selector shapes remain recommendations.

<a id="make-defaults-discoverable-editable-and-deliberately-repairable"></a>

### Make defaults discoverable, editable, and deliberately repairable

The CLI identifies ordinary default resources and shows publication mode, current version, selected configuration and pending update status. Future Studio presents the same facts, including a **Default** badge. It is not required to inspect or change them in v1.

Renaming a default changes its label, not its ID, binding, mode, or settings. Another Deployment starts in Manual releases unless Automatic updates and its input binding are explicitly chosen.

Changing which inputs an automatic Deployment follows needs Build, Manage releases, input access, the expected revision, and a fresh explicit update decision. Configuration selection is captured by the policy-controlled Build workflow. Saving a working revision alone cannot change the binding. Mode switching retains its separately reviewed update selection under [the publication rules](publication-and-automatic-updates.md#modes).

Changing the default route changes what serves requests, not just a label. It cannot override an attached candidate silently. It invalidates pending work for the old binding and uses the selected Deployment's own mode. An existing manual Deployment must not inherit the old default's automatic setting.

After deliberate deletion, keep setup and removal markers so restart does not recreate defaults. Repair requires an authorized choice of resources and mode. Deletion cancels pending publication, and an old default-route job cannot bring the removed Deployment back.

A missing default group blocks uploads. Repair follows normal lifecycle and permission rules, without a special one-time reset bypass.

CLI Deployment management owns the complete mode and default-route journey. It calls publication-mode changes and default-binding operations, rather than writing release state itself. Switching Automatic to Manual invalidates pending publication authority. Re-enabling Automatic initially reviews the currently serving version's configuration. Using different saved settings requires deliberate selection and fresh admission. An attached candidate, even at zero allocation, blocks enabling Automatic.

For example, Bob deliberately deletes the old default and later selects a ready Manual Deployment as its replacement. Review the route change, current authority and candidate restrictions before saving the new binding. Preserve that Deployment's Manual mode and invalidate authority tied to the old binding. If state changes during review, stop and review again. Do not silently accept newer state or recreate the deleted resource. Repairing a missing upload-default group belongs to ordinary Access administration, presented by CLI access management, not the release operation.

<a id="deployment-state-and-authority"></a>

## Deployment state and authority

A Deployment selects ready PipelineVersions using current, candidate and designated previous pointers.

Manage releases is one exact-Deployment action covering publication, canary control, rollback, mode switches and automatic input selection. It replaces older Publish/deploy terminology. Build, Delete and non-serving configuration Edit remain separate.

Human creation uses project Create Deployment and atomically records the ready initial version, Deployment and explicit creator grants. The reviewed catalogue assigns thirteen Pipeline and seven Deployment creator actions, including separate query/evaluation inspection and own-feedback authority. Creator history never overrides later removal, and existing resources receive no automatic backfill.

Private starter provisioning explicitly makes its creator both group member and manager. That supplies neither Build nor release authority by itself.

Before the first default Deployment exists, the default binding holds its publication mode/control revision and stays not-ready. Do not create a fake version. First publication transfers that state atomically through its separate creation checks.
