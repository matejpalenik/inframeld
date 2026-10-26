# ADR-0086: Serve recovery notifications through a private backend process

**Status:** Accepted

**Date:** 2026-10-25

## Context and Problem Statement

When Alice saves a replacement password, Kratos must deliver evidence even though Alice cannot yet use the product API. The callback needs database access and a dedicated service credential, without exposing a recovery control plane through public ingress.

## Considered Options

- Add callbacks to the public API and depend on ingress path restrictions.
- Run a small private application from the existing backend image.

## Decision Outcome

Use a separate `recovery-callbacks` process on container port 8081, without published ports or documentation endpoints. Bootstrap supplies focused database, provider and protected hook-key configuration. The public application does not mount its routes.

The application owns short transactions and commits receipts and their required recovery state before acknowledging them. Native hooks supply the evidence defined in [ADR-0085](ADR-0085-bind-password-settings-evidence-to-original-recoveries.md). This process neither calls Hydra nor releases recovery blocks.

## Consequences

This keeps the callback boundary independent of browser authentication and public routing. It adds one lightweight deployment role using the same code and schema. Private networking complements dedicated key authentication, strict bounded input and safe errors. Runtime packaging remains #95. Native-hook activation remains explicit until the cleanup worker exists.

## Links

- [Private handoff](../../.agents/skills/inframeld-access-models/references/private-recovery-handoff.md)
- [Identity coordination](ADR-0082-coordinate-first-admission-and-recovery-by-identity.md)
- [Delivery issue #243](https://github.com/matejpalenik/inframeld/issues/243)

## Implementation notes

The private service reads coordinated association facts and decides which original recovery a settings event belongs to. Persistence checks immutable bindings and records the checked result. Password evidence updates the existing aggregate and returns the stored receipt time. An application budget value derives the initial twelve-attempt/one-hour limits from that time, and the writer ensures the original handoff once.

Bootstrap assembles shared request-local collaborators and an instantiated protected-file key reader. Access HTTP middleware adds non-cacheable headers without buffering responses. The settings and password-saved Jsonnet templates remain self-contained because the pinned Kratos sandbox rejects imports. Both native hook paths receive behavioral coverage.

[Private delivery](../../.agents/skills/inframeld-access-models/references/private-recovery-handoff.md#implemented-private-delivery) records implementation and qualification limits separately from this process decision.
