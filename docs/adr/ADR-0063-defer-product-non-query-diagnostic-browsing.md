# ADR-0063: Defer product non-query diagnostic browsing

**Status:** Accepted.

**Date:** 2026-10-04

## Context and Problem Statement

Query-trace permissions already target an exact Pipeline or Deployment. Extending them to generator, judge, processing or sync diagnostics would widen disclosure and require additional owner-specific permissions. V1 still needs ordinary job, case and result inspection without a general diagnostic browser.

## Considered Options

The reviewed proposal deferred product-facing non-query diagnostic browsing while retaining narrow domain inspection. No broader trace-browser permission was selected.

## Decision Outcome

Keep non-query diagnostic trace browsing behind the existing host-operator boundary in v1. Do not introduce a general Project/installation trace-read grant or product audit-browser API. Direct/live query traces retain `inspect-query-traces` on their exact resource with current evidence checks.

Domain job, case and Evaluation result inspection remains available through its own authorized application contracts. Diagnostic recording and retention continue under existing controls; deferring browsing does not disable required audit or create hidden product disclosure.

## Consequences

- Applications and humans cannot obtain non-query diagnostics through a query-inspection grant.
- Future product diagnostic browsing needs reviewed owner/target permissions and protection rules.
- Host operators retain their existing infrastructure trust boundary; ordinary login does not acquire host authority.
- Implementation and qualification are pending. [Observability](../development/observability.md#non-query-diagnostics) owns the current scope.

## Links

- [Access trace authority](../development/access-control.md#trace-authority).
- [Evaluation result inspection](../development/evaluation.md#history).
- [CLI delivery](../development/cli-delivery-plan.md).
