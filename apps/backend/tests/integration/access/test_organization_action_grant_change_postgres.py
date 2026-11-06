"""Persist exact Organization grant effects with their original audit and receipt."""

import asyncio
import os
from dataclasses import replace
from uuid import UUID

import pytest
from sqlalchemy import func, select
from tests.support.authentication_evidence import MockAuthenticationEvidence
from tests.support.project_membership_postgres_scenarios import (
    MembershipProjectSeedDTO,
    seed_membership_project,
)

from inframeld_backend.access.application.commands.remove_organization_action_grant_command import (
    RemoveOrganizationActionGrantCommand,
)
from inframeld_backend.access.application.commands.set_organization_action_grant_command import (
    SetOrganizationActionGrantCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.organization_action_grant_change_result_dto import (
    OrganizationActionGrantChangeResultDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.access.infrastructure.rows.organization_action_grant_operation_result_row import (
    OrganizationActionGrantOperationResultRow,
)
from inframeld_backend.access.infrastructure.rows.organization_action_grant_row import (
    OrganizationActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.rows.project_membership_row import ProjectMembershipRow
from inframeld_backend.bootstrap.organization_grant_composition import (
    open_organization_grant_change,
)
from inframeld_backend.bootstrap.original_operation_lookup_composition import (
    open_original_operation_lookup,
)
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.enums.operation_lookup_authority_family import (
    OperationLookupAuthorityFamily,
)
from inframeld_backend.shared.application.enums.operation_reservation_state import (
    OperationReservationState,
)
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ConflictError,
)
from inframeld_backend.shared.application.queries.lookup_original_operation_query import (
    LookupOriginalOperationQuery,
)
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.operation_lookup_authority import (
    OperationLookupAuthority,
)
from inframeld_backend.shared.application.value_objects.request_fingerprint_key import (
    RequestFingerprintKey,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)
from inframeld_backend.shared.infrastructure.rows.installation_identity_row import (
    InstallationIdentityRow,
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
        reason="Requires isolated PostgreSQL integration services",
    ),
]


async def test_organization_assignment_commits_grant_revision_audit_and_original_result(
    database: Database,
) -> None:
    seed = await seed_membership_project(database)
    organization = seed.actor.organization_id
    async with database.session() as session:
        revision = await session.scalar(
            select(OrganizationRow.access_revision).where(OrganizationRow.id == organization.value)
        )
        assert revision is not None

    context = IdempotencyContextDTO(
        method=HttpMethod.PUT,
        requested_route=f"/v1/organizations/{organization.value}/grants/{seed.bob_id.value}/create-projects",
        key=IdempotencyKey("organization-create-projects-bob"),
    )
    async with open_organization_grant_change(
        database, RequestFingerprintService(RequestFingerprintKey(b"K" * 32))
    ) as service:
        result = await service.set_grant(
            access=seed.actor.access,
            command=SetOrganizationActionGrantCommand(
                organization_id=organization,
                recipient_principal_id=seed.bob_id,
                action_id=ActionId("create-projects"),
                can_grant=False,
                expected_access_revision=revision,
            ),
            context=context,
        )

    assert (result.status_code, result.changed, result.access_revision, result.can_grant) == (
        201,
        True,
        revision + 1,
        False,
    )
    operation = result.operation.operation_id.value
    async with database.session() as session:
        grant = await session.get(
            OrganizationActionGrantRow, (organization.value, seed.bob_id.value, "create-projects")
        )
        assert grant is not None and not grant.can_grant
        assert grant.assigned_by_principal_id == seed.actor.access.actor_principal_id.value
        assert (
            await session.scalar(
                select(OrganizationRow.access_revision).where(
                    OrganizationRow.id == organization.value
                )
            )
            == revision + 1
        )
        receipt = await session.get(OrganizationActionGrantOperationResultRow, operation)
        assert receipt is not None and receipt.status_code == 201 and receipt.changed
        assert (receipt.before_revision, receipt.access_revision, receipt.can_grant) == (
            revision,
            revision + 1,
            False,
        )
        reservation = await session.get(IdempotencyReservationRow, operation)
        assert reservation is not None and reservation.state is OperationReservationState.REPLAYABLE
        assert reservation.lookup_authority_family == "organization_grant_read"
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AccessAuditEventRow)
                .where(AccessAuditEventRow.correlation_id == operation)
            )
            == 1
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ProjectMembershipRow)
                .where(ProjectMembershipRow.principal_id == seed.bob_id.value)
            )
            == 0
        )


async def _revision(database: Database, seed: MembershipProjectSeedDTO) -> int:
    async with database.session() as session:
        revision = await session.scalar(
            select(OrganizationRow.access_revision).where(
                OrganizationRow.id == seed.actor.organization_id.value
            )
        )
        assert revision is not None
        return revision


def _context(
    seed: MembershipProjectSeedDTO,
    recipient: PrincipalId,
    action: str,
    key: str,
    method: HttpMethod = HttpMethod.PUT,
) -> IdempotencyContextDTO:
    return IdempotencyContextDTO(
        method=method,
        requested_route=f"/v1/organizations/{seed.actor.organization_id.value}/grants/{recipient.value}/{action}",
        key=IdempotencyKey(key),
    )


async def _set(
    database: Database,
    seed: MembershipProjectSeedDTO,
    *,
    recipient: PrincipalId,
    action: str,
    level: bool,
    revision: int,
    key: str,
    access: AccessContextDTO | None = None,
) -> OrganizationActionGrantChangeResultDTO:
    async with open_organization_grant_change(
        database, RequestFingerprintService(RequestFingerprintKey(b"K" * 32))
    ) as service:
        return await service.set_grant(
            access=access or seed.actor.access,
            command=SetOrganizationActionGrantCommand(
                organization_id=seed.actor.organization_id,
                recipient_principal_id=recipient,
                action_id=ActionId(action),
                can_grant=level,
                expected_access_revision=revision,
            ),
            context=_context(seed, recipient, action, key),
        )


async def _remove(
    database: Database,
    seed: MembershipProjectSeedDTO,
    *,
    recipient: PrincipalId,
    action: str,
    revision: int,
    key: str,
    access: AccessContextDTO | None = None,
) -> OrganizationActionGrantChangeResultDTO:
    async with open_organization_grant_change(
        database, RequestFingerprintService(RequestFingerprintKey(b"K" * 32))
    ) as service:
        return await service.remove_grant(
            access=access or seed.actor.access,
            command=RemoveOrganizationActionGrantCommand(
                organization_id=seed.actor.organization_id,
                recipient_principal_id=recipient,
                action_id=ActionId(action),
                expected_access_revision=revision,
            ),
            context=_context(seed, recipient, action, key, HttpMethod.DELETE),
        )


def _bob(seed: MembershipProjectSeedDTO) -> AccessContextDTO:
    return AccessContextDTO(
        actor_principal_id=seed.bob_id,
        authentication_evidence=MockAuthenticationEvidence.browser(
            VerifiedHumanIdentityDTO(
                authority=seed.actor.binding.identity.authority,
                subject=IdentitySubject(str(UUID(int=200))),
            ),
        ),
    )


@pytest.mark.parametrize(
    "action", ["admit-users", "suspend-users", "restore-users", "create-projects"]
)
@pytest.mark.parametrize("level", [False, True])
async def test_all_organization_actions_keep_noop_and_old_removal_receipts_immutable(
    database: Database, action: str, level: bool
) -> None:
    seed = await seed_membership_project(database)
    revision = await _revision(database, seed)
    original = await _set(
        database,
        seed,
        recipient=seed.bob_id,
        action=action,
        level=level,
        revision=revision,
        key="org-first",
    )
    assert (
        original.status_code == 201
        and original.changed
        and original.access_revision == revision + 1
    )
    noop = await _set(
        database,
        seed,
        recipient=seed.bob_id,
        action=action,
        level=level,
        revision=revision + 1,
        key="org-noop",
    )
    assert not noop.changed and noop.access_revision == revision + 1
    changed = await _set(
        database,
        seed,
        recipient=seed.bob_id,
        action=action,
        level=not level,
        revision=revision + 1,
        key="org-change",
    )
    assert changed.changed and changed.access_revision == revision + 2
    removed = await _remove(
        database,
        seed,
        recipient=seed.bob_id,
        action=action,
        revision=revision + 2,
        key="org-remove",
    )
    await _set(
        database,
        seed,
        recipient=seed.bob_id,
        action=action,
        level=level,
        revision=revision + 3,
        key="org-regrant",
    )
    replay = await _remove(
        database,
        seed,
        recipient=seed.bob_id,
        action=action,
        revision=revision + 2,
        key="org-remove",
    )
    _assert_original_replay(replay, removed)
    assert await _revision(database, seed) == revision + 4
    async with database.session() as session:
        assignment = await session.get(
            OrganizationActionGrantRow,
            (seed.actor.organization_id.value, seed.bob_id.value, action),
        )
        assert assignment is not None and assignment.can_grant is level
        assert (
            await session.scalar(
                select(func.count()).select_from(OrganizationActionGrantOperationResultRow)
            )
            == 5
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AccessAuditEventRow)
                .where(AccessAuditEventRow.event_type.like("organization_action_grant_%"))
            )
            == 4
        )


async def test_original_organization_lookup_and_write_replay_both_require_current_delegation(
    database: Database,
) -> None:
    seed = await seed_membership_project(database)
    revision = await _revision(database, seed)
    original = await _set(
        database,
        seed,
        recipient=seed.bob_id,
        action="create-projects",
        level=True,
        revision=revision,
        key="org-lookup",
    )
    async with database.session() as session:
        installed = await session.scalar(select(InstallationIdentityRow.installation_id))
        assert installed is not None
    query = LookupOriginalOperationQuery(
        installation_id=InstallationId(installed),
        organization_id=seed.actor.organization_id,
        project_id=None,
        method=HttpMethod.PUT,
        requested_route=_context(
            seed, seed.bob_id, "create-projects", "org-lookup"
        ).requested_route,
        key=IdempotencyKey("org-lookup"),
        expected_authority=OperationLookupAuthority(
            family=OperationLookupAuthorityFamily.ORGANIZATION_GRANT_READ,
            action_id=ActionId("create-projects"),
        ),
    )
    async with open_original_operation_lookup(database) as lookup:
        found = await lookup.lookup(access=seed.actor.access, query=query)
    assert (
        isinstance(found, CompletedSynchronousOperationDTO)
        and found.operation_id == original.operation.operation_id
    )
    await _remove(
        database,
        seed,
        recipient=seed.actor.access.actor_principal_id,
        action="create-projects",
        revision=revision + 1,
        key="org-bob-removes-alice",
        access=_bob(seed),
    )
    async with open_original_operation_lookup(database) as lookup:
        with pytest.raises(AccessDeniedError):
            await lookup.lookup(access=seed.actor.access, query=query)
    with pytest.raises(AccessDeniedError):
        await _set(
            database,
            seed,
            recipient=seed.bob_id,
            action="create-projects",
            level=True,
            revision=revision,
            key="org-lookup",
        )
    with pytest.raises(ConflictError):
        await _remove(
            database,
            seed,
            recipient=seed.bob_id,
            action="create-projects",
            revision=revision + 2,
            key="org-last",
            access=_bob(seed),
        )


async def test_competing_organization_delegators_reread_after_the_exclusive_turn(
    database: Database,
) -> None:
    seed = await seed_membership_project(database)
    revision = await _revision(database, seed)
    await _set(
        database,
        seed,
        recipient=seed.bob_id,
        action="create-projects",
        level=True,
        revision=revision,
        key="org-race-delegate",
    )
    outcomes = await asyncio.gather(
        _remove(
            database,
            seed,
            recipient=seed.bob_id,
            action="create-projects",
            revision=revision + 1,
            key="org-race-alice",
        ),
        _remove(
            database,
            seed,
            recipient=seed.actor.access.actor_principal_id,
            action="create-projects",
            revision=revision + 1,
            key="org-race-bob",
            access=_bob(seed),
        ),
        return_exceptions=True,
    )
    assert (
        sum(isinstance(result, OrganizationActionGrantChangeResultDTO) for result in outcomes) == 1
    )
    assert sum(isinstance(result, AccessDeniedError) for result in outcomes) == 1
    assert await _revision(database, seed) == revision + 2


def _assert_original_replay(
    replay: OrganizationActionGrantChangeResultDTO, original: OrganizationActionGrantChangeResultDTO
) -> None:
    """Distinguish admission while retaining every original business and correlation field."""
    assert original.operation.created is True and replay.operation.created is False
    assert replay.operation.operation_id == original.operation.operation_id
    assert replay.operation.expires_at == original.operation.expires_at
    assert replay.operation.replay_kind is original.operation.replay_kind
    assert replace(replay, operation=original.operation) == original
