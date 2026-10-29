# PD-INDEXING-05: Select and prove a bounded parser runtime

**Status:** ACCEPTED on 2026-10-29 in [ADR-0120](../../../../docs/adr/ADR-0120-qualify-one-conservative-offline-parser-profile.md). Implementation and qualification remain separate delivery work.

**Owner:** `inframeld-indexing`

The developer explicitly approved the presented batch-4 contracts and delegated selection of all remaining decisions to the assistant on 2026-10-29, requesting repository/GitHub recording and plain-language justification. This resolution is accepted under that authority. It selects logical policy, not implemented code or passing qualification.

## Contents

- [Approved resolution](#approved-resolution)
- [Why and example](#why-and-example)
- [Implementation and required evidence](#implementation-and-required-evidence)
- [Architectural impact and dependencies](#architectural-impact-and-dependencies)
- [Historical context and alternatives](#historical-context-and-alternatives)
- [Sources and finalization](#sources-and-finalization)

<a id="non-binding-recommendation"></a>

## Approved resolution

Select one initial production qualification target: patched Ubuntu Server 24.04 LTS x86-64, unified cgroup v2, enforcing AppArmor and qualified pinned Docker/Compose, bubblewrap, seccomp/LSM policies, parser image, Docling and assets. Exact supported patch versions, packages, policy hashes and image/asset digests become the release manifest's reproducible evidence. Other hosts, architectures and desktop-container VMs are unqualified until they pass this same protection profile; an unsupported local parser reports unavailable, not a privileged fallback. A compatible CLI may still target a qualified remote installation.

Preserve the 25 MiB upload limit. The initial parser profile permits one concurrent attempt; at most 500 PDF pages,10 MiB canonical extracted text,32 MiB complete structured output,2000 chunks per document,1024 tokens per chunk,1000000total emitted tokens including repeated text,300 seconds wall time,2 CPUs/8 GiB memory/128 PIDs for the parser service,1 GiB scratch per attempt including input/output and 2 GiB total service temporary storage. The whole-host current/physical-data ceilings may reject a smaller document even when these per-attempt bounds fit. Never silently truncate, change chunking or publish partial output to make a limit fit.

Initial qualification covers text-native PDF, Markdown/plain text and bounded structured tables. OCR is unavailable until its selected pinned offline assets pass the same profile. No parser/model/tokenizer download occurs during requests. Profile/source identity fixes exact conversion/chunking meaning and the accepted canonical source-coordinate mapping.

Keep application state, network, secrets, inherited descriptors and broad shared mounts out of the restricted child. Use the accepted per-attempt bubblewrap user/mount/PID/IPC/network namespaces, read-only required assets, parser-specific syscall allowlist and enforcing host policy. Do not disable AppArmor/seccomp globally, grant privileged containers or expose the Docker socket to bypass namespace restrictions. The application profile must permit only the namespace setup actually needed by the qualified build.

Supervise the entire process tree and attempt scratch lifetime. On timeout, cancellation, crash or limit breach stop all descendants, allow at most 10 seconds for termination/reaping, verify no lingering use before admitting the next attempt and remove owned private scratch. If teardown cannot be established, quarantine the parser runtime and keep parsing unavailable until controlled recovery. A main-process exit does not prove descendants stopped.

Startup self-tests must exercise actual network/secret/mount denial, syscall/LSM enforcement, resource limits, output validation and complete teardown using controlled fixtures. A missing capability or failed self-test disables parsing while leaving separately safe product functions available. Qualification checks normal fixtures and hostile expansion/fork/output/scratch cases on the exact supported host/artifacts. These limits and host selection are approved targets, not proof that the image exists or is secure.

## Why and example

A small uploaded file can expand into huge content or spawn children. File size alone cannot protect the host or isolate the next document.

Alice's PDF exceeds the expanded-text limit. Its attempt fails and all descendants/scratch are removed before Bob's file starts. If cleanup cannot be verified, the parser is quarantined rather than reused.

Some legitimate large or scanned documents are rejected initially, and unqualified hosts cannot parse. This keeps the supported security boundary narrow and testable.

<a id="decision-trigger-and-stopping-boundary"></a>

## Apply the accepted contract

Use this contract when the original trigger matches. Do not ask for the same policy decision again. Concrete native methods, DTO names and physical schemas are implementation choices consistent with this contract and the repository conventions. Missing measurements, fixtures or assembled evidence block the affected qualification/support claim, not authorized implementation or isolated tests. A failed test is not permission to weaken an accepted safety boundary.

<a id="open-questions-and-required-evidence"></a>

## Implementation and required evidence

Exact manifest, ordinary formats/tables, expansion and output bounds, unsupported host, network/secret/descriptor denial, namespace policies, fork descendants, timeout/cancellation and teardown-before-reuse.

These are required checks, not tests run or successful production evidence. No application edits, paid calls or production changes follow merely from recording this decision.

## Architectural impact and dependencies

Indexing preparation/supervisor, Knowledge admission failure reporting, deployment readiness and worker resource budgets. Update restricted-parser runtime/teardown sequences when the supported mechanism is selected.

Load neighboring decisions only under these conditions:

- [PD-ARCHITECTURE-01 (accepted): Select a measured supported workload and resource envelope](../../inframeld-architecture/references/decision-supported-operating-envelope.md). For whole-host and concurrent workload bounds.

## Historical context and alternatives

The following preserves the earlier problem, context and options. Statements that a choice was open describe that earlier analysis. The approved resolution above now settles it.

<a id="problem-and-example"></a>

### Original problem and example

Historical analysis before this resolution.

Alice uploads a supported PDF that expands into enormous text or leaves child processes running. Bob uploads another document immediately afterward. The parser must fail within its limits, remove the whole attempt and keep Bob’s attempt isolated.

The no-network/no-secret sandbox and accepted upload limit are selected. Numeric page/text/chunk/token/time/scratch limits and the exact supported image, policies and host combination remain unqualified. File-size bounds alone cannot prevent host exhaustion.

### Original accepted context and evidence

Historical context before this resolution. Unchanged invariants still apply.

Preserve the 25 MiB upload bound, offline pinned processing assets, no privileged fallback, closed inherited descriptors, validated output and complete process-tree teardown. Domain and application state stay outside the restricted child.

The supported host, kernel controls, bubblewrap/seccomp/LSM policy and image must be tested together. A configuration file or container flag alone does not prove isolation. Reranker behavior and remote gateway calls retain their separate boundaries.

### Considered alternatives and trade-offs

Historical options, resolved by the approved contract above.

1. **Start with one narrow tested host/profile.** Choose conservative numerical ceilings and qualify the complete supported combination. This reduces support variation, but rejects larger legitimate inputs until measured expansion.
2. **Offer a small set of explicitly qualified profiles.** Each profile has documented limits and passes the same hostile tests. This helps varied workloads, but multiplies release evidence and operator configuration.

## Sources and finalization

- [Sandbox and qualification](../../inframeld-knowledge/references/uploads-and-source-sync.md).
- [Restricted execution decision](../../../../docs/adr/ADR-0034-process-untrusted-documents-inside-a-restricted-execution-boundary.md).
- [Processing profile records](records.md#indexing).

Follow [decision finalization](../../../../docs/development/guides/architecture-decisions.md#just-in-time-architecture-decisions) for a later change to this accepted policy. Qualification evidence must identify its artifacts, environment, failures and limits. This record does not fabricate implementation or a passing test.
