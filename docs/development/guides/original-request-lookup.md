# Recover an original admission

Alice submits a grant for Bob but loses its acknowledgment. She retained the original request key, installation, Organization, Project and authority guard. `POST /v1/operations/lookup` reads the backend's retained admission metadata without assigning the grant again. The [owning contract](../../../.agents/skills/inframeld-application-contracts/references/operation-recovery-contracts.md#original-request-lookup) defines authority and unknown outcomes.

The HTTP router, Access authorization and PostgreSQL projection are implemented. The delivered grant and Project metadata routes provide complete business operations. Shared admission and reservation lookup support does not imply other domain endpoints. Native-client qualification and real persistence verification remain distinct checks. No CLI lookup command or local recovery-hint runtime is delivered here.

## Retain the original request context

Capture the expected guard before submitting the original operation. It describes that operation's authority meaning and grants no permission. Use the original installation and scope even if an alias, current Project or default has changed. Authentication supplies the caller's principal, so the body accepts no actor identifier.

For grant lookup, the caller must still be an eligible human with Project membership/visibility and can-use-and-grant `create-access-groups` on the original Project. The fixed grant route rejects a weaker Project action-use guard. Lookup does not reapply the recipient's assignment-time eligibility or an old expected access revision.

The [lookup request model](../../../apps/backend/src/inframeld_backend/shared/http/requests/original_operation_lookup_request.py) owns the native input. This is a complete new scratch request file at `/private/tmp/original-operation-lookup.json`, with illustrative UUIDs to replace using the retained original context:

```json
{
  "installationId": "00000000-0000-4000-8000-000000000001",
  "organizationId": "00000000-0000-4000-8000-000000000002",
  "projectId": "00000000-0000-4000-8000-000000000003",
  "method": "POST",
  "requestedRoute": "/v1/projects/{project_id}/grants",
  "key": "grant-bob-1",
  "expectedAuthority": {
    "family": "project_grant_read",
    "actionId": "create-access-groups"
  }
}
```

Send that JSON to the configured backend's `/v1/operations/lookup` with `Content-Type: application/json` and the existing human credential. A browser-cookie request also needs its trusted `Origin` and `X-Inframeld-CSRF: 1`. Human bearer authentication follows the existing credential contract. The original key belongs in the body, and lookup accepts no command payload or fingerprint. The received body is limited to 32 KiB. Unknown fields, duplicate JSON keys and invalid guard combinations fail validation.

For a Project metadata PATCH, retain canonical route `/v1/projects/{project_id}/metadata`, family `project_action_use` and action `edit-project-metadata`. Current exact metadata authority still applies before lookup. The [naming guide](../../../apps/docs/src/app/guides/name-and-rename-project/page.mdx#handle-a-failure-or-lost-acknowledgment) explains same-key write recovery. Metadata lookup does not repeat the change or return current Project fields.

Generic Project lookup uses `project_action_use` and the accepted original Project action. Organization lookup uses `organization_action_use`, its original Organization action and explicit `projectId: null`. Preserve the original method and canonical logical route exactly. Today's grants, defaults or aliases cannot reconstruct missing original meaning.

## Interpret the observation

Access checks the expected guard from current facts before reservation history is searched. A retained record must then match the entire original identity and immutable authority binding.

| HTTP 200 outcome | Meaning |
| --- | --- |
| `completed_synchronous` | Retained completion metadata, original operation ID, safe classification and unchanged expiry |
| `accepted_asynchronous` | Original admission is confirmed, with a known or explicitly unknown job reference and dispatch not established |
| `in_progress` | The original synchronous operation remains unfinished |
| `recovery_required` | The original operation requires recovery without an established asynchronous admission |
| `unresolved` | No retained authoritative match can be established |

Unresolved has exactly one field, `outcome`. It does not explain whether history was absent, expired, insufficiently bound or mismatched. It does not establish that nothing happened. A retained asynchronous admission remains accepted regardless of a later job state. The public lookup response returns `jobReference` as either `"unknown"` or a strict object such as `{"jobId": "00000000-0000-4000-8000-000000000004"}`. A known ID identifies that original work, but `dispatch` remains `not_established`. It establishes no execution state, progress, result content or permission to inspect the job later. This component supplies no job-inspection endpoint or CLI command.

For the delivered Project action-use path, the reference is disclosed only after current lookup authorization and an exact original ordinary product-job binding. Missing or malformed optional job data leaves admission confirmed with an unknown reference. It does not turn a non-authoritative original record into a match or hide a malformed original outcome or database failure. Cleanup-origin attribution cannot supply an ordinary product Job ID.

Invalid input, missing/rejected authentication, hidden scope, denied current authority and unavailable dependencies remain safe problem responses. A timeout or disconnect is a failed observation. Neither Unresolved nor a failed observation authorizes resubmission, a replacement operation or a provider call. Repeated successful reads preserve the original expiry.

## Verify the boundary

The [service tests](../../../apps/backend/tests/unit/shared/application/services/test_original_operation_lookup_service.py) cover authorization before history and outcome classification. The [HTTP tests](../../../apps/backend/tests/unit/shared/http/routes/test_original_operation_lookup_routes.py) cover framing, authentication, CSRF and response shape. PostgreSQL scenarios cover [Project identity and storage](../../../apps/backend/tests/integration/idempotency/test_original_operation_lookup_postgres.py), [Organization scope and current authority](../../../apps/backend/tests/integration/idempotency/test_organization_operation_lookup_postgres.py), [legacy migration](../../../apps/backend/tests/integration/idempotency/test_operation_lookup_migration_postgres.py) and the [real grant HTTP workflow](../../../apps/backend/tests/integration/access/test_project_grant_http_postgres.py).

Run `pnpm check:backend` for fast checks. Follow the [private integration procedure](testing.md#integration-tests) for PostgreSQL evidence. The [SDK endpoint walkthrough](../../../packages/sdk-tools/docs/adding-endpoint.md) owns native generation and complete client qualification. Controlled SDK fixtures establish HTTP fidelity, while PostgreSQL scenarios establish persistence behavior.
