import asyncio
from typing import override

from sqlalchemy import String, exists, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.application_key_authentication_dto import (
    ApplicationKeyAuthenticationDTO,
)
from inframeld_backend.access.application.dtos.application_key_verification_profile_dto import (
    ApplicationKeyVerificationProfileDTO,
)
from inframeld_backend.access.application.dtos.document_access_facts_dto import (
    DocumentAccessFactsDTO,
)
from inframeld_backend.access.application.protocols.document_access_facts_reader import (
    DocumentAccessFactsReader,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.mappers.postgres_application_key_facts_mapper import (
    PostgresApplicationKeyFactsMapper,
)
from inframeld_backend.access.infrastructure.mappers.postgres_project_actor_mapper import (
    PostgresProjectActorMapper,
)
from inframeld_backend.access.infrastructure.readers.application_key_state_queries import (
    ApplicationKeyStateQueries,
)
from inframeld_backend.access.infrastructure.readers.project_actor_queries import (
    ProjectActorQueries,
)
from inframeld_backend.access.infrastructure.rows.access_group_row import AccessGroupRow
from inframeld_backend.access.infrastructure.rows.application_key_row import ApplicationKeyRow
from inframeld_backend.access.infrastructure.rows.group_membership_row import GroupMembershipRow
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)


class PostgresDocumentAccessFactsReader(DocumentAccessFactsReader):
    """Observe Access state in the caller's short transaction with explicit key profile."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        application_key_profile: ApplicationKeyVerificationProfileDTO | None = None,
    ) -> None:
        self._session = session
        self._application_key_profile = application_key_profile

    @override
    async def read(
        self,
        *,
        access: AccessContextDTO,
        project_id: ProjectId,
        audience_group_ids: frozenset[AccessGroupId],
    ) -> DocumentAccessFactsDTO | None:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Document facts require the active caller transaction.")
        evidence = access.authentication_evidence
        application_key = (
            evidence if isinstance(evidence, ApplicationKeyAuthenticationDTO) else None
        )
        profile = self._application_key_profile
        if application_key is not None and profile is None:
            raise DependencyUnavailableError("The application verification profile is unavailable.")
        try:
            async with asyncio.timeout(5):
                with self._session.no_autoflush:
                    if (
                        await self._session.scalar(
                            select(func.current_setting("transaction_isolation", type_=String()))
                        )
                        != "read committed"
                    ):
                        raise RuntimeError("Document facts require READ COMMITTED isolation.")
                    if application_key is not None:
                        scope = (
                            (
                                await self._session.execute(
                                    ApplicationKeyStateQueries.account_scope(
                                        access.actor_principal_id
                                    )
                                )
                            )
                            .tuples()
                            .one_or_none()
                        )
                        if scope is None:
                            kind = await self._session.scalar(
                                select(PrincipalRow.kind).where(
                                    PrincipalRow.id == access.actor_principal_id.value
                                )
                            )
                            if kind is not None and kind is not PrincipalKind.APPLICATION:
                                raise RuntimeError(
                                    "Authentication evidence does not match the principal kind."
                                )
                            return None
                        if scope[1] != project_id.value:
                            return None
                    organization = await self._session.scalar(
                        select(PrincipalRow.organization_id).where(
                            PrincipalRow.id == access.actor_principal_id.value
                        )
                    )
                    if (
                        organization is None
                        or await self._session.scalar(
                            select(OrganizationRow.id)
                            .where(OrganizationRow.id == organization)
                            .with_for_update(read=True)
                        )
                        is None
                    ):
                        return None
                    if (
                        await self._session.scalar(
                            select(ProjectRow.id)
                            .where(
                                ProjectRow.id == project_id.value,
                                ProjectRow.organization_id == organization,
                            )
                            .with_for_update(read=True)
                        )
                        is None
                    ):
                        return None
                    if application_key is not None:
                        await self._session.scalar(
                            select(ApplicationKeyRow.key_id)
                            .where(
                                ApplicationKeyStateQueries.key_scope(
                                    key_id=application_key.key_id,
                                    principal_id=access.actor_principal_id,
                                    organization_id=OrganizationId(organization),
                                    project_id=project_id,
                                )
                            )
                            .with_for_update(read=True)
                        )
                    # Refresh identity-map rows and credential/recovery state after every wait.
                    row = (
                        (
                            await self._session.execute(
                                ProjectActorQueries.header(access, project_id)
                            )
                        )
                        .tuples()
                        .one_or_none()
                    )
                    if row is None:
                        return None
                    principal, project, installed, member, recovering, linked, version = row
                    if installed is None:
                        raise DependencyUnavailableError()
                    actor = PostgresProjectActorMapper.action(
                        access=access,
                        principal=principal,
                        project=project,
                        member=member,
                        recovering=recovering,
                        linked=linked,
                        version=version,
                        granted=False,
                    )
                    key_facts = None
                    if application_key is not None:
                        assert profile is not None
                        key_row = (
                            (
                                await self._session.execute(
                                    ApplicationKeyStateQueries.current_key(
                                        key_id=application_key.key_id,
                                        principal_id=access.actor_principal_id,
                                        organization_id=OrganizationId(organization),
                                        project_id=project_id,
                                        adapter=profile.adapter,
                                    )
                                )
                            )
                            .tuples()
                            .one_or_none()
                        )
                        key_facts = PostgresApplicationKeyFactsMapper.to_facts(
                            key_row, evidence=application_key, profile=profile
                        )
                    group_member = (
                        exists()
                        .where(
                            GroupMembershipRow.project_id == project_id.value,
                            GroupMembershipRow.group_id == AccessGroupRow.id,
                            GroupMembershipRow.principal_id == access.actor_principal_id.value,
                        )
                        .correlate(AccessGroupRow)
                    )
                    groups = (
                        (
                            await self._session.execute(
                                select(AccessGroupRow.id, group_member).where(
                                    AccessGroupRow.project_id == project_id.value,
                                    AccessGroupRow.id.in_(
                                        tuple(group.value for group in audience_group_ids)
                                    ),
                                )
                            )
                        )
                        .tuples()
                        .all()
                    )
                    return DocumentAccessFactsDTO(
                        principal=actor.principal,
                        organization_id=OrganizationId(project.organization_id),
                        project_id=project_id,
                        project_status=actor.project_status,
                        is_project_member=actor.is_project_member,
                        has_pending_recovery=actor.has_pending_recovery,
                        oauth_credential_facts=actor.oauth_credential_facts,
                        valid_group_ids=frozenset(AccessGroupId(group) for group, _ in groups),
                        member_group_ids=frozenset(
                            AccessGroupId(group) for group, is_member in groups if is_member
                        ),
                        application_key_facts=key_facts,
                    )
        except (TimeoutError, OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None
