# ADR-0045: Support preconfigured MCP clients with application credentials

Status: Accepted

**Date:** 2026-09-19

## Context and Problem Statement

MCP clients differ in how they configure authentication and preserve retry information. A static application key does not implement universal OAuth discovery or establish a human subject.

## Considered Options

- Trusted header-capable clients configured with resource-bound application credentials.
- Claim universal client support from a static bearer key.
- Implement OAuth discovery, token exchange, and delegated-user access in v1.

These options summarize the recorded choices, exclusions, and deferrals. They do not imply an additional comparison or benchmark was performed during this rewrite.

## Decision Outcome

Support the accepted preconfigured client profile: the client supplies the application credential, the correct MCP resource binding, and stable business idempotency keys. Authenticate every mounted request and reject unsupported delegation claims. Keep the tool arguments separate from credential verification. Universal OAuth interoperability and verified human delegation remain outside v1.

**Example.** A tool argument naming Alice cannot make SupportBot act with Alice’s HR permissions. Its verified actor remains SupportBot.

## Consequences

- Supported integrations have a clear authentication and retry contract without another authorization-server stack.
- Client capability and mounted transport behavior must be qualified. Everyone using an application’s valid authority shares that account’s permitted scope.

## Links

Implementation evidence and qualification limits are recorded in the current guides below. This ADR records the design choice; the editorial rewrite did not verify runtime behavior.

- [Current mcp](../development/mcp.md).
- [Current access control](../development/access-control.md).
- Related decisions: [ADR-0044](ADR-0044-provide-mcp-through-a-thin-adapter-in-the-existing-api-process.md).
