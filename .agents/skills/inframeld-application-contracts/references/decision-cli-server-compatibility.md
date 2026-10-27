# PD-CONTRACTS-03: Define supported CLI and server release combinations

**Status:** PENDING

**Owner:** `inframeld-application-contracts`

**Issue kind:** Public compatibility contract.

This reference supports a future discussion. Its recommendation is not accepted behavior. Current guides and ADRs retain authority.

## Contents

- [Problem and example](#problem-and-example)
- [Accepted context and evidence](#accepted-context-and-evidence)
- [Alternatives and trade-offs](#alternatives-and-trade-offs)
- [Non-binding recommendation](#non-binding-recommendation)
- [Decision trigger and stopping boundary](#decision-trigger-and-stopping-boundary)
- [Architectural impact and dependencies](#architectural-impact-and-dependencies)
- [Open questions and required evidence](#open-questions-and-required-evidence)
- [Sources and finalization](#sources-and-finalization)

## Problem and example

Alice upgrades one CLI and uses it with local, test and Production installations that were upgraded at different times. A mutation is admitted by an older server, but the new CLI cannot decode its result. Starting again with a fresh key could duplicate work even though issuer discovery succeeded.

Native OpenAPI and generated clients qualify one contract, not a supported version-skew policy. The accepted release scope requires compatibility evidence and release guidance, but no supported release range or breaking-change rule is selected.

## Accepted context and evidence

Preserve native FastAPI OpenAPI 3.1.x, generated application clients and independent explicit installation/account selection. Do not choose a generator or add a competing handwritten client here. The /v1 prefix alone does not establish every future release combination.

Stable operation identities and no automatic paid replay remain mandatory after acknowledgment/decode failure. API/worker/schema compatibility is separate from external CLI compatibility. Unsupported combinations should fail before effects where possible, without claiming certainty when admission may already have succeeded.

## Alternatives and trade-offs

1. **Support matching qualified releases first.** Publish CLI/runtime compatibility in release metadata and reject unsupported combinations clearly. This minimizes the matrix, but operators need coordinated upgrades.
2. **Support a small explicit adjacent-release window.** Test a documented older/newer range and use capability/version checks where necessary. This improves independent upgrades, but increases compatibility and unknown-enum/result handling work.

## Non-binding recommendation

**Proposal only.** Prefer matching qualified releases initially, with clear safe incompatibility handling and no hidden retry. Expand the window only when demonstrated demand and tests justify it. The support policy remains pending until approved.

## Decision trigger and stopping boundary

Before distributing independently installable CLI/runtime releases or making a compatibility-sensitive public contract change.

Pause the support/version-skew choice, not ordinary backend contract work that preserves current behavior.

## Architectural impact and dependencies

CLI release metadata, server discovery/compatibility response where selected, generated-client qualification and upgrade guidance. No discovery endpoint or version field is invented by this reference.

## Open questions and required evidence

- Which combinations are supported at first release?
- How are additive fields and unknown enums/outcome variants handled?
- What is breaking within v1 and how is it introduced?
- How does a client recover after admission but before decoding acknowledgment?

## Sources and finalization

- [Generated clients and CLI contracts](http-mcp-and-generated-clients.md).
- [CLI-first decision](../../../../docs/adr/ADR-0055-deliver-cli-first-v1-through-openapi-generated-clients.md).
- [Runtime compatibility is separate](../../../../docs/development/operations/upgrades.md).

When the trigger applies, follow [the decision finalization workflow](../../../../docs/development/guides/architecture-decisions.md#just-in-time-architecture-decisions). Obtain explicit approval of the concrete design and named documentation edits, reconcile affected sources and diagrams, and complete the repository-wide consistency pass before dependent implementation. Acceptance does not establish runtime qualification or authorize application writes.
