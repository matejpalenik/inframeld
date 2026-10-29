# ADR-0098: Publish bounded first-party discovery

**Status:** Accepted

**Date:** 2026-10-28

## Context and Problem Statement

A user supplies one API URL to discover an installation without exposing saved credentials. Issue #118 must establish this boundary before target persistence and login in #159/#160. The developer approved the backend and stateless Rust validator together, with private/VPN HTTPS and explicit proxies supported.

## Considered Options

A backend-only endpoint leaves the client safety acceptance unverified. A custom discovery protocol duplicates standard metadata. The selected profile uses RFC 9728 and Hydra OIDC metadata with a small first-party extension.

## Decision Outcome

Publish resource, one authorization server, the API scope and header bearer transport. The inframeld extension contains schema_version 1, persistent installation_id and fixed client_id inframeld-cli. Canonical API identity equals the configured Hydra audience. Exact identifiers retain their spelling and path meaning. Metadata is anonymous and never derives authority from request headers.

Discovery has no persistent cache, uses no-store responses and allows ten seconds overall, five seconds per request and 64 KiB per response. Redirects and retries are disabled. Ordinary targets require verified HTTPS. Only trusted managed-runtime context permits exact recorded literal-loopback HTTP origins. Metadata cannot grant that exception. Private/VPN HTTPS and explicitly configured proxies remain supported for ordinary targets. Managed-local discovery rejects explicit proxies before I/O and continues to disable inherited proxies.

A fresh generated application client reads API metadata without credentials. The maintained OpenID Connect library validates Hydra metadata through a bounded HTTP adapter. Supported Hydra protocol and key-set endpoints remain on the issuer origin. The first-party provider must advertise authorization-code and refresh grants, the code response, public-client token authentication and S256. Omitted grant metadata uses the standard authorization-code/implicit default, which does not satisfy this profile's refresh requirement. [ADR-0099](ADR-0099-preserve-encoded-relative-paths-in-generated-clients.md) records the generated path capability used to preserve RFC 9728 request paths. Discovery returns facts without saving targets, reading credentials or starting login. It does not establish release compatibility.

## Consequences

Reuse existing installation identity and startup resources. Configure discovery explicitly and fail startup on inconsistent enabled settings. An unconfigured endpoint returns a safe unavailable response. SDK generation and all native bindings must cover the new operations. Runtime management and full login qualification remain separate. This decision is accepted. The [verification report](../development/reports/server-discovery-verification.md) separates implemented behavior, local execution and pending final-revision CI.

## Links

- [Target discovery](../../.agents/skills/inframeld-application-contracts/references/cli-targets-and-accounts.md#target-discovery)
- [Managed local boundary](../../.agents/skills/inframeld-application-contracts/references/cli-local-runtime.md#managed-local-http)
- [RFC 9728](https://www.rfc-editor.org/rfc/rfc9728.html)
