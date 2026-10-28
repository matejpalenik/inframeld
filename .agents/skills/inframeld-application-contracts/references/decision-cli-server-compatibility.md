# PD-CONTRACTS-03: Define supported CLI and server release combinations

**Status:** ACCEPTED

**Owner:** `inframeld-application-contracts`

**Issue kind:** Public compatibility contract.

## Approved resolution

On 2026-10-27 the developer selected explicitly qualified matching CLI/runtime releases initially and approved metadata-first reporting and the affected documentation. [ADR-0095](../../../../docs/adr/ADR-0095-support-matching-qualified-cli-and-runtime-releases.md) records the decision and alternatives.

Release metadata records CLI version, source revision, build target and the qualified runtime pair. Development builds claim no supported released runtime. Offline reporting cannot verify a remote server. Automatic mismatch enforcement awaits an approved backend version contract. Health, /v1, issuer discovery and authentication are not version evidence.

Generated SDK behavior governs additive fields. Unknown variants and decode failures remain explicit failures without redispatch. Breaking changes need a coordinated qualified release and upgrade guidance. No adjacent-release window is supported by implication.

## Preserved rationale and qualification boundary

Alice upgrades her CLI while Production remains older. Matching releases keep the initial test matrix small but require coordinated upgrades. An adjacent-release window would ease upgrades and require more qualification. It was considered and not selected.

Future enforcement should reject unsupported pairs before effects where possible. Lost acknowledgments still require original-operation recovery rather than a new request. API/worker/schema compatibility is a distinct boundary.

The policy is accepted. Release-pair qualification, remote verification and independently published releases are separate delivery work. Qualification gaps do not reopen the policy or prohibit tests.

## Sources

- [HTTP and generated clients](http-mcp-and-generated-clients.md)
- [Upgrade guidance](../../../../docs/development/operations/upgrades.md)
- [CLI implementation and packaging](../../../../apps/cli/README.md)
