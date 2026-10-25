---
name: inframeld-releases
description: Explains and reviews Inframeld Deployment publication, automatic/manual modes, canaries, promotion and rollback. Use for traffic selection and stale-publication races, not pipeline preparation or CI releases.
---

# Inframeld Releases

Help a developer understand which ready version answers the next request and who may change that selection. Releases owns Deployment serving pointers, cohorts, publication modes and transitions. Pipelines owns builds and answer execution. Indexing owns search readiness. Evaluation supplies evidence but never release authority.

## Working model

Production currently serves A and retains Z as its designated previous version. Alice builds B. Finishing B makes it ready, not live. In Manual mode she may attach B as a candidate, try a canary, promote it or reject it under current release authority.

Rejecting B leaves A current and Z previous. Promoting B makes A previous. A later rollback consumes that one-step target under its own checks. Restoring working Pipeline configuration is a different operation and does not move traffic.

Automatic mode coordinates ordinary preparation with separate conditional publication. If Alice changes Automatic to Manual while a build runs, the build may still finish usefully, but its old publication authority is invalid. Switching back admits fresh work and cannot revive it.

## Essential rules

- Deployments select complete ready versions, never mutable working copies. A ready label does not prove current health or permission to serve erased inputs.
- The default onboarding path starts Automatic updates. Explicit new Deployments default Manual releases with an automatic option. Preserve deliberate mode choices on later setup.
- Manage releases belongs to the exact Deployment and covers publication, candidate/canary control, rollback, mode switches and automatic input selection. Build, Delete and non-serving configuration Edit remain separate.
- Automatic work needs underlying input/mutation rights, Build and target release authority. Before first default publication, creation has its separately authorized project scope.
- Recheck captured and current authority, selected inputs, control revisions, newest authorized request and serving/attempt state before publication. Superseded work cannot become a fallback after a newer failure.
- Canaries and rollback require Manual mode. Any attached candidate, including 0%, blocks switching to Automatic.
- Stable principal and rollout identities determine canary affinity. Key rotation does not reshuffle callers. A percentage describes identities, not an exact request count.
- Manual mode and Pipeline rollback do not freeze shared model connections or restore old credentials.

## Explain or review

1. Start with current A, previous Z and candidate B. Name mode, authority and selected inputs.
2. Walk one transition at a time and show the resulting pointers. Keep build readiness separate from traffic movement.
3. Include stale commands, erasure/unusable targets or an old automatic build finishing after off/on.
4. Explain why failures preserve healthy current traffic and why no alternate target is silently chosen.
5. Cite current rules and distinguish accepted design from inspected implementation. Loading this skill grants no release, deployment or external-action authority.

Before domain-specific backend component design, code generation or structural review, read [this module's architecture](references/architecture.md) and the relevant workflow, together with Coding Standards. Its accepted design, inspected implementation and proposals have different status. Resolve a pending architectural choice before suggesting code that depends on it. Behaviour-only questions can go directly to their workflow.

## Read as needed

- For module responsibilities, collaborators, data ownership or component design/review, read [Architecture](references/architecture.md).

- For creation, first publication, current authority, modes and delayed automatic work, read [Publication and automatic updates](references/publication-and-automatic-updates.md).
- For stable cohorts, candidates, rejection, promotion or rollback, read [Canaries and rollback](references/canaries-and-rollback.md).

The [Pipelines and Releases guide](../../../docs/development/pipelines-and-releases.md) owns transitions and races. [Release records](../../../docs/development/data-model.md#releases), [Access](../../../docs/development/access-control.md) and [onboarding](../../../docs/development/onboarding.md) own related contracts. Read those details only when they matter to the request.
