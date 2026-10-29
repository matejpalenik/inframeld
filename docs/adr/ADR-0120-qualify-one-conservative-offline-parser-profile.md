# ADR-0120: Qualify one conservative offline parser profile

**Status:** Accepted

**Date:** 2026-10-29

## Context and Problem Statement

A small uploaded file can expand into huge content or spawn children. File size alone cannot protect the host or isolate the next document.

## Considered Options

- Use the focused bounded contract above. Selected.
- Qualify several parser hosts/profiles initially, multiplying the required hostile-fixture evidence.

## Decision Outcome

Apply the [complete accepted PD-INDEXING-05 contract](../../.agents/skills/inframeld-indexing/references/decision-parser-runtime-profile.md#approved-resolution). It owns the exact behavior, bounds, current-state checks and failure outcomes. Select one initial production qualification target: patched Ubuntu Server 24.04 LTS x86-64, unified cgroup v2, enforcing AppArmor and qualified pinned Docker/Compose, bubblewrap, seccomp/LSM policies, parser image, Docling and assets. Exact supported patch versions, packages, policy hashes and image/asset digests become the release manifest's reproducible evidence. Other hosts, architectures and desktop-container VMs are unqualified until they pass this same protection profile; an unsupported local parser reports unavailable, not a privileged fallback. A compatible CLI may still target a qualified remote installation.

The developer explicitly approved the presented batch-4 contracts and delegated selection of all remaining decisions to the assistant on 2026-10-29, requesting repository/GitHub recording and plain-language justification. This resolution is accepted under that authority. It selects logical policy, not implemented code or passing qualification.

## Consequences

Some legitimate large or scanned documents are rejected initially, and unqualified hosts cannot parse. This keeps the supported security boundary narrow and testable.

Alice's PDF exceeds the expanded-text limit. Its attempt fails and all descendants/scratch are removed before Bob's file starts. If cleanup cannot be verified, the parser is quarantined rather than reused.

Implementation, measured support and qualification remain separate. A chosen threshold is not a measured result. No application code, public endpoint or passing runtime evidence is delivered here.

## Links

- [Owning contract](../../.agents/skills/inframeld-indexing/references/decision-parser-runtime-profile.md#approved-resolution)
- [Decision finalization](../development/guides/architecture-decisions.md#just-in-time-architecture-decisions)
