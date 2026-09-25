# ADR-0049: Require group managers to be ordinary members

**Status:** Accepted

**Date:** 2026-09-25

## Context and Problem Statement

A group determines who may read documents that allow that group. The earlier design allowed a human to manage membership without being an ordinary member. Alice could therefore grant Bob document access that she did not personally hold.

That is a possible separation of administrative and reading duties, but it does not match Inframeld's intended sharing model. A new maintainer should be able to understand a group manager as someone who holds the group's document access and may share it with eligible project members.

## Considered Options

- **Allow managers without ordinary membership.** Keeps access administration separate from personal reading. It requires explaining why someone denied document access may still authorize disclosure to others.
- **Require explicit membership for every manager.** Makes the group's readers and sharing authority easier to understand. It gives every appointed manager access to the group's current and future permitted documents.

## Decision Outcome

Require every human group manager to have an ordinary membership in the same project and group. Keep the records separate. Membership supplies document access, while management adds authority to change membership and appoint peer managers. Ordinary membership alone cannot authorize sharing.

Group creation and manager appointment explicitly record both assignments. Demotion removes management while retaining membership. Removing membership also removes management in the same transaction. Ordinary last-manager handover still applies. Emergency suspension blocks both reading and administration immediately, and scoped recovery records both assignments for an eligible replacement.

**Example.** Alice is a member and manager of SupportKnowledge. She adds Bob as an ordinary member. Both may use documents that allow this group, but only Alice may change its membership. Query on Production and other operational permissions remain separate checks. Neither person receives access to HRPrivate from these assignments.

Use the existing Access records and write coordination. No new service, authorization engine, or permission language is required. The guides below own exact lifecycle and proposed database details.

## Consequences

- Managers have the document access they may share. Appointing a manager must clearly disclose that it grants both membership and management.
- Read checks still use ordinary membership. A manager flag never bypasses a missing membership or another required permission.
- Management without ordinary membership is no longer supported. The choice removes a surprising state, but broadens direct reading access for anyone appointed as a manager. It does not prevent misuse by a trusted manager.
- Creation, appointment, removal, and recovery must preserve the membership requirement together with scope revisions and audit history. Demotion and membership removal remain visibly different operations.
- Suspension may strand management without restoring a compromised account or giving an operator ordinary unrestricted reading. Other group memberships may independently preserve document access after removal from one group.
- This decision concerns group membership and management. It does not give ordinary readers sharing authority or automatically grant Query, Build, Add documents, Update documents, or Delete documents.

## Links

- [Current group-management rules](../development/access-control.md#group-managers).
- [Record constraint and proposed foreign key](../development/data-model.md#group-manager-membership-constraint).
- [Private starter provisioning](../development/onboarding.md#model).
- [Emergency suspension and recovery](../development/access-control.md#recovery).
- [ADR-0014: bounded delegation](ADR-0014-bound-permission-delegation-by-action-and-exact-target.md), partially superseded only for manager eligibility.
- [ADR-0015: separate document access](ADR-0015-keep-document-group-access-separate-from-operational-permissions.md), retained.
- [ADR-0019: scoped recovery](ADR-0019-permit-emergency-suspension-with-scoped-operator-recovery.md), retained.
- [ADR-0022: transactional Access coordination](ADR-0022-coordinate-access-writes-by-project-with-scope-revisions.md), reused.

Implementation and behavioral qualification are pending. This documentation change does not implement a migration or claim that the constraint and workflows have passed tests.
