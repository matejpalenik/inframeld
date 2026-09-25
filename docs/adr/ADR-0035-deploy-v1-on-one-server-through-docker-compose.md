# ADR-0035: Deploy v1 on one server through Docker Compose

Status: Accepted

**Date:** 2026-09-17

## Context and Problem Statement

The product needs a production-capable installation that one developer can understand and maintain. Separate cloud-specific and local architectures would multiply integration and operational work.

## Considered Options

- One Docker Compose deployment model for trials and production.
- A required Vercel/AWS-hosted split or distributed orchestration platform.
- Treat a disposable local trial as evidence of production readiness.

These options summarize the recorded choices, exclusions, and deferrals. They do not imply an additional comparison or benchmark was performed during this rewrite.

## Decision Outcome

Use the same single-server Docker Compose model for supported v1 installations. Give API, worker, parser boundary, identity, relational storage, numerical storage, and artifact storage explicit responsibilities. Keep private services and durable paths inside their defined boundaries. AWS and Vercel are not required.

**Example.** A trial can use smaller limits, but a production installation still needs durable keys, approved network exposure, controlled upgrades, and a tested recovery process.

## Consequences

- Development and operation use one understandable runtime arrangement without a required service per business domain.
- The host remains a shared resource and failure boundary. Security enforcement, capacity, exact image pins, persistence, backup, and upgrades still need deployment qualification.

## Links

Implementation evidence and qualification limits are recorded in the current guides below. This ADR records the design choice; the editorial rewrite did not verify runtime behavior.

- [Current deployment](../development/deployment.md).
- [Current upgrades and recovery](../development/upgrades-and-recovery.md).
- Related decisions: [ADR-0036](ADR-0036-use-seaweedfs-through-the-application-s3-storage-boundary.md).
