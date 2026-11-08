from dataclasses import replace
from datetime import datetime, timedelta
from hmac import compare_digest
from typing import override
from uuid import uuid4

from sqlalchemy import ColumnElement, String, delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.access_group_grant_target_dto import (
    AccessGroupGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.application_account_grant_target_dto import (
    ApplicationAccountGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.invitation_action_grant_intent_dto import (
    InvitationActionGrantIntentDTO,
)
from inframeld_backend.access.application.dtos.invitation_activation_binding_dto import (
    InvitationActivationBindingDTO,
)
from inframeld_backend.access.application.dtos.invitation_activation_result_dto import (
    InvitationActivationResultDTO,
)
from inframeld_backend.access.application.dtos.invitation_group_manager_intent_dto import (
    InvitationGroupManagerIntentDTO,
)
from inframeld_backend.access.application.dtos.invitation_group_membership_intent_dto import (
    InvitationGroupMembershipIntentDTO,
)
from inframeld_backend.access.application.dtos.invitation_project_access_revision_dto import (
    InvitationProjectAccessRevisionDTO,
)
from inframeld_backend.access.application.dtos.invitation_project_membership_intent_dto import (
    InvitationProjectMembershipIntentDTO,
)
from inframeld_backend.access.application.dtos.invitation_record_dto import InvitationRecordDTO
from inframeld_backend.access.application.dtos.invitation_revocation_result_dto import (
    InvitationRevocationResultDTO,
)
from inframeld_backend.access.application.dtos.organization_grant_target_dto import (
    OrganizationGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.project_grant_target_dto import ProjectGrantTargetDTO
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.protocols.invitation_activation_operation_store import (
    InvitationActivationOperationStore,
)
from inframeld_backend.access.application.protocols.invitation_writer import InvitationWriter
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.organization_action import OrganizationAction
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.value_objects.invitation_id import InvitationId
from inframeld_backend.access.domain.value_objects.invitation_token_digest import (
    InvitationTokenDigest,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.mappers.postgres_invitation_mapper import (
    PostgresInvitationMapper,
)
from inframeld_backend.access.infrastructure.readers.postgres_invitation_binding_reader import (
    PostgresInvitationBindingReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_invitation_facts_reader import (
    PostgresInvitationFactsReader,
)
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.access.infrastructure.rows.human_identity_link_row import (
    HumanIdentityLinkRow,
)
from inframeld_backend.access.infrastructure.rows.invitation_activation_operation_row import (
    InvitationActivationOperationRow,
)
from inframeld_backend.access.infrastructure.rows.invitation_revocation_result_row import (
    InvitationRevocationResultRow,
)
from inframeld_backend.access.infrastructure.rows.invitation_row import InvitationRow
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.enums.operation_reservation_state import (
    OperationReservationState,
)
from inframeld_backend.shared.application.errors.application_errors import (
    ConflictError,
    DependencyUnavailableError,
    IdempotencyInProgressError,
    IdempotencyKeyReusedError,
    ResourceNotFoundError,
    StaleRevisionError,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)
from inframeld_backend.shared.infrastructure.rows.installation_identity_row import (
    InstallationIdentityRow,
)
from inframeld_backend.shared.infrastructure.writers.postgres_operation_reservation_writer import (
    PostgresOperationReservationWriter,
)


class PostgresInvitationWriter(InvitationWriter, InvitationActivationOperationStore):
    """Persist the checked invitation and its atomic lifecycle evidence."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def save_issue(
        self, *, record: InvitationRecordDTO, expected_access_revision: int
    ) -> None:
        try:
            await self._save_issue(record=record, expected_access_revision=expected_access_revision)
        except (TimeoutError, OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None

    async def _save_issue(
        self, *, record: InvitationRecordDTO, expected_access_revision: int
    ) -> None:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Invitation persistence requires the active caller transaction.")
        RevisionValidation.require(expected_access_revision)
        RevisionValidation.require(record.issued_access_revision)
        if (
            expected_access_revision == RevisionValidation.MAX_VALUE
            or record.issued_access_revision != expected_access_revision + 1
            or record.issued_at.utcoffset() is None
            or record.expires_at.utcoffset() is None
            or not record.issued_at < record.expires_at <= record.issued_at + timedelta(days=30)
            or not 1 <= len(record.assignments) <= 100
            or record.revoked_at is not None
            or record.consumed_at is not None
            or record.consumed_by_principal_id is not None
        ):
            raise ConflictError("The new invitation has incoherent lifecycle facts.")

        with self._session.no_autoflush:
            reservation = await self._session.get(
                IdempotencyReservationRow, record.issued_operation_id.value, populate_existing=True
            )
            if (
                reservation is None
                or reservation.organization_id != record.organization_id.value
                or reservation.principal_id != record.issuer_principal_id.value
                or reservation.project_id is not None
                or reservation.method != HttpMethod.POST.value
                or reservation.requested_route != "/v1/invitations"
                or reservation.lookup_authority_family is not None
                or reservation.lookup_action_id is not None
                or reservation.state is not OperationReservationState.IN_PROGRESS
                or reservation.replay_kind is not None
                or reservation.expires_at is not None
            ):
                raise ConflictError("Invitation issuance has no matching original reservation.")
            issuer = await self._session.scalar(
                select(PrincipalRow.id).where(
                    PrincipalRow.id == record.issuer_principal_id.value,
                    PrincipalRow.organization_id == record.organization_id.value,
                    PrincipalRow.kind == PrincipalKind.HUMAN,
                    PrincipalRow.status == PrincipalStatus.ACTIVE,
                )
            )
            if issuer is None:
                raise ConflictError("The checked invitation issuer changed.")
            revision = await self._session.scalar(
                select(OrganizationRow.access_revision).where(
                    OrganizationRow.id == record.organization_id.value
                )
            )
            if revision != expected_access_revision:
                raise StaleRevisionError()

        advanced = await self._session.scalar(
            update(OrganizationRow)
            .where(
                OrganizationRow.id == record.organization_id.value,
                OrganizationRow.access_revision == expected_access_revision,
                OrganizationRow.access_revision < RevisionValidation.MAX_VALUE,
            )
            .values(access_revision=OrganizationRow.access_revision + 1)
            .returning(OrganizationRow.access_revision)
        )
        if advanced != record.issued_access_revision:
            raise StaleRevisionError()
        self._session.add(
            InvitationRow(
                id=record.invitation_id.value,
                organization_id=record.organization_id.value,
                issuer_principal_id=record.issuer_principal_id.value,
                token_digest=record.digest.value,
                assignments=PostgresInvitationMapper.to_payload(record.assignments),
                issued_operation_id=record.issued_operation_id.value,
                issued_access_revision=record.issued_access_revision,
                issued_at=record.issued_at,
                expires_at=record.expires_at,
            )
        )
        self._session.add(
            AccessAuditEventRow(
                id=uuid4(),
                organization_id=record.organization_id.value,
                actor_kind=PrincipalKind.HUMAN.value,
                actor_principal_id=record.issuer_principal_id.value,
                event_type="invitation_issued",
                target_kind="invitation",
                target_id=record.invitation_id.value,
                action=OrganizationAction.ADMIT_USERS.value,
                before_values={"access_revision": expected_access_revision},
                after_values={
                    "access_revision": record.issued_access_revision,
                    "assignment_count": len(record.assignments),
                },
                correlation_id=record.issued_operation_id.value,
            )
        )
        await self._session.flush()

    @override
    async def save_revocation(
        self,
        *,
        invitation: InvitationRecordDTO,
        result: InvitationRevocationResultDTO,
        actor_principal_id: PrincipalId,
        expected_access_revision: int,
        revoked_at: datetime,
    ) -> None:
        try:
            await self._save_revocation(
                invitation=invitation,
                result=result,
                actor_principal_id=actor_principal_id,
                expected_access_revision=expected_access_revision,
                revoked_at=revoked_at,
            )
        except (TimeoutError, OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None

    async def _save_revocation(
        self,
        *,
        invitation: InvitationRecordDTO,
        result: InvitationRevocationResultDTO,
        actor_principal_id: PrincipalId,
        expected_access_revision: int,
        revoked_at: datetime,
    ) -> None:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Revocation persistence requires the active caller transaction.")
        RevisionValidation.require(expected_access_revision)
        RevisionValidation.require(result.access_revision)
        changed = invitation.revoked_at is None
        if (
            result.invitation_id != invitation.invitation_id
            or result.organization_id != invitation.organization_id
            or result.access_revision != expected_access_revision + int(changed)
            or result.operation.created is not True
            or result.operation.replay_kind is not OperationReplayKind.SAFE_RESULT
            or result.operation.expires_at.utcoffset() is None
            or revoked_at.utcoffset() is None
            or revoked_at < invitation.issued_at
            or (not changed and revoked_at != invitation.revoked_at)
            or (changed and expected_access_revision == RevisionValidation.MAX_VALUE)
        ):
            raise ConflictError("The checked revocation has incoherent result facts.")
        parent = IdempotencyReservationRow
        with self._session.no_autoflush:
            reservation = await self._session.scalar(
                select(parent)
                .where(
                    parent.operation_id == result.operation.operation_id.value,
                    parent.principal_id == actor_principal_id.value,
                    parent.organization_id == invitation.organization_id.value,
                    parent.project_id.is_(None),
                    parent.method == HttpMethod.POST.value,
                    parent.requested_route
                    == f"/v1/invitations/{invitation.invitation_id.value}/revoke",
                    parent.lookup_authority_family.is_(None),
                    parent.lookup_action_id.is_(None),
                    parent.state == OperationReservationState.REPLAYABLE,
                    parent.replay_kind == OperationReplayKind.SAFE_RESULT,
                    parent.expires_at == result.operation.expires_at,
                    parent.expires_at > func.clock_timestamp(),
                )
                .execution_options(populate_existing=True)
            )
            if reservation is None:
                raise ConflictError("Revocation has no matching native original completion.")
            actor = await self._session.scalar(
                select(PrincipalRow.id).where(
                    PrincipalRow.id == actor_principal_id.value,
                    PrincipalRow.organization_id == invitation.organization_id.value,
                    PrincipalRow.kind == PrincipalKind.HUMAN,
                    PrincipalRow.status == PrincipalStatus.ACTIVE,
                )
            )
            if actor is None:
                raise ConflictError("The checked revocation actor changed.")
            row = await self._session.get(
                InvitationRow, invitation.invitation_id.value, populate_existing=True
            )
            if (
                row is None
                or row.organization_id != invitation.organization_id.value
                or row.issuer_principal_id != invitation.issuer_principal_id.value
                or row.token_digest != invitation.digest.value
                or row.assignments != PostgresInvitationMapper.to_payload(invitation.assignments)
                or row.issued_operation_id != invitation.issued_operation_id.value
                or row.issued_access_revision != invitation.issued_access_revision
                or row.issued_at != invitation.issued_at
                or row.expires_at != invitation.expires_at
                or row.revoked_at != invitation.revoked_at
                or row.consumed_at != invitation.consumed_at
                or row.consumed_by_principal_id
                != (
                    invitation.consumed_by_principal_id.value
                    if invitation.consumed_by_principal_id is not None
                    else None
                )
            ):
                raise ConflictError("The observed invitation changed before revocation.")
            revision = await self._session.scalar(
                select(OrganizationRow.access_revision).where(
                    OrganizationRow.id == invitation.organization_id.value
                )
            )
            if revision != expected_access_revision:
                raise StaleRevisionError()
            if (
                await self._session.get(
                    InvitationRevocationResultRow, result.operation.operation_id.value
                )
                is not None
            ):
                raise ConflictError("The revocation original has already been saved.")

        if changed:
            advanced = await self._session.scalar(
                update(OrganizationRow)
                .where(
                    OrganizationRow.id == invitation.organization_id.value,
                    OrganizationRow.access_revision == expected_access_revision,
                    OrganizationRow.access_revision < RevisionValidation.MAX_VALUE,
                )
                .values(access_revision=OrganizationRow.access_revision + 1)
                .returning(OrganizationRow.access_revision)
            )
            if advanced != result.access_revision:
                raise StaleRevisionError()
            marked = await self._session.scalar(
                update(InvitationRow)
                .where(
                    InvitationRow.id == invitation.invitation_id.value,
                    InvitationRow.organization_id == invitation.organization_id.value,
                    InvitationRow.revoked_at.is_(None),
                )
                .values(revoked_at=revoked_at)
                .returning(InvitationRow.id)
            )
            if marked is None:
                raise ConflictError("The invitation was already revoked.")
        self._session.add(
            AccessAuditEventRow(
                id=uuid4(),
                organization_id=invitation.organization_id.value,
                actor_kind=PrincipalKind.HUMAN.value,
                actor_principal_id=actor_principal_id.value,
                event_type="invitation_revoked",
                target_kind="invitation",
                target_id=invitation.invitation_id.value,
                action=OrganizationAction.ADMIT_USERS.value,
                before_values={"access_revision": expected_access_revision, "revoked": not changed},
                after_values={"access_revision": result.access_revision, "revoked": True},
                correlation_id=result.operation.operation_id.value,
            )
        )
        self._session.add(
            InvitationRevocationResultRow(
                operation_id=result.operation.operation_id.value,
                organization_id=invitation.organization_id.value,
                actor_principal_id=actor_principal_id.value,
                invitation_id=invitation.invitation_id.value,
                before_revision=expected_access_revision,
                access_revision=result.access_revision,
                changed=changed,
            )
        )
        await self._session.flush()

    @override
    async def read_activation_original(
        self,
        *,
        installation_id: InstallationId,
        identity: VerifiedHumanIdentityDTO,
        organization_id: OrganizationId,
        invitation_id: InvitationId,
        principal_id: PrincipalId | None,
        context: IdempotencyContextDTO,
        fingerprint: RequestFingerprint,
    ) -> InvitationActivationResultDTO | None:
        try:
            await self._require_activation_transaction(context)
            with self._session.no_autoflush:
                row = await self._session.scalar(
                    select(InvitationActivationOperationRow)
                    .where(
                        *self._activation_namespace(
                            installation_id, identity, organization_id, context
                        )
                    )
                    .execution_options(populate_existing=True, autoflush=False)
                )
                if row is None:
                    return None
                now = await self._session.scalar(select(func.clock_timestamp()))
                if row.expires_at is not None and now is not None and row.expires_at <= now:
                    return None
                if not compare_digest(row.request_fingerprint, fingerprint.value):
                    raise IdempotencyKeyReusedError()
                if row.invitation_id != invitation_id.value:
                    raise ConflictError("The activation original changed its invitation binding.")
                if row.state is OperationReservationState.IN_PROGRESS:
                    raise IdempotencyInProgressError(
                        OperationId(row.operation_id), retry_after_seconds=1
                    )
                if (
                    row.state is not OperationReservationState.REPLAYABLE
                    or principal_id is None
                    or row.principal_id != principal_id.value
                    or row.completed_at is None
                    or row.expires_at is None
                    or row.organization_access_revision is None
                    or row.project_access_revisions is None
                    or now is None
                    or row.expires_at <= row.completed_at
                ):
                    raise ConflictError("The activation has no coherent live original outcome.")
                try:
                    RevisionValidation.require(row.organization_access_revision)
                    if row.organization_access_revision < 1:
                        raise ValueError("The retained Organization revision is invalid.")
                    revisions = PostgresInvitationMapper.from_project_revisions(
                        row.project_access_revisions
                    )
                except (TypeError, ValueError, KeyError):
                    raise DependencyUnavailableError() from None
                return InvitationActivationResultDTO(
                    invitation_id=invitation_id,
                    organization_id=organization_id,
                    principal_id=principal_id,
                    organization_access_revision=row.organization_access_revision,
                    project_access_revisions=revisions,
                    operation=CompletedSynchronousOperationDTO(
                        operation_id=OperationId(row.operation_id),
                        created=False,
                        replay_kind=OperationReplayKind.SAFE_RESULT,
                        expires_at=row.expires_at,
                    ),
                )
        except (TimeoutError, OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None

    @override
    async def reserve_activation(
        self,
        *,
        installation_id: InstallationId,
        identity: VerifiedHumanIdentityDTO,
        invitation: InvitationRecordDTO,
        principal_id: PrincipalId | None,
        context: IdempotencyContextDTO,
        fingerprint: RequestFingerprint,
    ) -> InvitationActivationBindingDTO:
        try:
            await self._require_activation_transaction(context)
            with self._session.no_autoflush:
                installed = await self._session.scalar(
                    select(InstallationIdentityRow.installation_id).where(
                        InstallationIdentityRow.singleton_key == 1
                    )
                )
                if installed != installation_id.value:
                    raise ConflictError("The pending activation changed its installation binding.")
                current = await self._session.scalar(
                    select(InvitationRow.id).where(
                        InvitationRow.id == invitation.invitation_id.value,
                        InvitationRow.organization_id == invitation.organization_id.value,
                        InvitationRow.issuer_principal_id == invitation.issuer_principal_id.value,
                        InvitationRow.token_digest == invitation.digest.value,
                    )
                )
                link = await self._session.scalar(
                    select(HumanIdentityLinkRow)
                    .where(
                        HumanIdentityLinkRow.authority == identity.authority.value,
                        HumanIdentityLinkRow.subject == identity.subject.value,
                    )
                    .execution_options(populate_existing=True, autoflush=False)
                )
                if current is None or (link is None) != (principal_id is None):
                    raise ConflictError(
                        "The pending activation changed its invitation or recipient."
                    )
                if link is not None and (
                    principal_id is None
                    or link.principal_id != principal_id.value
                    or link.organization_id != invitation.organization_id.value
                    or link.principal_kind is not PrincipalKind.HUMAN
                ):
                    raise ConflictError("The pending activation changed its identity binding.")
                namespace = self._activation_namespace(
                    installation_id, identity, invitation.organization_id, context
                )
                await self._session.execute(
                    delete(InvitationActivationOperationRow).where(
                        *namespace,
                        InvitationActivationOperationRow.state
                        == OperationReservationState.REPLAYABLE,
                        InvitationActivationOperationRow.expires_at <= func.clock_timestamp(),
                    )
                )
                operation_id = OperationId(str(uuid4()))
                inserted = await self._session.scalar(
                    insert(InvitationActivationOperationRow)
                    .values(
                        operation_id=operation_id.value,
                        installation_id=installation_id.value,
                        authority=identity.authority.value,
                        subject=identity.subject.value,
                        organization_id=invitation.organization_id.value,
                        invitation_id=invitation.invitation_id.value,
                        issuer_principal_id=invitation.issuer_principal_id.value,
                        method=context.method.value,
                        requested_route=context.requested_route,
                        request_key=context.key.value,
                        request_fingerprint=fingerprint.value,
                        principal_id=principal_id.value if principal_id is not None else None,
                    )
                    .on_conflict_do_nothing(constraint="uq_invitation_activation_namespace")
                    .returning(InvitationActivationOperationRow.operation_id)
                )
                if inserted is None:
                    original = await self._session.scalar(
                        select(InvitationActivationOperationRow)
                        .where(*namespace)
                        .execution_options(populate_existing=True, autoflush=False)
                    )
                    if original is None:
                        raise RuntimeError("The conflicting activation reservation was not found.")
                    if not compare_digest(original.request_fingerprint, fingerprint.value):
                        raise IdempotencyKeyReusedError()
                    if original.state is OperationReservationState.IN_PROGRESS:
                        raise IdempotencyInProgressError(
                            OperationId(original.operation_id), retry_after_seconds=1
                        )
                    raise ConflictError(
                        "Recover the matching completed activation before fresh execution."
                    )
                if inserted != operation_id.value:
                    raise RuntimeError("Activation reservation changed its original operation.")
                return InvitationActivationBindingDTO(
                    operation_id=operation_id,
                    installation_id=installation_id,
                    identity=identity,
                    organization_id=invitation.organization_id,
                    invitation_id=invitation.invitation_id,
                    issuer_principal_id=invitation.issuer_principal_id,
                    principal_id=principal_id,
                    context=context,
                    fingerprint=fingerprint,
                )
        except (TimeoutError, OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None

    @override
    async def bind_activation_principal(
        self, *, binding: InvitationActivationBindingDTO, principal: Principal
    ) -> InvitationActivationBindingDTO:
        try:
            reader = PostgresInvitationBindingReader(self._session)
            row = await reader.require_pending_activation(binding)
            if (
                principal.organization_id != binding.organization_id
                or principal.kind is not PrincipalKind.HUMAN
                or principal.status is not PrincipalStatus.ACTIVE
                or (binding.principal_id is not None and binding.principal_id != principal.id)
            ):
                raise ConflictError("The activation principal changed its checked binding.")
            await reader.require_activation_principal(binding=binding, principal_id=principal.id)
            row.principal_id = principal.id.value
            await self._session.flush()
            return replace(binding, principal_id=principal.id)
        except (TimeoutError, OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None

    @override
    async def complete_activation(
        self,
        *,
        binding: InvitationActivationBindingDTO,
        digest: InvitationTokenDigest,
        organization_access_revision: int,
        project_access_revisions: tuple[InvitationProjectAccessRevisionDTO, ...],
    ) -> InvitationActivationResultDTO:
        try:
            reader = PostgresInvitationBindingReader(self._session)
            row = await reader.require_pending_activation(binding)
            if binding.principal_id is None:
                raise ConflictError(
                    "Activation completion requires its admitted principal binding."
                )
            await reader.require_activation_principal(
                binding=binding, principal_id=binding.principal_id
            )
            record = await PostgresInvitationFactsReader(self._session).read_by_digest(digest)
            if (
                record is None
                or record.invitation_id != binding.invitation_id
                or record.organization_id != binding.organization_id
                or record.issuer_principal_id != binding.issuer_principal_id
            ):
                raise ResourceNotFoundError()
            RevisionValidation.require(organization_access_revision)
            if organization_access_revision < 1:
                raise ValueError("The completed Organization revision is invalid.")
            payload = PostgresInvitationMapper.to_project_revisions(project_access_revisions)
            expected_projects: set[ProjectId] = set()
            for intent in record.assignments:
                if isinstance(
                    intent,
                    (
                        InvitationProjectMembershipIntentDTO,
                        InvitationGroupMembershipIntentDTO,
                        InvitationGroupManagerIntentDTO,
                    ),
                ):
                    expected_projects.add(intent.project_id)
                elif isinstance(intent, InvitationActionGrantIntentDTO):
                    if isinstance(
                        intent.target,
                        (
                            ProjectGrantTargetDTO,
                            AccessGroupGrantTargetDTO,
                            ApplicationAccountGrantTargetDTO,
                        ),
                    ):
                        expected_projects.add(intent.target.project_id)
                    elif (
                        not isinstance(intent.target, OrganizationGrantTargetDTO)
                        or intent.target.organization_id != binding.organization_id
                    ):
                        raise ConflictError("The invitation target owner is not available.")
            if {item.project_id for item in project_access_revisions} != expected_projects:
                raise RuntimeError(
                    "Activation completion changed its exact intended Project scope."
                )
            current_revision = await self._session.scalar(
                select(OrganizationRow.access_revision).where(
                    OrganizationRow.id == binding.organization_id.value
                )
            )
            if current_revision != organization_access_revision:
                raise StaleRevisionError()
            for project in project_access_revisions:
                current = await self._session.scalar(
                    select(ProjectRow.access_revision).where(
                        ProjectRow.id == project.project_id.value,
                        ProjectRow.organization_id == binding.organization_id.value,
                    )
                )
                if current != project.access_revision:
                    raise StaleRevisionError()
            completed_at = await self._session.scalar(
                update(InvitationRow)
                .where(
                    InvitationRow.id == binding.invitation_id.value,
                    InvitationRow.organization_id == binding.organization_id.value,
                    InvitationRow.issuer_principal_id == binding.issuer_principal_id.value,
                    InvitationRow.token_digest == digest.value,
                    InvitationRow.revoked_at.is_(None),
                    InvitationRow.consumed_at.is_(None),
                    InvitationRow.consumed_by_principal_id.is_(None),
                    InvitationRow.expires_at > func.clock_timestamp(),
                )
                .values(
                    consumed_at=func.clock_timestamp(),
                    consumed_by_principal_id=binding.principal_id.value,
                )
                .returning(InvitationRow.consumed_at)
            )
            if completed_at is None:
                raise ResourceNotFoundError()
            expiry = completed_at + PostgresOperationReservationWriter.COMPLETED_ORIGINAL_RETENTION
            row.state = OperationReservationState.REPLAYABLE
            row.completed_at = completed_at
            row.expires_at = expiry
            row.organization_access_revision = organization_access_revision
            row.project_access_revisions = payload
            audit = AccessAuditEventRow(
                id=uuid4(),
                organization_id=binding.organization_id.value,
                actor_kind=PrincipalKind.HUMAN.value,
                actor_principal_id=binding.principal_id.value,
                affected_principal_id=binding.principal_id.value,
                event_type="invitation_activated",
                target_kind="invitation",
                target_id=binding.invitation_id.value,
                before_values={"consumed": False},
                after_values={"consumed": True},
                correlation_id=binding.operation_id.value,
            )
            audit.occurred_at = completed_at
            self._session.add(audit)
            await self._session.flush()
            return InvitationActivationResultDTO(
                invitation_id=binding.invitation_id,
                organization_id=binding.organization_id,
                principal_id=binding.principal_id,
                organization_access_revision=organization_access_revision,
                project_access_revisions=project_access_revisions,
                operation=CompletedSynchronousOperationDTO(
                    operation_id=binding.operation_id,
                    created=True,
                    replay_kind=OperationReplayKind.SAFE_RESULT,
                    expires_at=expiry,
                ),
            )
        except (TimeoutError, OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None

    async def _require_activation_transaction(self, context: IdempotencyContextDTO) -> None:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Activation persistence requires the active caller transaction.")
        if (
            context.method is not HttpMethod.POST
            or context.requested_route != "/v1/invitations/activate"
        ):
            raise RuntimeError("Activation persistence changed its native method or route.")
        if (
            await self._session.scalar(
                select(func.current_setting("transaction_isolation", type_=String()))
            )
            != "read committed"
        ):
            raise RuntimeError("Activation persistence requires READ COMMITTED isolation.")

    @staticmethod
    def _activation_namespace(
        installation_id: InstallationId,
        identity: VerifiedHumanIdentityDTO,
        organization_id: OrganizationId,
        context: IdempotencyContextDTO,
    ) -> tuple[ColumnElement[bool], ...]:
        return (
            InvitationActivationOperationRow.installation_id == installation_id.value,
            InvitationActivationOperationRow.authority == identity.authority.value,
            InvitationActivationOperationRow.subject == identity.subject.value,
            InvitationActivationOperationRow.organization_id == organization_id.value,
            InvitationActivationOperationRow.method == context.method.value,
            InvitationActivationOperationRow.requested_route == context.requested_route,
            InvitationActivationOperationRow.request_key == context.key.value,
        )
