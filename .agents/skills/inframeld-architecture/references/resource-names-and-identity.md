# Resource names, display names and identity

<a id="resource-names-display-names-and-identity"></a>

Alice selects `legal-research`, sees the label Legal Research and saves a permanent project ID. These three values serve different purposes. Renaming a resource must not redirect an admitted operation or transfer its authority.

> **Status:** accepted behavior is stated separately from proposed representations and qualification work. Existing Python types, generated OpenAPI and migrations own implemented shapes. Pending decisions are not accepted by this reference.

<a id="keep-identity-resource-names-and-imported-access-separate"></a>

#### Keep identity, resource names and imported access separate

The existing cookie/CSRF and deployment OIDC implementation remains in place. Hydra adds human CLI login through a small standalone Ory browser account UI. Full Studio is not required. Additional SSO onboarding is deferred, but existing SSO-related code is not removed. Target discovery uses one server URL and publishes operator-configured public API and issuer information, never private administration endpoints or secrets.

[Resource names](#resource-naming) select resources, not permissions. Project names are unique within an installation. Pipeline, Deployment, connection, collection and profile names are scoped by project and resource type.

For a source or imported evaluation dataset, an authorized human explicitly maps its audience to destination groups. Applications importing cases use the current saved human-approved Pipeline import audience under [Evaluation audience administration](../../inframeld-evaluation/references/case-audiences.md#case-audiences). A matching group name or imported metadata cannot grant access. Imported case content needs protection before its source is linked. After linking, access must also satisfy the current source permissions.

The [accepted dispatch](../../inframeld-access-models/references/credential-dispatch.md#credential-dispatch) and [reviewed capability catalogue](../../inframeld-access-models/references/actions-and-initial-grants.md#reviewed-capability-catalogue) resolve the choices recorded here. The [V1 scope](v1-scope-and-extension-boundaries.md) identifies remaining invitation, naming, imported-audience and other specification work. These accepted rules do not imply that all those operations already exist.

<a id="resource-naming"></a>

<a id="resource-names-display-names-and-permanent-ids"></a>

## Resource names, display names and permanent IDs

Alice sees a project displayed as **Legal Research** and selects it with `--project legal-research`. The backend resolves that name under the current installation and permissions, then uses the project's permanent ID for saved selection and relationships. Another project may share the display name, but not the resource name in the same naming scope.

| Term | Meaning | Example and constraint |
| --- | --- | --- |
| **Name** (`name`) | Exact, command-friendly resource selector. | `legal-research`. Unique in the resource's defined scope. It is not a display-name lookup, fuzzy match or permission. |
| **Display name** (`display_name`) | Human-readable presentation label. | `Legal Research`. Editable and non-unique. Never use it to resolve a resource or establish identity. |
| **ID** (`id`) | Permanent application-owned identity. | A UUID for these named resources. Stored relationships, saved selection and admitted operations retain this identity through renames. |

This is the accepted product vocabulary, not a claim that all current fields or selectors implement it. Project names are unique across the installation's single organization. Pipelines, Deployments and model connections have names unique per project and resource type. Uniqueness includes inaccessible resources without disclosing their owners. Other configurable resources use this vocabulary when their named interfaces are specified. Their exact naming scope, reference schemas and administration contracts must be settled explicitly. Do not add names to every internal version, job or derived artifact by implication.

Changing a display name alone preserves the name and ID. An explicit resource-name change preserves the ID and stored bindings. Retired names cannot be reassigned to a different resource in the same scope. Requests using an old name stop, with current-name guidance only when authorized, rather than silently redirecting. Current authorization and availability checks still apply to IDs and names. Configuration references resolve to exact resource identities and required immutable revisions. Execution does not continually reinterpret their names. Renaming profile metadata must not change its immutable processing or embedding meaning.

Names contain 1–63 ASCII characters: lowercase letters, digits and hyphens, starting with a letter and ending with a letter or digit. There are no additional reserved words, so `production` is valid. Validate the exact submitted selector without normalization. Lookup never corrects spelling, matches a prefix/Display name or chooses a fuzzy result. Name/ID selectors are mutually exclusive even when both identify the same resource.

A submitted replacement Display name contains 1–128 Unicode code points. It must be nonblank, have no surrounding whitespace, and contain no controls or line/paragraph separators. Display names remain non-unique. These input rules do not reject retained legacy labels on migration, reads, replay or selector-only updates. Never normalize or truncate a retained value. Human presentation escapes unsafe control content without changing storage or machine results.

Suggestions are previews, never lookup or allocation rules. Decompose Unicode, remove combining marks, lowercase ASCII, replace other runs with hyphens and trim surrounding hyphens. For example, `Légal Research` suggests `legal-research`. A suggestion that is invalid, too long or unavailable requires explicit valid input. Never truncate, add a prefix/suffix or silently allocate it. Starter generation retains its separate bounded collision policy.

An explicit user-selected name that collides must fail or return to review. Never silently suffix it. A clean available suggestion is preferred for a deliberately created project, with a reviewed alternative only when necessary. Availability checks are advisory until atomic backend allocation. Report unavailability without disclosing the private resource, owner or deletion history. Automatically generated starter names alone have bounded collision retries inside ordinary atomic provisioning.

Changing Name and Display name together is atomic under current authority and expected-state checks. A collision, invalid input, revoked authority or stale review leaves both unchanged. An uncertain rename is reconciled through the resource ID/original operation, not by resolving its old name to another object. Deletion retires the current name even without a previous rename.

Across multiple renames, authorized guidance identifies the current name without automatically following an alias chain. Minimal reservation/history metadata follows the accepted [retention and erasure policy](../../inframeld-knowledge/references/decision-retention-erasure-policy.md). Keep only the safety metadata needed for non-reuse and original-ID recovery, never deleted content or a registry surviving a complete local factory reset. Same-resource restoration details remain unspecified.

Deployment names such as `contracts-development` and `contracts-production` are project-scoped, not Pipeline-relative paths such as `contracts/production`. Bare `production` is not newly reserved. A Pipeline and Deployment may share a name because their types differ. Names confer no environment isolation, grant, publication mode or default selection. Every Deployment serves a ready version. Direct Pipeline querying needs no development Deployment. Renaming a Deployment preserves its customer endpoint, live pointers and policy. Renaming a connection changes neither provider model ID nor endpoint/credentials. The exact endpoint schema is not prescribed by naming.

Saved project preferences use UUIDs and remain separate per target/account. Admitted jobs retain their original resource IDs through rename. Deleted/inaccessible selections fail without creating another starter or selecting a substitute. [CLI context](../../inframeld-application-contracts/references/cli-targets-and-accounts.md#cli-context) specifies resolution and one-shot overrides. [starter provisioning](first-use-and-private-defaults.md#starter-naming) specifies generated names.

Keep existing code and physical field spellings accurate when describing implementation. For example, the inspected [ProjectRow](../../../../apps/backend/src/inframeld_backend/access/infrastructure/rows/project_row.py) and [initial migration](../../../../apps/backend/migrations/versions/0001_initial.py) have one text `name` field, not separate `name`/`display_name` fields or the selected resource-name contract. The [Access persistence map](../../inframeld-access-models/references/access-persistence.md#identity-ownership-and-membership-tables) preserves those spellings. Do not infer unique selector behavior from the column name or silently reinterpret existing values. The approved transition preserves that unrestricted text exactly as the legacy Display name and adds a distinct initially unallocated selector with a separate metadata revision. Legacy Projects remain addressable by ID. An authorized human explicitly allocates the first selector by ID. Migration never invents a slug or reinterprets the label. Physical field names and constraints remain implementation choices. This recording changes no database, public wire field or application behavior.

## Typed resolution and Project metadata

Resolution binds installation/Organization, expected resource kind, naming scope and exact Name. Its result identifies the actual kind, permanent ID, authoritative scope, stored Name, binding revision and current/retired state. The production resolver must validate every returned binding field against the request, including Project scope where applicable. A missing, retired or ambiguous exact match fails without a substitute. A wrong-kind, wrong-Project or wrong-name adapter result fails closed without another-kind lookup. A Collection and Processing profile may share a spelling because their types differ. A Collection binding cannot satisfy a profile request.

Access owns Project resolution and metadata changes. Current Project membership permits basic metadata disclosure. A change requires the human-only exact-Project `edit-project-metadata` action, current eligibility/membership and expected metadata revision. Permission revisions remain separate. First allocation and combined Name/Display-name updates save name reservation, metadata, audit and original outcome together. A collision, stale review or revoked grant leaves both fields unchanged. Recheck current authority for protected replay. Recover an uncertain result through the permanent ID and original operation, not the retired selector.

[The approved metadata decision](../../inframeld-access-models/references/decision-project-metadata-authority.md) records the authority, repair and delivery boundary under [ADR-0124](../../../../docs/adr/ADR-0124-authorize-project-metadata-changes-explicitly.md). #120 must deliver real Project HTTP/PostgreSQL resolution, first allocation and rename, lossless legacy transitions, narrow first-grant repair, and typed cross-kind/scope checks in the same production-used resolver. Controlled Collection/Profile bindings qualify that boundary without claiming future CRUD or adapters. Full CLI context management and future resource provisioning are separate delivery work. All of this #120 behavior remains unimplemented at this recording checkpoint.
