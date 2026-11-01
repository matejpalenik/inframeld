# Authorize Project metadata changes explicitly

Alice’s existing Project has the label Legal Research but no command selector. She must allocate `legal-research` through its permanent ID, then be able to rename it without moving grants or admitted work. Creator history and Create projects do not supply this authority.

**Status:** the developer approved this concrete design and its guide/ADR reconciliation on 2026-10-30. [ADR-0124](../../../../docs/adr/ADR-0124-authorize-project-metadata-changes-explicitly.md) records the decision. At this recording checkpoint the #120 application behavior, migrations, HTTP operations and qualification remain unfinished. This reference does not claim runtime delivery.

## Selected contract and owners

[Architecture naming](../../inframeld-architecture/references/resource-names-and-identity.md#resource-naming) owns exact selector/display-label validation, scope, permanent identity, non-reuse and typed resolution. Names contain 1–63 lowercase ASCII letters/digits/hyphens with the accepted start/end grammar. Submitted replacement labels contain 1–128 Unicode code points under its whitespace/control rules. No extra words are reserved. Suggestions remain previews without normalization at lookup or silent allocation.

Access owns **`edit-project-metadata`**, a human-only action on one exact Project. It permits first selector allocation and Name/Display-name changes. Current eligible human state, Project membership and this current grant are required. It supplies no creation, membership, document, configuration, release or deletion authority. Applications cannot receive it, even through import. Do not borrow an unrelated action or infer it from a creator/audit field.

The [initial-assignment contract](actions-and-initial-grants.md#initial-assignments) adds this action as the eighteenth explicit can-use-and-grant assignment for new ordinary Projects and private starters. It preserves the other seventeen actions, other resource seeds and four Organization bootstrap grants. No existing Project receives a backfill. #223 owns automatic assignment during ordinary creation and #27 during private-starter provisioning. Their future transactions must save all eighteen grants, membership, Project, audit and original outcome together. #224’s later handover must protect the resulting exact responsibility. #120 must not add an unused allocator or creation endpoint to imply those provisioners exist.

## One metadata change

1. Resolve an exact Name under its kind and installation/Organization scope, or use the original permanent ID. Validate the adapter’s returned kind, scope and exact binding before current Access visibility permits disclosure. Display labels never resolve identity.
2. Authenticate and check current exact metadata authority. Review the ID, proposed values and expected metadata revision. This revision is separate from the Access revision used by permission administration.
3. Under coordinated database work, recheck current authority and expected state, then save the name reservation, metadata, required audit and original operation outcome together. A concurrent collision, stale review, invalid submitted replacement or revoked grant changes neither field.
4. After response loss, recover through the original ID/operation under current authority. Never follow a retired name to a substitute. Authorized current-name guidance retains the original ID. Revocation blocks protected replay and does not invalidate identity itself.

Retain an unrestricted legacy `projects.name` value exactly as its Display name on migration, reads, replay and selector-only updates. It may be blank, long or contain controls. Validate only submitted replacements, without normalization or truncation. Return the stored value in machine output and escape unsafe controls for human presentation. An unallocated legacy selector remains nullable until explicitly assigned by ID. Physical columns/tables remain ordinary implementation choices governed by migrations.

## Establish the first grant on an existing Project

[Host maintenance](host-maintenance.md#project-metadata-authority-repair) owns the exact repair procedure. #120 must deliver only `repair-stranded-authority` for `action-grantor`, target `project`, literal `edit-project-metadata`. This is a bounded application of accepted host repair, not a new security bypass or universal repair framework. General grant administration remains #28.

The operator’s verified host/container execution authorizes repair. Protected stdin carries the independently controlled installation ID, original operation ID, attribution/reason, expected Project Access revision and verified recipient identity proof. The transient Hydra token identifies the recipient only. Private Hydra/current Kratos checks precede SQL coordination. Require an existing active admitted human and current Project membership.

Under identity/recovery and Organization/Project coordination, recheck identity eligibility, membership, active Project state, reviewed revision and that no active eligible human can grant this exact action. Missing facts fail closed. Atomically save only its use-and-grant assignment, revision change, operator reason, required audit and original safe receipt. No creator-history inference or unrelated grant is sufficient.

All modes share the installation/operator-request-ID namespace. Fingerprint verified recipient identity, mode, target/action, original reviewed revision and request meaning, excluding replaceable token bytes. Every invocation verifies current proof and recipient eligibility. Matching completed receipts return the original result before fresh stranded/revision checks. Changed meaning/identity/mode conflicts. Replay after grant removal never regrants. Typed repair receipt data must preserve existing recovery-continuation semantics without fabricated recovery fields.

## Alternatives and consequences

Unrestricted selector/label inputs would avoid new submission limits but increase presentation and compatibility costs. Extra reserved-word lists would require another policy and reject useful names. Preview-only suggestions keep exact lookup predictable. Borrowing Create projects or membership administration would grant unrelated power and fail existing members without those actions. Creator inference or automatic backfill would weaken current exact grants. The new action and narrow host repair supply least authority, at the cost of explicit first-grant recovery and an additional creator assignment.

## Full #120 delivery and evidence

#120’s approved completion boundary is real Project HTTP/PostgreSQL resolution, explicit first allocation and rename, narrow host repair, lossless legacy handling, current authorization and original-ID recovery. The real Project service must consume the same typed resolver exercised with controlled Collection/ProcessingProfile bindings. Same-spelling kinds resolve independently. Missing, retired or ambiguous exact matches fail without a substitute. A wrong-kind or wrong-Project adapter result fails closed. Future owner adapters/CRUD remain unsupported until delivered, without a provisioning prerequisite cycle.

Qualification must cover duplicate labels, name retirement/non-reuse, concurrent collisions, stale reviews, grant removal, rollback after audit/commit failure, and long/blank/whitespace/control-bearing legacy labels through reads and selector-only changes. Repair evidence needs real private Ory verification, concurrent repairs, refreshed-proof replay, cross-mode request conflicts and replay after grant removal without regranting. New public operations need native OpenAPI, supported generation and qualification of all three SDKs, user guidance and DX review. Full CLI context management and resource provisioning remain outside this boundary. Recording this design alone cannot close #120 or establish any of those results.
