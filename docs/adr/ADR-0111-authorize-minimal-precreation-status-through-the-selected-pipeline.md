# ADR-0111: Authorize minimal precreation status through the selected Pipeline

**Status:** Accepted

**Date:** 2026-10-29

## Context and Problem Statement

Alice has Query on her starter Pipeline, but the first build failed before any Deployment was created. Query on a nonexistent Deployment cannot authorize useful setup details. Bob guessing the Project ID must not learn the Project's state.

## Considered Options

- Use the focused bounded contract above. Selected.
- Return only generic not-ready status and require a separate existing-resource inspection for all details.

## Decision Outcome

Apply the [complete accepted PD-ACCESS-06 contract](../../.agents/skills/inframeld-access-models/references/decision-setup-read-authority.md#approved-resolution). It owns the exact behavior, bounds, current-state checks and failure outcomes. Use an explicit minimal Pipeline-authorized precreation setup projection through the shared default resolver. Require current eligible principal, Project membership and Query on the exact existing Pipeline named by the server-owned starter/default setup binding. Do not infer project-wide Query, scan for any visible Pipeline or trust a caller-supplied replacement target. Existing human/application eligibility and current credential checks apply. No new permission, placeholder Deployment or administrative MCP tool is introduced.

The developer explicitly approved the presented batch-4 contracts and delegated selection of all remaining decisions to the assistant on 2026-10-29, requesting repository/GitHub recording and plain-language justification. This resolution is accepted under that authority. It selects logical policy, not implemented code or passing qualification.

## Consequences

Because the minimum setup view has an explicit existing authority, Alice can understand first-use failure without inventing a fake Deployment. Because richer fields keep separate checks, Query does not expose teammates' jobs or configuration. The alternative is always returning a generic not-ready result and requiring separate inspection. That is narrower, but makes setup harder to explain in CLI/MCP clients.

Alice can learn that her authorized starter Pipeline is not ready and that an authorized Build is the next step. Detailed build progress is shown only if she also passes the existing job-inspection checks. Bob has no Project/Pipeline access, so he learns neither that a build failed nor which resources exist. After first publication, Alice needs Query on the new Deployment; having Pipeline Query alone cannot bypass that transition.

Implementation, measured support and qualification remain separate. A chosen threshold is not a measured result. No application code, public endpoint or passing runtime evidence is delivered here.

## Links

- [Owning contract](../../.agents/skills/inframeld-access-models/references/decision-setup-read-authority.md#approved-resolution)
- [Decision finalization](../development/guides/architecture-decisions.md#just-in-time-architecture-decisions)
