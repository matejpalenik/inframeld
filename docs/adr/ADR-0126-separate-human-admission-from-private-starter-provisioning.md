# ADR-0126: Separate human admission from private starter provisioning

**Status:** Accepted

**Date:** 2026-11-03

## Context and Problem Statement

Alice has current `admit-users` authority and wants to admit Bob, whose real Kratos identity is verified. Bob needs a stable local identity and admission before using product operations. Creating his private starter resources is a different operation with its own failure and retry behavior.

ADR-0046 coupled Bob's admission to creating his defaults. The developer approved separate admission and starters on 2026-11-03. This decision supersedes that coupling only. Private starters remain required ordinary resources, and the first-administrator host claim retains its existing authority and fixed grants.

## Considered Options

- Keep human admission and private starter provisioning in one transaction. Admission then depends on every starter resource being created successfully.
- Complete human admission separately, then run required, resumable private starter provisioning. Each operation retains its own atomic result and recovery boundary.

## Decision Outcome

Use separate operations. Access checks Alice's current human eligibility and `admit-users` authority and verifies Bob's exact trusted Kratos identity. Provider verification stays outside the local database transaction. Following the existing identity/recovery coordination, atomically save the legitimate principal and identity link, local admission, required audit and original result. Admission creates no starter resources and grants no implicit `create-projects` authority.

Recover the original admission result under current authorization and eligibility. Admission replay never provisions starters, repairs defaults or restores removed permissions. A failed later starter operation does not undo successful admission.

Private starter provisioning remains a required, separate human-only operation. Use the admitted principal and purpose to resume the same operation, preserving generated names, resource IDs and completed work. Commit its ordinary resources and explicit creator assignments together. Record deliberate removal so a later login, admission replay or setup restart cannot recreate deleted starters silently.

Admission, starter records and runtime health do not establish setup readiness. Setup continues through ordinary model, knowledge, build and publication checks before reporting a usable result. Preserve the existing eighteen Project creator assignments and fixed resource grants. Starter provisioning neither requires nor grants Organization `create-projects`.

## Consequences

Admission can complete while Bob has no Project or starter resources. Setup must distinguish that state from completed provisioning and from deliberate removal. Separate original results make retries explicit without a distributed coordinator or a second permission model.

This ADR records the accepted split. The private first-administrator consumer and ordinary human admission are implemented. The supported unadmitted-human proof integration remains unfinished under Access #27. Private starter provisioning remains unfinished under [Onboarding #8](https://github.com/matejpalenik/inframeld/issues/8). Complete first use remains unfinished, and human acceptance remains unperformed under #185. This current delivery allocation preserves the decision's admission/provisioning separation.

## Links

- [ADR-0046, partially superseded](ADR-0046-provision-creator-private-defaults-through-ordinary-resources.md).
- [Ordinary human admission](../../.agents/skills/inframeld-access-models/references/admission-and-invitations.md#ordinary-human-admission).
- [Identity and recovery coordination](../../.agents/skills/inframeld-access-models/references/identity-admission-coordination.md).
- [First use and private starters](../../.agents/skills/inframeld-architecture/references/first-use-and-private-defaults.md).
- [Fixed initial grants](../../.agents/skills/inframeld-access-models/references/actions-and-initial-grants.md#initial-assignments).
- [Remaining Access implementation #27](https://github.com/matejpalenik/inframeld/issues/27), [starter provisioning under Onboarding #8](https://github.com/matejpalenik/inframeld/issues/8) and [human qualification #185](https://github.com/matejpalenik/inframeld/issues/185).
