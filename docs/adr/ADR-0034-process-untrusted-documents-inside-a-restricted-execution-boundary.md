# ADR-0034: Process untrusted documents inside a restricted execution boundary

Status: Accepted

**Date:** 2026-09-24

## Context and Problem Statement

Document parsers handle attacker-controlled bytes and can consume excessive resources or contain vulnerabilities. Ordinary application-worker permissions are too broad for that work.

## Considered Options

- A restricted per-attempt processing boundary supervised by the worker.
- Parse directly inside a privileged application process.
- Rely only on filename checks, library success, or container packaging.

These options summarize the recorded choices, exclusions, and deferrals. They do not imply an additional comparison or benchmark was performed during this rewrite.

## Decision Outcome

Validate and bound uploads, then process document bytes in the documented restricted parser environment. Separate the worker, supervisor, and processing child. Restrict credentials, network access, filesystem access, resource use, and lifetime. Validate returned artifacts before accepting them as application data, and reject unsupported hosts rather than silently weakening isolation.

**Example.** A conversion that times out must lose its attempt’s process lifetime and cannot publish a half-validated artifact merely because some output files exist.

## Consequences

- Parser faults and excessive work are contained by a boundary separate from application authority.
- The deployed host, container, process, and enforcement mechanisms need joint qualification. Operating-system isolation does not make extracted content trustworthy instructions or guarantee a document will parse successfully.

## Links

Implementation evidence and qualification limits are recorded in the current guides below. This ADR records the design choice; the editorial rewrite did not verify runtime behavior.

- [Current ingestion security](../development/ingestion-security.md).
- [Current deployment](../development/deployment.md).
