import asyncio
from typing import override
from uuid import UUID

from sqlalchemy import String, exists, func, select, tuple_
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.access_group_grant_target_dto import (
    AccessGroupGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.application_account_grant_target_dto import (
    ApplicationAccountGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.human_credential_state_dto import (
    HumanCredentialStateDTO,
)
from inframeld_backend.access.application.dtos.invitation_activation_binding_dto import (
    InvitationActivationBindingDTO,
)
from inframeld_backend.access.application.dtos.invitation_admission_only_intent_dto import (
    InvitationAdmissionOnlyIntentDTO,
)
from inframeld_backend.access.application.dtos.invitation_assignment_dto import (
    InvitationAssignmentDTO,
)
from inframeld_backend.access.application.dtos.invitation_group_manager_intent_dto import (
    InvitationGroupManagerIntentDTO,
)
from inframeld_backend.access.application.dtos.invitation_group_membership_intent_dto import (
    InvitationGroupMembershipIntentDTO,
)
from inframeld_backend.access.application.dtos.invitation_model_connection_target_dto import (
    InvitationModelConnectionTargetDTO,
)
from inframeld_backend.access.application.dtos.invitation_preview_facts_dto import (
    InvitationPreviewFactsDTO,
)
from inframeld_backend.access.application.dtos.invitation_project_membership_intent_dto import (
    InvitationProjectMembershipIntentDTO,
)
from inframeld_backend.access.application.dtos.invitation_record_dto import InvitationRecordDTO
from inframeld_backend.access.application.dtos.invitation_scope_dto import InvitationScopeDTO
from inframeld_backend.access.application.dtos.invitation_target_dto import InvitationTargetDTO
from inframeld_backend.access.application.dtos.organization_grant_target_dto import (
    OrganizationGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.project_grant_target_dto import ProjectGrantTargetDTO
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.protocols.invitation_preview_facts_reader import (
    InvitationPreviewFactsReader,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.policies.human_admission_policy import HumanAdmissionPolicy
from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
from inframeld_backend.access.domain.value_objects.invitation_token_digest import (
    InvitationTokenDigest,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.mappers.postgres_human_credential_state_mapper import (
    PostgresHumanCredentialStateMapper,
)
from inframeld_backend.access.infrastructure.mappers.postgres_invitation_mapper import (
    PostgresInvitationMapper,
)
from inframeld_backend.access.infrastructure.readers.human_credential_state_queries import (
    HumanCredentialStateQueries,
)
from inframeld_backend.access.infrastructure.readers.postgres_invitation_facts_reader import (
    PostgresInvitationFactsReader,
)
from inframeld_backend.access.infrastructure.rows.access_group_row import AccessGroupRow
from inframeld_backend.access.infrastructure.rows.application_account_row import (
    ApplicationAccountRow,
)
from inframeld_backend.access.infrastructure.rows.human_identity_link_row import (
    HumanIdentityLinkRow,
)
from inframeld_backend.access.infrastructure.rows.invitation_activation_operation_row import (
    InvitationActivationOperationRow,
)
from inframeld_backend.access.infrastructure.rows.invitation_row import InvitationRow
from inframeld_backend.access.infrastructure.rows.model_connection_row import ModelConnectionRow
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_membership_row import ProjectMembershipRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.enums.operation_reservation_state import (
    OperationReservationState,
)
from inframeld_backend.shared.application.errors.application_errors import (
    ConflictError,
    DependencyUnavailableError,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.infrastructure.rows.installation_identity_row import (
    InstallationIdentityRow,
)


class PostgresInvitationBindingReader(InvitationPreviewFactsReader):
    """Observe exact recipient state and safe labels without admitting or assigning anyone."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def read_preview(
        self, *, identity: VerifiedHumanIdentityDTO, digest: InvitationTokenDigest
    ) -> InvitationPreviewFactsDTO | None:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Invitation preview requires the active caller read transaction.")
        try:
            async with asyncio.timeout(5):
                with self._session.no_autoflush:
                    invitation = await PostgresInvitationFactsReader(self._session).read_by_digest(
                        digest
                    )
                    if invitation is None:
                        return None
                    principal, state, history = await self._recipient(identity)
                    return InvitationPreviewFactsDTO(
                        invitation=invitation,
                        principal=principal,
                        credential_state=state,
                        has_credential_history=history,
                        scopes=await self._scopes(invitation),
                    )
        except (TimeoutError, OperationalError, SqlAlchemyTimeoutError, TypeError, ValueError):
            raise DependencyUnavailableError() from None

    async def _recipient(
        self, identity: VerifiedHumanIdentityDTO
    ) -> tuple[Principal | None, HumanCredentialStateDTO, bool]:
        link = await self._session.scalar(
            select(HumanIdentityLinkRow)
            .where(
                HumanIdentityLinkRow.authority == identity.authority.value,
                HumanIdentityLinkRow.subject == identity.subject.value,
            )
            .execution_options(populate_existing=True, autoflush=False)
        )
        principal = None
        if link is not None:
            row = await self._session.scalar(
                select(PrincipalRow)
                .where(
                    PrincipalRow.id == link.principal_id,
                    PrincipalRow.organization_id == link.organization_id,
                    PrincipalRow.kind == link.principal_kind,
                )
                .execution_options(populate_existing=True, autoflush=False)
            )
            if row is None or link.principal_kind is not PrincipalKind.HUMAN:
                raise DependencyUnavailableError("The recipient identity link is incoherent.")
            principal = Principal(
                id=PrincipalId(row.id),
                organization_id=OrganizationId(row.organization_id),
                kind=row.kind,
                status=row.status,
            )
        state_row = (
            (await self._session.execute(HumanCredentialStateQueries.for_identity(identity)))
            .tuples()
            .one_or_none()
        )
        state = PostgresHumanCredentialStateMapper.to_state(identity, state_row)
        if state_row is None:
            raise DependencyUnavailableError()
        return principal, state, state_row[3]

    @staticmethod
    def _targets(
        invitation: InvitationRecordDTO, model_projects: dict[UUID, ProjectId]
    ) -> set[InvitationTargetDTO] | None:
        targets: set[InvitationTargetDTO] = {
            OrganizationGrantTargetDTO(organization_id=invitation.organization_id)
        }
        for intent in invitation.assignments:
            if isinstance(intent, InvitationAdmissionOnlyIntentDTO):
                continue
            if isinstance(intent, InvitationProjectMembershipIntentDTO):
                targets.add(ProjectGrantTargetDTO(project_id=intent.project_id))
            elif isinstance(
                intent, (InvitationGroupMembershipIntentDTO, InvitationGroupManagerIntentDTO)
            ):
                targets.add(ProjectGrantTargetDTO(project_id=intent.project_id))
                targets.add(
                    AccessGroupGrantTargetDTO(
                        project_id=intent.project_id, access_group_id=intent.access_group_id
                    )
                )
            else:
                target = intent.target
                if isinstance(target, OrganizationGrantTargetDTO):
                    if target.organization_id != invitation.organization_id:
                        return None
                elif isinstance(
                    target,
                    (
                        ProjectGrantTargetDTO,
                        AccessGroupGrantTargetDTO,
                        ApplicationAccountGrantTargetDTO,
                    ),
                ):
                    targets.add(ProjectGrantTargetDTO(project_id=target.project_id))
                elif isinstance(target, InvitationModelConnectionTargetDTO):
                    project = model_projects.get(target.model_connection_id)
                    if project is None:
                        return None
                    targets.add(ProjectGrantTargetDTO(project))
                else:
                    return None
                targets.add(target)
        return targets

    async def _scopes(
        self, invitation: InvitationRecordDTO
    ) -> tuple[InvitationScopeDTO, ...] | None:
        model_projects = await PostgresInvitationFactsReader(self._session).model_projects(
            invitation.organization_id, invitation.assignments
        )
        targets = self._targets(invitation, model_projects)
        if targets is None:
            return None
        organization = await self._session.scalar(
            select(OrganizationRow.name).where(
                OrganizationRow.id == invitation.organization_id.value
            )
        )
        if organization is None:
            return None
        labels: dict[InvitationTargetDTO, str] = {
            OrganizationGrantTargetDTO(organization_id=invitation.organization_id): organization
        }
        projects = [
            target.project_id.value
            for target in targets
            if isinstance(target, ProjectGrantTargetDTO)
        ]
        if projects:
            project_rows = (
                (
                    await self._session.execute(
                        select(ProjectRow.id, ProjectRow.name)
                        .where(
                            ProjectRow.id.in_(projects),
                            ProjectRow.organization_id == invitation.organization_id.value,
                            ProjectRow.status == ProjectStatus.ACTIVE,
                        )
                        .order_by(ProjectRow.id)
                    )
                )
                .tuples()
                .all()
            )
            for project_id, name in project_rows:
                labels[ProjectGrantTargetDTO(project_id=ProjectId(project_id))] = name
        groups = [
            (target.project_id.value, target.access_group_id.value)
            for target in targets
            if isinstance(target, AccessGroupGrantTargetDTO)
        ]
        if groups:
            group_rows = (
                (
                    await self._session.execute(
                        select(AccessGroupRow.project_id, AccessGroupRow.id, AccessGroupRow.name)
                        .join(ProjectRow, ProjectRow.id == AccessGroupRow.project_id)
                        .where(
                            tuple_(AccessGroupRow.project_id, AccessGroupRow.id).in_(groups),
                            ProjectRow.organization_id == invitation.organization_id.value,
                            ProjectRow.status == ProjectStatus.ACTIVE,
                        )
                        .order_by(AccessGroupRow.project_id, AccessGroupRow.id)
                    )
                )
                .tuples()
                .all()
            )
            for project_id, group_id, name in group_rows:
                labels[
                    AccessGroupGrantTargetDTO(
                        project_id=ProjectId(project_id), access_group_id=AccessGroupId(group_id)
                    )
                ] = name
        applications = [
            (target.project_id.value, target.application_principal_id.value)
            for target in targets
            if isinstance(target, ApplicationAccountGrantTargetDTO)
        ]
        if applications:
            bound = (
                exists()
                .where(
                    ProjectMembershipRow.project_id == ApplicationAccountRow.project_id,
                    ProjectMembershipRow.organization_id == invitation.organization_id.value,
                    ProjectMembershipRow.principal_id == ApplicationAccountRow.principal_id,
                    ProjectMembershipRow.application_principal_id
                    == ApplicationAccountRow.principal_id,
                    ProjectMembershipRow.principal_kind == PrincipalKind.APPLICATION,
                )
                .correlate(ApplicationAccountRow)
            )
            application_rows = (
                (
                    await self._session.execute(
                        select(
                            ApplicationAccountRow.project_id,
                            ApplicationAccountRow.principal_id,
                            PrincipalRow.display_name,
                        )
                        .join(PrincipalRow, PrincipalRow.id == ApplicationAccountRow.principal_id)
                        .join(ProjectRow, ProjectRow.id == ApplicationAccountRow.project_id)
                        .where(
                            tuple_(
                                ApplicationAccountRow.project_id, ApplicationAccountRow.principal_id
                            ).in_(applications),
                            ApplicationAccountRow.organization_id
                            == invitation.organization_id.value,
                            ProjectRow.organization_id == invitation.organization_id.value,
                            ProjectRow.status == ProjectStatus.ACTIVE,
                            ApplicationAccountRow.principal_kind == PrincipalKind.APPLICATION,
                            PrincipalRow.organization_id == invitation.organization_id.value,
                            PrincipalRow.kind == PrincipalKind.APPLICATION,
                            PrincipalRow.status == PrincipalStatus.ACTIVE,
                            bound,
                        )
                        .order_by(
                            ApplicationAccountRow.project_id, ApplicationAccountRow.principal_id
                        )
                    )
                )
                .tuples()
                .all()
            )
            for project_id, principal_id, name in application_rows:
                labels[
                    ApplicationAccountGrantTargetDTO(
                        project_id=ProjectId(project_id),
                        application_principal_id=PrincipalId(principal_id),
                    )
                ] = name
        model_ids = [
            target.model_connection_id
            for target in targets
            if isinstance(target, InvitationModelConnectionTargetDTO)
        ]
        if model_ids:
            rows = (
                await self._session.execute(
                    select(
                        ModelConnectionRow.id,
                        ModelConnectionRow.project_id,
                        ModelConnectionRow.display_name,
                    )
                    .join(ProjectRow, ProjectRow.id == ModelConnectionRow.project_id)
                    .where(
                        ModelConnectionRow.id.in_(model_ids),
                        ModelConnectionRow.organization_id == invitation.organization_id.value,
                        ProjectRow.organization_id == invitation.organization_id.value,
                        ProjectRow.status == ProjectStatus.ACTIVE,
                        ModelConnectionRow.retired_at.is_(None),
                    )
                    .order_by(ModelConnectionRow.id)
                )
            ).tuples()
            for connection_id, project_id, label in rows:
                if model_projects.get(connection_id) != ProjectId(project_id):
                    return None
                labels[InvitationModelConnectionTargetDTO(connection_id)] = label
        if set(labels) != targets:
            return None
        return tuple(
            InvitationScopeDTO(
                target=target,
                display_name=name,
                model_project_id=model_projects[target.model_connection_id]
                if isinstance(target, InvitationModelConnectionTargetDTO)
                else None,
            )
            for target, name in labels.items()
        )

    async def require_pending_activation(
        self, binding: InvitationActivationBindingDTO
    ) -> InvitationActivationOperationRow:
        """Lock the actual uncompleted original with its exact immutable pending binding.

        This persistence guard is shared by invitation state entries, never ordinary
        native reservations. It proves neither fresh authority nor target eligibility.
        The caller retains identity, Organization and sorted Project coordination.
        """
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Activation persistence requires the active caller transaction.")
        if (
            binding.context.method is not HttpMethod.POST
            or binding.context.requested_route != "/v1/invitations/activate"
        ):
            raise RuntimeError("Activation changed its original method or route.")
        with self._session.no_autoflush:
            if (
                await self._session.scalar(
                    select(func.current_setting("transaction_isolation", type_=String()))
                )
                != "read committed"
            ):
                raise RuntimeError("Activation persistence requires READ COMMITTED isolation.")
            row = await self._session.scalar(
                select(InvitationActivationOperationRow)
                .join(
                    InvitationRow,
                    (InvitationRow.id == InvitationActivationOperationRow.invitation_id)
                    & (
                        InvitationRow.organization_id
                        == InvitationActivationOperationRow.organization_id
                    )
                    & (
                        InvitationRow.issuer_principal_id
                        == InvitationActivationOperationRow.issuer_principal_id
                    ),
                )
                .join(
                    InstallationIdentityRow,
                    InstallationIdentityRow.installation_id
                    == InvitationActivationOperationRow.installation_id,
                )
                .where(
                    InvitationActivationOperationRow.operation_id == binding.operation_id.value,
                    InvitationActivationOperationRow.installation_id
                    == binding.installation_id.value,
                    InstallationIdentityRow.singleton_key == 1,
                    InvitationActivationOperationRow.authority == binding.identity.authority.value,
                    InvitationActivationOperationRow.subject == binding.identity.subject.value,
                    InvitationActivationOperationRow.organization_id
                    == binding.organization_id.value,
                    InvitationActivationOperationRow.invitation_id == binding.invitation_id.value,
                    InvitationActivationOperationRow.issuer_principal_id
                    == binding.issuer_principal_id.value,
                    InvitationActivationOperationRow.method == binding.context.method.value,
                    InvitationActivationOperationRow.requested_route
                    == binding.context.requested_route,
                    InvitationActivationOperationRow.request_key == binding.context.key.value,
                    InvitationActivationOperationRow.request_fingerprint
                    == binding.fingerprint.value,
                    InvitationActivationOperationRow.principal_id.is_not_distinct_from(
                        binding.principal_id.value if binding.principal_id is not None else None
                    ),
                    InvitationActivationOperationRow.state == OperationReservationState.IN_PROGRESS,
                    InvitationActivationOperationRow.completed_at.is_(None),
                    InvitationActivationOperationRow.expires_at.is_(None),
                    InvitationActivationOperationRow.organization_access_revision.is_(None),
                    InvitationActivationOperationRow.project_access_revisions.is_(None),
                )
                .with_for_update(of=InvitationActivationOperationRow)
                .execution_options(populate_existing=True, autoflush=False)
            )
            if row is None:
                raise ConflictError("Activation has no matching pending original binding.")
            return row

    async def require_activation_principal(
        self, *, binding: InvitationActivationBindingDTO, principal_id: PrincipalId
    ) -> None:
        """Require the exact flushed active human link, preserving current recovery/history safeguards."""
        with self._session.no_autoflush:
            principal, state, history = await self._recipient(binding.identity)
            if (
                principal is None
                or principal.id != principal_id
                or state.installation_id != binding.installation_id
                or not HumanAdmissionPolicy.may_admit(
                    principal=principal,
                    organization_id=binding.organization_id,
                    has_pending_recovery=state.has_pending_recovery,
                )
            ):
                raise ConflictError("The activation recipient binding is no longer admissible.")
            if state.version is None and history:
                raise DependencyUnavailableError()

    async def require_assignment_binding(
        self,
        *,
        binding: InvitationActivationBindingDTO,
        principal_id: PrincipalId,
        intent: InvitationAssignmentDTO,
        organization_id: OrganizationId,
        issuer_principal_id: PrincipalId,
        installation_id: InstallationId | None = None,
    ) -> None:
        """Bind a checked assignment to the real pending original and exact stored promise.

        The application has already coordinated and checked current issuer authority.
        This guard preserves the bound recipient and never manufactures native admission.
        """
        try:
            async with asyncio.timeout(5):
                await self.require_pending_activation(binding)
                if (
                    binding.principal_id != principal_id
                    or binding.organization_id != organization_id
                    or binding.issuer_principal_id != issuer_principal_id
                    or (installation_id is not None and binding.installation_id != installation_id)
                ):
                    raise ConflictError("The assignment changed its exact activation scope.")
                await self.require_activation_principal(binding=binding, principal_id=principal_id)
                with self._session.no_autoflush:
                    payload = await self._session.scalar(
                        select(InvitationRow.assignments)
                        .where(
                            InvitationRow.id == binding.invitation_id.value,
                            InvitationRow.organization_id == binding.organization_id.value,
                            InvitationRow.issuer_principal_id == binding.issuer_principal_id.value,
                        )
                        .execution_options(autoflush=False)
                    )
                    if payload is None or intent not in PostgresInvitationMapper.from_payload(
                        payload
                    ):
                        raise ConflictError(
                            "The assignment is not an exact stored invitation promise."
                        )
        except (TimeoutError, OperationalError, SqlAlchemyTimeoutError, TypeError, ValueError):
            raise DependencyUnavailableError() from None
