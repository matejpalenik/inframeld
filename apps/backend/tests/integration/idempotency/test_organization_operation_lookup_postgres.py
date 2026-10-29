"""Qualify Organization lookup using real current grants and original null-Project scope.

Admission uses shared idempotency with an explicit trusted test authorization.
It does not claim a delivered Organization business command or HTTP admission.
"""

import os
from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select, update
from tests.support.access_scenarios import MockAccessScenarios
from tests.support.authentication_evidence import MockAuthenticationEvidence

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
    HumanOAuthCredentialBindingDTO,
)
from inframeld_backend.access.application.dtos.operation_lookup_authorization_dto import (
    OperationLookupAuthorizationDTO,
)
from inframeld_backend.access.application.enums.identity_recovery_event_kind import (
    IdentityRecoveryEventKind,
)
from inframeld_backend.access.application.errors.human_oauth_credential_rejected_error import (
    HumanOAuthCredentialRejectedError,
)
from inframeld_backend.access.application.services.operation_lookup_authorization_service import (
    OperationLookupAuthorizationService,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.readers.postgres_operation_lookup_facts_reader import (
    PostgresOperationLookupFactsReader,
)
from inframeld_backend.access.infrastructure.rows.human_credential_version_row import (
    HumanCredentialVersionRow,
)
from inframeld_backend.access.infrastructure.rows.human_identity_link_row import (
    HumanIdentityLinkRow,
)
from inframeld_backend.access.infrastructure.rows.identity_recovery_admission_row import (
    IdentityRecoveryAdmissionRow,
)
from inframeld_backend.access.infrastructure.rows.organization_action_grant_row import (
    OrganizationActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.project_membership_row import ProjectMembershipRow
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.dtos.new_operation_reservation_dto import (
    NewOperationReservationDTO,
)
from inframeld_backend.shared.application.dtos.operation_admission_context_dto import (
    OperationAdmissionContextDTO,
)
from inframeld_backend.shared.application.dtos.unresolved_operation_dto import (
    UnresolvedOperationDTO,
)
from inframeld_backend.shared.application.enums.operation_lookup_authority_family import (
    OperationLookupAuthorityFamily,
)
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ResourceNotFoundError,
)
from inframeld_backend.shared.application.queries.lookup_original_operation_query import (
    LookupOriginalOperationQuery,
)
from inframeld_backend.shared.application.services.idempotency_service import IdempotencyService
from inframeld_backend.shared.application.services.original_operation_lookup_service import (
    OriginalOperationLookupService,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.operation_lookup_authority import (
    OperationLookupAuthority,
)
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.infrastructure.readers.postgres_installation_identity_reader import (
    PostgresInstallationIdentityReader,
)
from inframeld_backend.shared.infrastructure.readers.postgres_operation_lookup_reader import (
    PostgresOperationLookupReader,
)
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)
from inframeld_backend.shared.infrastructure.writers.postgres_operation_reservation_writer import (
    PostgresOperationReservationWriter,
)

pytestmark = pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
    reason="Requires PostgreSQL integration services",
)
ACTION = ActionId("create-projects")


async def organization_admitted(
    database: Database,
) -> tuple[AccessContextDTO, LookupOriginalOperationQuery, str, ProjectId]:
    async with database.session() as session, session.begin():
        seed = await MockAccessScenarios.seed_project_authorization(
            session, is_project_member=False, has_action_grant=False
        )
        session.add(
            OrganizationActionGrantRow(
                organization_id=seed.organization_id.value,
                recipient_principal_id=seed.principal_id.value,
                recipient_kind=PrincipalKind.HUMAN,
                action=ACTION.value,
                can_grant=False,
            )
        )
    access = AccessContextDTO(seed.principal_id, MockAuthenticationEvidence.browser())
    installed = await PostgresInstallationIdentityReader(database).read()
    query = LookupOriginalOperationQuery(
        installed,
        seed.organization_id,
        None,
        "POST",
        "/v1/original-organization-operation",
        IdempotencyKey("organization-lost-ack"),
        OperationLookupAuthority(OperationLookupAuthorityFamily.ORGANIZATION_ACTION_USE, ACTION),
    )
    async with database.session() as session, session.begin():
        service = IdempotencyService(PostgresOperationReservationWriter(session))
        original = await service.find_or_reserve(
            context=OperationAdmissionContextDTO(query.method, query.requested_route, query.key),
            access=access,
            authorization=OperationLookupAuthorizationDTO(seed.organization_id, None),
            fingerprint=RequestFingerprint(b"O" * 32),
            expected_replay_kind=OperationReplayKind.SAFE_RESULT,
            lookup_authority=query.expected_authority,
        )
        assert isinstance(original, NewOperationReservationDTO)
        await service.record_completed_result(original, replay_kind=OperationReplayKind.SAFE_RESULT)
    return access, query, original.operation_id.value, seed.project_id


async def observe(
    database: Database, access: AccessContextDTO, query: LookupOriginalOperationQuery
) -> CompletedSynchronousOperationDTO | UnresolvedOperationDTO:
    async with database.session() as session:
        service = OriginalOperationLookupService(
            OperationLookupAuthorizationService(PostgresOperationLookupFactsReader(session)),
            PostgresOperationLookupReader(session),
        )
        result = await service.lookup(access=access, query=query)
        assert isinstance(result, CompletedSynchronousOperationDTO | UnresolvedOperationDTO)
        return result


@pytest.mark.asyncio
async def test_organization_lookup_preserves_original_scope_without_project_membership(
    database: Database,
) -> None:
    access, query, operation, _project = await organization_admitted(database)
    async with database.session() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ProjectMembershipRow)
                .where(ProjectMembershipRow.principal_id == access.actor_principal_id.value)
            )
            == 0
        )
    result = await observe(database, access, query)
    assert isinstance(result, CompletedSynchronousOperationDTO)
    assert result.operation_id.value == operation


@pytest.mark.asyncio
async def test_organization_reader_finds_exact_original_null_project_binding(
    database: Database,
) -> None:
    access, query, operation, _project = await organization_admitted(database)
    async with database.session() as session:
        result = await PostgresOperationLookupReader(session).read(
            principal_id=access.actor_principal_id, query=query
        )
        assert result is not None
        assert result.operation_id.value == operation


@pytest.mark.asyncio
@pytest.mark.parametrize("history", ["retained", "absent", "legacy", "mismatched"])
async def test_organization_revoked_exact_action_denies_independently_of_history(
    database: Database, history: str
) -> None:
    access, query, operation, _project = await organization_admitted(database)
    async with database.session() as session, session.begin():
        await session.execute(
            delete(OrganizationActionGrantRow).where(
                OrganizationActionGrantRow.recipient_principal_id
                == access.actor_principal_id.value,
                OrganizationActionGrantRow.action == ACTION.value,
            )
        )
        if history == "absent":
            query = replace(query, key=IdempotencyKey("absent"))
        elif history == "legacy":
            await session.execute(
                update(IdempotencyReservationRow)
                .where(IdempotencyReservationRow.operation_id == operation)
                .values(lookup_authority_family=None, lookup_action_id=None)
            )
        elif history == "mismatched":
            await session.execute(
                update(IdempotencyReservationRow)
                .where(IdempotencyReservationRow.operation_id == operation)
                .values(lookup_action_id="admit-users")
            )
    with pytest.raises(AccessDeniedError):
        await observe(database, access, query)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [PrincipalStatus.SUSPENDED, PrincipalStatus.RETIRED])
async def test_organization_lookup_rechecks_current_account_eligibility(
    database: Database, status: PrincipalStatus
) -> None:
    access, query, _operation, _project = await organization_admitted(database)
    async with database.session() as session, session.begin():
        await session.execute(
            update(PrincipalRow)
            .where(PrincipalRow.id == access.actor_principal_id.value)
            .values(status=status)
        )
    with pytest.raises(AccessDeniedError):
        await observe(database, access, query)


@pytest.mark.asyncio
async def test_project_permission_does_not_replace_organization_authority(
    database: Database,
) -> None:
    access, query, _operation, project = await organization_admitted(database)
    async with database.session() as session, session.begin():
        await session.execute(
            delete(OrganizationActionGrantRow).where(
                OrganizationActionGrantRow.recipient_principal_id == access.actor_principal_id.value
            )
        )
        session.add(
            ProjectMembershipRow(
                project_id=project.value,
                principal_id=access.actor_principal_id.value,
                organization_id=query.organization_id.value,
                principal_kind=PrincipalKind.HUMAN,
            )
        )
        await session.flush()
        session.add(
            ProjectActionGrantRow(
                project_id=project.value,
                recipient_principal_id=access.actor_principal_id.value,
                recipient_kind=PrincipalKind.HUMAN,
                action="create-access-groups",
                can_grant=True,
            )
        )
    with pytest.raises(AccessDeniedError):
        await observe(database, access, query)


@pytest.mark.asyncio
async def test_another_organization_is_not_substituted(database: Database) -> None:
    access, query, _operation, _project = await organization_admitted(database)
    with pytest.raises(ResourceNotFoundError):
        await observe(database, access, replace(query, organization_id=OrganizationId(uuid4())))


@pytest.mark.asyncio
async def test_organization_recovery_block_is_current_authority(database: Database) -> None:
    access, query, _operation, _project = await organization_admitted(database)
    identity = MockAuthenticationEvidence.browser().identity
    async with database.session() as session, session.begin():
        session.add(
            HumanIdentityLinkRow(
                authority=identity.authority.value,
                subject=identity.subject.value,
                organization_id=query.organization_id.value,
                principal_id=access.actor_principal_id.value,
                principal_kind=PrincipalKind.HUMAN,
            )
        )
        session.add(
            IdentityRecoveryAdmissionRow(
                operation_id="new-recovery",
                installation_id=query.installation_id.value,
                authority=identity.authority.value,
                flow_id=uuid4(),
                subject=identity.subject.value,
                event_kind=IdentityRecoveryEventKind.RECOVERY,
            )
        )
    with pytest.raises(AccessDeniedError):
        await observe(database, access, query)


@pytest.mark.asyncio
@pytest.mark.parametrize("history", ["absent", "legacy", "mismatched", "expired"])
async def test_organization_authorized_nonmatches_share_unresolved(
    database: Database, history: str
) -> None:
    access, query, operation, _project = await organization_admitted(database)
    async with database.session() as session, session.begin():
        if history == "absent":
            query = replace(query, key=IdempotencyKey("absent"))
        elif history == "legacy":
            await session.execute(
                update(IdempotencyReservationRow)
                .where(IdempotencyReservationRow.operation_id == operation)
                .values(lookup_authority_family=None, lookup_action_id=None)
            )
        elif history == "mismatched":
            await session.execute(
                update(IdempotencyReservationRow)
                .where(IdempotencyReservationRow.operation_id == operation)
                .values(lookup_action_id="admit-users")
            )
        else:
            await session.execute(
                update(IdempotencyReservationRow)
                .where(IdempotencyReservationRow.operation_id == operation)
                .values(expires_at=func.clock_timestamp() - timedelta(seconds=1))
            )
    assert await observe(database, access, query) == UnresolvedOperationDTO()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "credential", ["current", "stale", "missing_version", "other_identity", "other_installation"]
)
async def test_organization_lookup_uses_current_original_human_credential_binding(
    database: Database, credential: str
) -> None:
    access, query, operation, _project = await organization_admitted(database)
    identity = MockAuthenticationEvidence.browser().identity
    async with database.session() as session, session.begin():
        session.add(
            HumanIdentityLinkRow(
                authority=identity.authority.value,
                subject=identity.subject.value,
                organization_id=query.organization_id.value,
                principal_id=access.actor_principal_id.value,
                principal_kind=PrincipalKind.HUMAN,
            )
        )
        if credential != "missing_version":
            session.add(
                HumanCredentialVersionRow(
                    installation_id=query.installation_id.value,
                    authority=identity.authority.value,
                    subject=identity.subject.value,
                    version=2 if credential == "stale" else 1,
                )
            )
    binding = HumanOAuthCredentialBindingDTO(
        replace(identity, subject=IdentitySubject("another-human"))
        if credential == "other_identity"
        else identity,
        InstallationId(uuid4()) if credential == "other_installation" else query.installation_id,
        HumanCredentialVersion(1),
    )
    access = replace(access, authentication_evidence=binding)
    if credential == "current":
        result = await observe(database, access, query)
        assert isinstance(result, CompletedSynchronousOperationDTO)
        assert result.operation_id.value == operation
    else:
        with pytest.raises(HumanOAuthCredentialRejectedError):
            await observe(database, access, query)
