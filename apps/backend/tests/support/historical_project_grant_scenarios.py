"""Seed exact pre-cutover request history through the existing typed reservation row."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.enums.operation_lookup_authority_family import (
    OperationLookupAuthorityFamily,
)
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.enums.operation_reservation_state import (
    OperationReservationState,
)
from inframeld_backend.shared.application.queries.lookup_original_operation_query import (
    LookupOriginalOperationQuery,
)
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.application.value_objects.operation_lookup_authority import (
    OperationLookupAuthority,
)
from inframeld_backend.shared.application.value_objects.request_fingerprint_key import (
    RequestFingerprintKey,
)
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)
from tests.support.project_action_grant_postgres_scenarios import (
    seed_project_grant_recipients,
)
from tests.support.project_membership_postgres_scenarios import MembershipProjectSeedDTO

ACTION = ActionId("create-access-groups")
HISTORICAL_ROUTE = "/v1/projects/{project_id}/grants"


@dataclass(frozen=True, slots=True)
class RetainedProjectGrantPostDTO:
    seed: MembershipProjectSeedDTO
    query: LookupOriginalOperationQuery
    operation_id: OperationId
    expires_at: datetime
    fingerprint: bytes


async def seed_retained_project_grant_post(database: Database) -> RetainedProjectGrantPostDTO:
    seed = await seed_project_grant_recipients(database)
    query = LookupOriginalOperationQuery(
        installation_id=seed.actor.binding.installation_id,
        organization_id=seed.actor.organization_id,
        project_id=seed.project.project_id,
        method=HttpMethod.POST,
        requested_route=HISTORICAL_ROUTE,
        key=IdempotencyKey("historical-post-original"),
        expected_authority=OperationLookupAuthority(
            OperationLookupAuthorityFamily.PROJECT_GRANT_READ, ACTION
        ),
    )
    # Saved bytes remain historical identity. No live Command or POST dispatcher is constructed.
    canonical = (
        '{"actionId":"create-access-groups","expectedAccessRevision":2,"projectId":"'
        + str(seed.project.project_id.value)
        + '","recipientPrincipalId":"'
        + str(seed.bob_id.value)
        + '"}'
    ).encode()
    fingerprint = (
        RequestFingerprintService(RequestFingerprintKey(b"T" * 32))
        .fingerprint(purpose="access.project-grant.assign-use-only:v1", canonical_request=canonical)
        .value
    )
    operation = OperationId(str(uuid4()))
    expires = datetime.now(UTC) + timedelta(hours=12)
    reservation = IdempotencyReservationRow(
        operation_id=operation.value,
        principal_id=seed.actor.access.actor_principal_id.value,
        organization_id=seed.actor.organization_id.value,
        project_id=seed.project.project_id.value,
        method=HttpMethod.POST.value,
        requested_route=HISTORICAL_ROUTE,
        request_key=query.key.value,
        request_fingerprint=fingerprint,
        replay_kind=OperationReplayKind.SAFE_RESULT,
        expires_at=expires,
        lookup_authority_family=OperationLookupAuthorityFamily.PROJECT_GRANT_READ.value,
        lookup_action_id=ACTION.value,
    )
    reservation.state = OperationReservationState.REPLAYABLE
    async with database.session() as session, session.begin():
        session.add(reservation)
    return RetainedProjectGrantPostDTO(
        seed=seed, query=query, operation_id=operation, expires_at=expires, fingerprint=fingerprint
    )
