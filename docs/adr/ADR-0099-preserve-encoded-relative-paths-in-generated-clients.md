# ADR-0099: Preserve encoded relative paths in generated clients

**Status:** Accepted

**Date:** 2026-10-28

## Context and Problem Statement

Alice discovers an API at `/api/v1`. RFC 9728 requires the metadata request to retain both path segments. Ordinary generated path parameters encode the slash as `%2F`. Decoding before serialization also loses the distinction between a separator and an originally encoded slash. The developer approved an explicit generated-client capability while retaining generated application requests.

## Considered Options

Handwritten discovery HTTP would bypass the selected application SDK boundary. Globally changing path encoding would alter ordinary parameter behavior. A schema annotation confines the new semantics to parameters that explicitly require an encoded relative path.

## Decision Outcome

Use `x-inframeld-encoded-path: true` on the native path-parameter schema. Selected generators preserve literal separators and existing escapes, validate the encoded relative path before dispatch and leave ordinary parameters unchanged. The argument remains a string. Its documented meaning is an already percent-encoded relative path, without a leading slash.

The [generator guide](../../packages/sdk-tools/docs/generators.md#encoded-relative-path-parameters) owns the input rules and maintenance procedure. The first consumer is the discovery operation accepted through ADR-0098. No public CLI option or handwritten transport is introduced.

## Consequences

The three patched generators and TypeScript parser retain this capability through explicit generation. Shared raw-wire assertions and native zero-dispatch regressions qualify it. Generated sources remain generator-owned. SDKs remain unpublished, so no compatibility alias is needed for the corrected discovery argument semantics. The [verification report](../development/reports/server-discovery-verification.md) separates local evidence and pending platform CI.

## Links

- [Discovery profile](ADR-0098-publish-bounded-first-party-discovery.md)
- [RFC 9728 metadata request](https://www.rfc-editor.org/rfc/rfc9728.html#section-3.1)
