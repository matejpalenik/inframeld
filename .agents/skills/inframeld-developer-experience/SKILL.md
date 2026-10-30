---
name: inframeld-developer-experience
description: Review Inframeld CLI and generated SDK journeys for discoverability, safe automation, clear output, recovery and useful examples. Use for requested developer-experience reviews of public interfaces, not ordinary backend-only work or generic tool recommendations.
---

# Review the developer's complete task

Alice should be able to discover a command, choose the correct target, understand the result and recover without guessing whether a write happened. Review that journey across help, output, errors, generated client behavior and documentation. A polished success message cannot compensate for an unsafe retry or an ambiguous account.

This skill supplies a focused review lens. [Review](../inframeld-review/SKILL.md) owns severity, scores and reporting. Load it for a requested assessment, along with Coding Standards, the affected language/package rules and the owning behavioral workflow. Do not impose a second scorecard, require a perfect numerical rating or add speculative architecture to make an interface look sophisticated.

## Establish the supported journey

Identify the changed interface, expected developer, task, actual base/head revisions and issue acceptance. Inspect the public entry point and one normal and relevant failure path. Distinguish accepted future CLI design from shipped commands. An unimplemented command outside the issue's scope is not automatically a defect. Do not promise published SDK packages or unsupported credential modes.

For CLI changes, read [CLI review](references/cli-review.md). For generated clients, read [SDK review](references/sdk-review.md). Use [worked reviews](references/worked-reviews.md) to calibrate concrete findings and valid exceptions. Read only the relevant lens for a narrow task.

## Review through observable behavior

1. Follow first use with the documented setup, discovery and smallest useful result. Note where the developer must guess a target, value, installation step or generated type.
2. Inspect help and output as public interfaces. Distinguish human presentation from automation contracts. Check stdout, stderr, JSON shape, exit status, non-interactive behavior and cancellation where applicable.
3. Trace failure and recovery. Preserve current authority, credential privacy, partial effects, retained original context and uncertainty. A transport timeout never proves that a write did not occur.
4. Check SDK ergonomics using actual generated APIs and their lifecycle. Confirm that examples use correct types, equivalent behavior across languages and no competing handwritten application client.
5. Gather proportionate read-only evidence. Use controlled local fixtures when available and report unexecuted paths. Do not run paid or production calls to improve a review's confidence.
6. Return actionable findings through Review's standard report. Name the triggering task, inspected evidence, developer consequence, priority and smallest useful remedy. Separate material defects from optional preferences.

## Coordinate delivery

For an assigned delivery review, follow the [assignment protocol](../inframeld-backlog-delivery/references/assignment-protocol.md) for checkout binding, trusted instructions and check/resource ownership. Return the issue, exact base/head, scope, findings, checks and readiness to the coordinator and worker through the authorized native internal messaging channel. Review remains read-only unless an explicit separate fix assignment provides file ownership. Do not stage, commit, rebase, push, post GitHub comments or change issue scope.

P0 and P1 findings require a stop or fix under Review's rules. Address P2 findings unless the human explicitly accepts the bounded risk and follow-up. Keep P3 suggestions optional. In a backlog run, three unsuccessful remediation cycles escalate to the coordinator rather than creating an endless polishing loop. High scores cannot override a failed gate, and no material findings means stop inventing work.

Accepted Inframeld contracts are authoritative. [Command Line Interface Guidelines](https://clig.dev/) informs general usability. Stripe's first-use path and IBM Cloud's targeting model are comparison examples, not requirements to copy their commands, flags or authentication.
