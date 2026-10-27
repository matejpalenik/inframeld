---
name: inframeld-sdks
description: Explains Inframeld's shared SDK generation and qualification strategy. Use for cross-language SDK changes, endpoint coverage or shared generator policy.
---

# Inframeld SDKs

Help a developer deliver generated clients that preserve the backend's native HTTP contract. [ADR-0089](../../../docs/adr/ADR-0089-select-patched-typescript-and-python-sdk-generators.md) selects the TypeScript and Python generators alongside Rust's existing decision. [ADR-0090](../../../docs/adr/ADR-0090-qualify-sdks-with-shared-contract-scenarios.md) accepts shared qualification across all three languages.

## Working model

Alice adds an operation with an optional nullable description. The SDK must preserve whether she omitted that field or sent null. A shared scenario describes the expected request once. Each language's small driver constructs generated models and invokes the generated method. Backend observations establish what arrived, while shared assertions inspect the SDK's actual response or failure. A driver cannot repair a wrong request to make its SDK pass.

Backend behavior and native OpenAPI come first. Regeneration supplies models and operations, then qualification demonstrates the delivered behavior. OpenAPI identifies operations and shapes, but meaningful business expectations still require authored scenarios.

## Essential constraints

- Generate complete clients from native OpenAPI. Maintain verified, targeted generator source or shipped-resource patches instead of editing generated SDK output, weakening schemas or substituting handwritten HTTP methods.
- Keep generation explicit. Ordinary compilation consumes committed generated source without a generator or backend. Read versions, source hashes, patch order and options from the actual configuration and manifests.
- Keep typed bodies, available status/headers and inspectable failures together. A lost response does not establish that a write failed and cannot authorize automatic redispatch.
- Keep scenario expectations shared and SDK calls native. Judge each SDK against the contract and backend witnesses, not merely agreement with the other clients.
- Selection, implementation and qualification are different facts. The typed workflows, ordinary Node feature tests and operation-coverage gate are implemented under [ADR-0092](../../../docs/adr/ADR-0092-maintain-sdks-with-typed-workflows-and-native-conformance-tests.md). Filtered runs remain partial evidence. Linux checks are automatic for applicable PRs, with macOS for generator and platform-sensitive process/browser/lifecycle changes, plus manual runs. External branch rules must require the stable aggregate separately. Report actual execution evidence without inferring remote qualification.

## Choose the reading route

| Task | Read |
| --- | --- |
| Consume or investigate one language's client | [Rust](../inframeld-rust-sdk/SKILL.md), [TypeScript](../inframeld-typescript-sdk/SKILL.md) or [Python](../inframeld-python-sdk/SKILL.md), independently |
| Add endpoint coverage or compare SDK behavior | [Shared qualification](references/shared-qualification.md) |
| Change generation, add a patch, upgrade or retire one | [Generator maintenance](references/generator-maintenance.md), plus the affected language's maintenance route |
| Choose a product test layer or investigate fixture isolation | [Testing](../inframeld-testing/SKILL.md) |
| Change HTTP meaning or release compatibility | [Application Contracts](../inframeld-application-contracts/references/http-mcp-and-generated-clients.md) and its [compatibility decision](../inframeld-application-contracts/references/decision-cli-server-compatibility.md) |

These are sibling skills with explicit links, not automatic inheritance. Ordinary language questions do not require every SDK reference. Coding Standards remains mandatory for code work. Loading guidance authorizes no edits or external actions. Keep unpublished package protection and defer registry publication, release compatibility, CLI/login flows and an HTTP escape hatch to their separate work.
