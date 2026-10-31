---
name: inframeld-testing
description: Guides Inframeld test-layer selection, dependency isolation and verification evidence. Use for unit, contract or integration strategy and test-environment diagnosis. SDK generator conformance belongs to SDK skills.
---

# Inframeld Testing

Help a developer choose the boundary that can demonstrate the requested behavior, run the relevant checks within scope and explain what their result establishes. This skill owns test strategy and evidence boundaries. The shared Coding Standards retains scaffold-first TDD and documentation. Python Standards and Rust Standards own language-specific test/code conventions and typing. Domain skills retain business behavior.

## Working model

Alice changes a grant service. A unit test with controlled collaborators can show that denied authority prevents a save. A PostgreSQL test is needed to demonstrate actual rollback or concurrent locking. A real Hydra scenario checks a provider boundary that a mocked verifier cannot establish. Passing one of these layers does not qualify the complete CLI/login journey.

An SDK test can additionally show that the generated client sent the right request through the real HTTP router. That is distinct evidence from a real database commit or provider call.

## Essential constraints

- Choose tests for the behavior and failure boundary. A mock can establish interactions and decisions, not an unexecuted database or provider guarantee.
- Describe both the behavior checked and the resources used. Require cleanup after setup or assertion failure, and stop dependent runtime checks when resource ownership or cleanup is unresolved. The references below distinguish these cases from ordinary independent assertion failures.
- Keep service-dependent tests isolated from development databases, credentials and volumes. Use the existing private test procedures rather than an improvised stack or broad cleanup.
- Establish acceptance through repository-owned behavioral tests and maintained workspace commands. Temporary diagnostics answer a bounded question and remain partial evidence. Review expanding harness repairs before adding executors or duplicate supervision. [Isolation and evidence](references/isolation-and-evidence.md#maintained-commands-and-diagnostic-probes) owns these limits and routes delivery to its host boundary.
- Distinguish passed, failed, skipped and unavailable checks. Inspect enabled integration flags and the actual collected/executed scenarios before claiming a whole suite or product journey passed.
- Follow Coding Standards' behavioral TDD and meaningful-test rules when writing code. Do not add architecture, naming, import-boundary or composition enforcement tests.
- Loading this skill grants no authority to run migrations, provision databases or contact providers merely to answer a question. Authorized test execution uses the existing disposable test boundaries.

## Choose the reading route

| Task | Read |
| --- | --- |
| Choose a test boundary, classify resources or assess assertions and doubles | [Test strategy](references/test-strategy.md) |
| Investigate fixture ownership, integration setup, cleanup failures or evidence claims | [Isolation and evidence](references/isolation-and-evidence.md) |
| Run a focused check or integration stack | [Testing runbook](../../../docs/development/guides/testing.md) |
| Explain CI relevance, not-applicable results or manual full verification | [CI selection and proof boundaries](../../../docs/development/guides/testing.md#ci-selection) |
| Explain dependency caches, invalidation or cold/warm CI evidence | [CI cache policy](../../../docs/development/guides/testing.md#ci-dependency-caches) |
| Shared TDD and documentation | [Core testing contract](../inframeld-coding-standards/references/testing-and-documentation.md) |
| Python test conventions and doubles | [Python test/code examples](../inframeld-python-standards/references/testing-and-documentation.md), for authored Python tests |
| Rust test and process conventions | [Rust Standards](../inframeld-rust-standards/SKILL.md), for authored Rust tests |
| Qualify generated SDK behavior | [SDK strategy](../inframeld-sdks/SKILL.md), or the relevant language skill directly |

Ordinary code changes do not automatically need this whole strategy guide. For a narrow test implementation, keep the mandatory coding guidance and owning behavior in view without loading unrelated integration references. Model-quality evaluation, frozen benchmarks and faithfulness belong to [Evaluation](../inframeld-evaluation/SKILL.md). This skill does not invent a frontend runner or qualify an unimplemented Studio/CLI journey.
